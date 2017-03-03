from uconf import BN_BITRATE

SW_TYPE_UGUALE = 'sw_uguale'
SW_TYPE_1FIFO = 'sw_fifo'


def gen_script(queuelen, sw_type, num_queues, server_intf, client_intfs, server_ip, client_intf_to_source_ips,
               num_bands):
    """

    :param queuelen: num. of packets for each switch-port queue
    :param num_queues: number of priority queues
    :param server_intf: name of the intf connected to the server
    :param client_intfs: list of intf names connected to clients
    :return:
    """
    lines = []
    all_intfs = client_intfs + [server_intf]

    intf_to_port_num = {all_intfs[x - 1]: x for x in range(1, len(all_intfs) + 1)}

    # Set the switch in secure-mode
    # it will need a controller, stop to learn
    lines.append("ovs-vsctl del-br brUG")
    lines.append("tc qdisc del dev {} root".format(server_intf))
    # lines.append("ovs-ofctl -O openflow13 del-flows brUG")
    lines.append("ovs-vsctl --all destroy queue")
    lines.append("ovs-vsctl --all destroy qos")
    lines.extend(["tc qdisc del dev {} root".format(intf, queuelen) for intf in all_intfs])

    lines.append('set -e')
    lines.extend(["ifconfig {} txqueuelen {}".format(intf, queuelen) for intf in all_intfs])

    lines.append("ovs-vsctl add-br brUG")
    lines.extend(["ovs-vsctl add-port brUG %s" % intf for intf in all_intfs])
    lines.extend(["ifconfig %s up 0.0.0.0" % intf for intf in all_intfs])

    if sw_type == SW_TYPE_1FIFO:
        lines.extend(['echo TC CONF %s && tc qdisc show dev %s' % (intf, intf) for intf in all_intfs])
        return lines

    lines.append("ovs-vsctl set-fail-mode brUG secure")
    # Create N Round robin queues on eth4 with ovs-vsctl
    qos = "ovs-vsctl set port {} qos=@newqos -- ".format(server_intf)
    qos += "\\\n    --id=@newqos create qos type=linux-htb other-config:max-rate={} queues=".format(BN_BITRATE)

    for i in range(1, num_queues + 1):  # i=1..8
        qos += "{}=@q{}".format(i, i)
        if i < num_queues:
            qos += ","
        else:
            qos += " -- "

    for i in range(1, num_queues + 1):
        qos += "\\\n\t--id=@q{} create queue other-config:min-rate=600 other-config:max-rate={}".format(i, BN_BITRATE)
        if i < num_queues:
            qos += " -- "

    lines.append(qos)

    # Substitute the round robin queues with prio queues
    lines.append("tc qdisc del dev {} root".format(server_intf))
    lines.append("tc qdisc add dev {} root handle 1: prio bands {}".format(server_intf, num_queues + 1))

    # OpenFlow rules
    lines.append(add_flow(match=dict(eth_type='0x0806'), actions=['flood'], priority=1000))
    for client_intf, source_ips in client_intf_to_source_ips.items():
        for source_ip in source_ips:
            # sink -> source
            lines.append(add_flow(match=dict(eth_type='0x0800', ip_dst=source_ip),
                                  actions=['output:%s' % intf_to_port_num[client_intf]], priority=100))
    # source -> sink (marked)
    for dscp in range(1, num_bands + 1):  # i=1-->8
        lines.append(add_flow(match=dict(eth_type='0x0800', ip_dst=server_ip, ip_dscp=dscp),
                              actions=['enqueue:%s:%s' % (intf_to_port_num[server_intf], dscp)], priority=200))
    lines.append(add_flow(match=dict(eth_type='0x0800', ip_dst=server_ip),
                          actions=['enqueue:%s:%s' % (intf_to_port_num[server_intf], 1)], priority=150))

    lines.append('ovs-ofctl --color -m dump-flows brUG')
    lines.extend(['tc qdisc show dev %s' % intf for intf in all_intfs])

    return lines


def add_flow(match=None, actions=None, priority=None):
    elems = ['table=0']
    if priority:
        elems.append('priority=%s' % priority)
    if match:
        elems.extend(['%s=%s' % (k, v) for k, v in match.items()])
    if actions:
        elems.append('actions=' + ','.join(actions))
    return "ovs-ofctl -O openflow13 add-flow brUG {}".format(','.join(elems))
