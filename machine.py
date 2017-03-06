from cmdlib import killall_str
from misc import hnum
from uconf import BN_BITRATE, SUBNET_PREFIX_LEN

NO_MARKERS = "no_markers"
BUCKETS_MARKERS = "buckets_markers"
IPTABLES_MARKERS = "iptables_markers"

veth_counter = dict()


def reset_gloabals():
    global veth_counter
    veth_counter = dict()


def clean_up(intfs):
    lines = []

    br_names = ['brUG' + intf for intf in intfs]

    lines.append("# Cleanup routine")
    lines.append(killall_str("iperf"))
    lines.append("ip netns list | xargs -L1 ip netns del")
    lines.extend(["ovs-vsctl del-br %s" % br_name for br_name in br_names])
    lines.extend(["tc qdisc del dev %s root" % intf for intf in intfs])
    lines.append("iptables -F && iptables -F -t mangle && iptables -F -t nat")
    lines.append("sysctl -w net.ipv4.tcp_no_metrics_save=1")
    lines.append("")
    lines.append("")

    return lines


def fwchain(source_confs, server_ip, client_intf, client_id, queuelen=1000, marking_type=IPTABLES_MARKERS):
    ratess = [c['marking_rates'] for c in source_confs]
    n_users = len(ratess)
    rtts = [c['rtt'] for c in source_confs]
    veth_ips = [c['source_ip'] for c in source_confs]
    br_name = 'brUG%s' % client_intf

    global veth_counter
    if client_id not in veth_counter:
        veth_counter[client_id] = 1

    assert len(rtts) == n_users, 'A RTT should be given for each user'

    sum_band_set = set([len(rates) for rates in ratess])
    assert len(sum_band_set) == 1, 'All user should be assigned with the same number of rates'
    num_bands = sum_band_set.pop() + 1

    lines = []

    # Create bridge and veth

    lines.append("##")
    lines.append("## SOURCE GROUP %s->%s, %s sources" % (client_id, client_intf, n_users))
    lines.append("##\n")

    lines.append("set -e # exit on errors")
    lines.append("")

    lines.append("# Create OVS bridge %s" % br_name)
    lines.append("ovs-vsctl add-br %s" % br_name)
    lines.append("ovs-vsctl set-fail-mode %s standalone" % br_name)
    # lines.append("ifconfig %s %s up" % (br_name, client_ip))
    lines.append("ifconfig %s up" % br_name)
    lines.append("ovs-vsctl add-port %s %s" % (br_name, client_intf))
    lines.append("ifconfig %s 0.0.0.0 up" % client_intf)

    veth_intfs = []

    lines.append(set_queuelen(client_intf, queuelen * n_users))

    # Create veths
    for i in range(len(veth_ips)):
        veth_id = veth_counter[client_id]
        veth_counter[client_id] += 1
        veth_ip = veth_ips[i]
        veth_intf = "veth{}".format(veth_id)
        ns_name = 'ns{}'.format(veth_id)
        veth_intfs.append(veth_intf)
        lines.append("")
        lines.append("# Configure %s (%s)" % (ns_name, veth_ip))
        lines.append(
            "ovs-vsctl add-port {} {} -- set interface {} type=internal".format(br_name, veth_intf, veth_intf))
        lines.append("ifconfig {} 0.0.0.0 up".format(veth_intf))

        # create netns
        lines.append('ip netns add %s' % ns_name)
        lines.append('ip link set dev %s netns %s' % (veth_intf, ns_name))

        ns_lines = []

        rates = ratess[i]
        if_delay = rtts[i]
        est_period_ms = max(250, if_delay)

        ns_lines.append('ifconfig %s %s/%s up' % (veth_intf, veth_ip, SUBNET_PREFIX_LEN))
        ns_lines.append(set_queuelen(veth_intf, queuelen))

        ns_lines.append("# RTT: %sms" % if_delay)
        netem_qdisc_id = 1
        dsmark_qdisc_id = netem_qdisc_id + 1
        if if_delay <= 0:
            if_delay = 1
        ns_lines.append(tc_add_netem_qdisc(veth_intf, "root", netem_qdisc_id, BN_BITRATE, if_delay, queuelen))
        # ns_lines.append("tc qdisc add dev {} {} handle {}: pfifo".format(veth_intf, 'root', netem_qdisc_id))

        ns_lines.append("# DSCP marker")
        if marking_type != NO_MARKERS:
            ns_lines.append("tc qdisc add dev {} parent {} handle {}: dsmark indices {} default {}".format(
                veth_intf, '%s:1' % netem_qdisc_id, dsmark_qdisc_id, 64, num_bands))
            for dscp in range(1, num_bands + 1):  # i=1-->8
                ns_lines.append("tc class change dev {} parent {}: classid {}:{} dsmark mask 0xff value {}".format(
                    veth_intf, dsmark_qdisc_id, dsmark_qdisc_id, dscp, hex(dscp << 2)))
            ns_lines.append("# Rate bands: %s [bit/s]" % ', '.join([hnum(r) for r in rates]))
        if marking_type == IPTABLES_MARKERS:
            ns_lines.extend(ipt_meter_marker(rates, server_ip, est_period_ms, dsmark_qdisc_id))
        elif marking_type == BUCKETS_MARKERS:
            raise Exception('BUCKETS_MARKERS not implemented')
        ns_lines.append("iptables -t nat -A POSTROUTING -o {} -j MASQUERADE".format(veth_intf))

        lines.extend([(ns(ns_name) + n if n[0] != '#' else n) for n in ns_lines])
        lines.append("")

    lines.append("")

    return lines


