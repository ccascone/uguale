#!/usr/bin/python
"""
iptables functions
"""
from cmdlib import cmd


def flush_iptables():
    """
    Delete all rules
    """
    return "# flush iptables\niptables -F && iptables -F -t mangle && iptables -F -t nat"


def print_iptables():
    """
    Print all rules
    """
    cmd("iptables -nL")
    cmd("iptables -nL -t mangle")
    cmd("iptables -nL -t nat")


def masquerade(intf):
    return "iptables -t nat -A POSTROUTING -o {} -j MASQUERADE".format(intf)


def classify_and_accept(est_name, dest_ip, qdisc_id, class_id, rate=-1):
    """
    Classify and accept packets over the threshold rate with a certain dport.
    If no threshold is passed, match only the dport
    """
    if rate > 0:
        match_on_rate = "-m rateest --rateest {} --rateest-gt --rateest-bps {} ".format(est_name, rate)
    else:
        match_on_rate = ""

    command1 = "iptables -A OUTPUT -d {} {} -j CLASSIFY --set-class {}:{}" \
        .format(dest_ip, match_on_rate, qdisc_id, class_id)

    command2 = "iptables -A OUTPUT -d {} {} -j ACCEPT" \
        .format(dest_ip, match_on_rate)

    return [command1, command2]


def mark_port_based(protocol, dest_port, dest_intf_id):
    """
    FW mark packets based on the destination port
    (this allows packets to be routed with different routing tables)
    """
    return "iptables -t mangle -A OUTPUT -p {} --dport {} -j MARK --set-mark {}".format(protocol, dest_port,
                                                                                        dest_intf_id)


"""
Send all packets for a certain dport to a dedicated estimator.
NB. The minimum interval applied is 250ms
"""


def send_to_estimator(est_name, protocol, dest_port, interval):
    return "iptables -A OUTPUT -p {} -m {} --dport {} -j RATEEST --rateest-name {} --rateest-interval {}ms --rateest-ewmalog {}ms" \
        .format(protocol, protocol, dest_port, est_name, interval, interval * 2)
