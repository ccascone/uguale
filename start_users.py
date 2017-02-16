#!/usr/bin/python
"""
Script executed by each "client" PC.
Applies the netem-marking settings and starts
ipert TCP connections at a certain instant.
"""
import getopt
import sys
import time

import netem_and_marker as nm
from mylib import *


def run_program(
        duration, start_ts,
        fixed_conns, fixed_rtts, vr_limit, marking,
        bn_cap, g_rates, m_m_rates, e_f_rates, num_bands, do_symm):
    killall("iperf")
    n_users = len(g_rates)

    # ------- obsolete params-----
    intf = "eth0"
    veth_queuelen = 0
    tech = TECH_OVS
    # ----------------------------

    # Apply meter and markers and netem on veths
    nm.veth_netem_marker(
        intf, bn_cap, fixed_rtts, vr_limit,
        veth_queuelen, g_rates, m_m_rates, marking,
        tech, num_bands, do_symm, e_f_rates)

    # Sleep until start_ts
    sleep_time = start_ts - time.time()
    if sleep_time > 0:
        print "Netem and markers configuration done, sleep for {}".format(sleep_time)
        time.sleep(sleep_time)

    # Start iperf connections
    for user in range(n_users):
        dest_port = FIRST_TCP_PORT + user
        num_conn = fixed_conns[user]
        iperf_str = "iperf -c{} -P{} -t{} -p{}".format(SERVER_IP, num_conn, duration + 5, dest_port)
        launch_bg(iperf_str)


def main(argv):
    start_ts = 0
    help_string = "TRANSMISSION:\n\
	-d<duration> -t<starting timestamp>\n\
	USERS CONFIGURATION:\n\
	-P<TCP connections:L> -T<RTTs:L> \n\
	-C<veth rate limit>   -m<marking type>\n\
	BANDS ASSIGNMENT:\n\
 	-b<bottleneck-capacity>\n\
 	-G<guaranteed-rates:L> -M<MMRs:L> -E<EFRs:L>\n\
	-Q<num bands> -K<do_symm>"

    try:
        opts, args = getopt.getopt(argv, "hd:t:P:T:C:m:b:G:M:E:Q:K:")
    except getopt.GetoptError:
        print help_string
        sys.exit(2)

    for opt, arg in opts:
        if opt == '-h':
            print help_string
            sys.exit()

        elif opt in ("-d"):
            duration = int(arg)
        elif opt in ("-S"):
            start_ts = float(arg)

        elif opt in ("-P"):
            fixed_conns = map(int, arg.split(","))
        elif opt in ("-T"):
            fixed_rtts = map(float, arg.split(","))
        elif opt in ("-C"):
            vr_limit = rate_to_int(arg)
        elif opt in ("-m"):
            marking = arg

        elif opt in ("-b"):
            bn_cap = rate_to_int(arg)
        elif opt in ("-G"):
            g_rates = map(rate_to_int, arg.split(","))
        elif opt in ("-M"):
            m_m_rates = map(rate_to_int, arg.split(","))
        elif opt in ("-E"):
            e_f_rates = map(rate_to_int, arg.split(","))
        elif opt in ("-Q"):
            num_bands = int(arg)
        elif opt in ("-K"):
            do_symm = my_bool(arg)

    run_program(
        duration, start_ts,
        fixed_conns, fixed_rtts, vr_limit, marking,
        bn_cap, g_rates, m_m_rates, e_f_rates, num_bands, do_symm)


if __name__ == "__main__":
    main(sys.argv[1:])
