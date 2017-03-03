import machine
import switch
from uconf import SWITCH, SUBNET, CLIENTS, SERVER, BN_BITRATE


def gen_scripts(source_confs, sw_type=switch.SW_TYPE_1FIFO, sw_queuelen=1000):
    num_rates_set = set([len(c['marking_rates']) for c in source_confs])
    assert len(num_rates_set) == 1, 'All users must have the same number of marking rates'

    sw_num_bands = num_rates_set.pop() + 1
    assert len(source_confs) % len(CLIENTS) == 0, 'The number of sources must be multiple of the number of clients'

    source_per_client = len(source_confs) / len(CLIENTS)
    assert source_per_client < 100, 'A maximum of 100 sources per client is allowed'

    sw_of_server_port_no = len(SWITCH['intfs'])
    server_ip = SUBNET + str(sw_of_server_port_no)
    client_ips = [SUBNET + str(i) for i in range(1, len(SWITCH['intfs']))]
    assert len(client_ips) < 10

    source_ips = dict()
    source_ip_counter = 11

    for i in range(len(CLIENTS) * source_per_client):
        client_idx = i / source_per_client
        client = CLIENTS[client_idx]
        if client not in source_ips:
            source_ips[client] = []
        source_ips[client].append(SUBNET + str(i + source_ip_counter))

    # Start switch
    sw_server_intf = SWITCH['bn_intf']
    sw_client_intfs = [i for i in SWITCH['intfs'] if i != sw_server_intf]
    client_intf_to_source_ips = {c['sw_intf']: source_ips[c] for c in CLIENTS}
    ovs_script = switch.gen_script(sw_type=sw_type, queuelen=sw_queuelen, num_queues=sw_num_bands,
                                   client_intfs=sw_client_intfs, server_intf=sw_server_intf, server_ip=server_ip,
                                   client_intf_to_source_ips=client_intf_to_source_ips, num_bands=sw_num_bands)

    with open('gen/conf-switch.sh', 'w') as f:
        f.write('#!/usr/bin/env bash\n')
        f.write('# Switch script\n')
        f.write("\n".join(ovs_script))

    # with open('gen/testbed.sh', 'w') as f:
    #     print >> f, '#!/usr/bin/env bash\n'
    #     print >> f, 'set -e'
    #     for i in range(len(client_ips) + 1):
    #         if i == len(client_ips):
    #             machine = SERVER
    #             ip_addr = server_ip
    #         else:
    #             machine = CLIENTS[i]
    #             ip_addr = client_ips[i]
    #         client_host = machine['ctrl_addr']
    #         client_intf = machine['intf']
    #         print >> f, 'ssh %s "ifconfig %s up %s"' % (client_host, client_intf, ip_addr)

    # Start clients
    client_chain_scripts = {client['ctrl_addr']: [] for client in CLIENTS}
    iperf_confs = {client['ctrl_addr']: [] for client in CLIENTS}
    client_to_intfs = {client['ctrl_addr']: [] for client in CLIENTS}

    for c in range(len(CLIENTS)):
        client = CLIENTS[c]
        client_ctrl_addr = client['ctrl_addr']
        client_intf = client['intf']

        client_to_intfs[client_ctrl_addr].append(client_intf)

        # Generate source conf for this client (add source_ip)
        client_source_confs = [dict(source_ip=ip, **source_confs.pop()) for ip in source_ips[client]]
        chain_script = machine.fwchain(source_confs=client_source_confs, server_ip=server_ip,
                                       client_intf=client_intf, client_id=client_ctrl_addr)
        client_chain_scripts[client_ctrl_addr].extend(chain_script)
        iperf_confs[client_ctrl_addr].extend(source_confs)

    for ctrl_addr, intfs in client_to_intfs.items():
        server_intfs = []
        server_script = None
        if ctrl_addr == SERVER['ctrl_addr']:
            server_intfs.append(SERVER['intf'])
            server_script = machine.gen_server_script(server_ip, SERVER['intf'])
        cleanup_script = machine.clean_up(intfs + server_intfs)
        with open('gen/conf-%s.sh' % ctrl_addr, 'w') as f:
            f.write('#!/usr/bin/env bash\n')
            f.write('\n'.join(cleanup_script))
            f.write('\n'.join(client_chain_scripts[ctrl_addr]))
            if server_script:
                f.write('\n'.join(server_script))

        iperf_script = machine.iperf_clients(iperf_confs=iperf_confs[ctrl_addr], server_ip=server_ip)
        with open('gen/start-trfc-%s.sh' % ctrl_addr, 'w') as f:
            f.write('#!/usr/bin/env bash\n')
            f.write('\n'.join(iperf_script))


if __name__ == '__main__':
    num_rates = 3
    rates = [i * BN_BITRATE / num_rates for i in range(1, num_rates)]
    defaults = dict(marking_rates=rates, rtt=40, num_conn=2)
    source_confs = [defaults for _ in range(len(CLIENTS) * 2)]
    gen_scripts(source_confs=source_confs, sw_type=switch.SW_TYPE_1FIFO)