def iperf_clients(source_confs, server_ip, duration):
    lines = []
    num_conns = [c['num_conn'] for c in source_confs]
    ratess = [c['marking_rates'] for c in source_confs]
    n_users = len(ratess)
    for u in range(n_users):
        num_conn = num_conns[u]
        lines.append(
            ns('ns%s' % (u + 1)) +
            "iperf -c{} -P{} -t{} -p{} > /tmp/iperf.{}.log &".format(server_ip, num_conn, duration, 5001, u + 1))
    lines.append("wait")
    lines.append("echo DONE!")
    return lines


def pingers(source_confs, server_ip, count=1):
    lines = ['set -e']
    for u in range(len(source_confs)):
        lines.append(ns('ns%s' % (u + 1)) + "ping -qn -c%s %s" % (count, server_ip))
    return lines


est_count = 0


def ipt_meter_marker(rates, dest_ip, interval, dsmark_qdisc_id):
    lines = []
    global est_count
    est_count += 1
    est_name = "EST{}".format(est_count)
    """
    All packets of the connection will be first
    sent to an estimator named as the port
    """
    lines.append(
        "iptables -A OUTPUT -d {} -j RATEEST --rateest-name {} --rateest-interval {}ms --rateest-ewmalog {}ms" \
            .format(dest_ip, est_name, interval, interval * 2))
    # send_to_estimator(est_name,"udp", dest_port_udp, interval)

    my_rates = [0] + sorted(rates)
    for i in reversed(range(len(my_rates))):
        dscp = i + 1
        if my_rates[i] != min(my_rates):
            lines.extend(ipt_classify_and_accept(est_name, dest_ip, dsmark_qdisc_id, dscp, my_rates[i]))
        else:
            lines.extend(ipt_classify_and_accept(est_name, dest_ip, dsmark_qdisc_id, dscp))

    return lines


def ipt_classify_and_accept(est_name, dest_ip, qdisc_id, class_id, rate=-1):
    """
    Classify and accept packets over the threshold rate with a certain dport.
    If no threshold is passed, match only the dport
    """
    match_on_rate = ""
    if rate > 0:
        match_on_rate = "-m rateest --rateest {} --rateest-gt --rateest-bps {} ".format(est_name, int(rate))

    command1 = "iptables -A OUTPUT -d {} {} -j CLASSIFY --set-class {}:{}".format(dest_ip, match_on_rate, qdisc_id,
                                                                                  class_id)
    command2 = "iptables -A OUTPUT -d {} {} -j ACCEPT".format(dest_ip, match_on_rate)

    return [command1, command2]


def tc_add_netem_qdisc(intf, parent_id, netem_qdisc_id, rate=0, delay=0, limit=0):
    if rate == 0 and delay == 0:
        print "NetEm called without limiting parameters"
        return

    my_rate, my_delay, my_limit = "", "", ""

    if rate > 0:
        my_rate = "rate {}".format(rate)

    if delay > 0:
        my_delay = "delay {}ms".format(delay)

    if limit > 0:
        my_limit = "limit {}".format(limit)

    command = "tc qdisc add dev {} {} handle {}: netem {} {} {}".format(
        intf, parent_id, netem_qdisc_id, my_delay, my_rate, my_limit)

    return command


def gen_server_script(server_ip, intf):
    lines = []

    ns_name = 'ns-sink'
    br_name = 'brUG' + intf
    veth_intf = 'veth-sink'

    lines.append('##\n## SINK CONFIGURATION (%s - %s)\n##\n' % (intf, server_ip))
    lines.append('# Configure netns %s' % ns_name)
    lines.append('set -e # exit on errors')
    lines.append('ovs-vsctl add-br %s' % br_name)
    lines.append("ovs-vsctl set-fail-mode %s standalone" % br_name)
    # lines.append("ifconfig %s %s up" % (br_name, client_ip))
    lines.append("ifconfig %s up" % br_name)
    lines.append("ovs-vsctl add-port %s %s" % (br_name, intf))
    lines.append("ifconfig %s 0.0.0.0 up" % intf)
    lines.append("ovs-vsctl add-port {} {} -- set interface {} type=internal".format(br_name, veth_intf, veth_intf))
    lines.append("ifconfig {} 0.0.0.0 up".format(veth_intf))
    lines.append('ip netns add %s' % ns_name)
    lines.append('ip link set dev %s netns %s' % (veth_intf, ns_name))
    lines.append(ns(ns_name) + 'ifconfig %s up %s/%s' % (veth_intf, server_ip, SUBNET_PREFIX_LEN))

    return lines


def set_queuelen(intf, length):
    return "ifconfig {} txqueuelen {}".format(intf, int(length))


def ns(id):
    return 'ip netns exec %s ' % id
