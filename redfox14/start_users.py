#!/usr/bin/python

import sys, getopt, time, threading, os
from mylib import *
import netem_and_marker as marker

"""
program executed on each host PC.
Apply settings and start connectios
"""

def run_program(pc_ip, intf, g_rates, bn_cap, fixed_conns,
				fixed_rtts, vr_limit, duration,
				marking, m_m_rates,queuelen, tech, start_ts, 
				num_colors, symmetric, e_f_rates):

	
	killall("iperf") 
	#-------------------- Apply meter and markers and netem on veths --------------------------
	n_users = len(g_rates)
	print "{}: Configuring veths and markers".format(pc_ip)
	marker.veth_netem_marker(intf, bn_cap, fixed_rtts, vr_limit, 
		queuelen, g_rates, m_m_rates, marking, tech, num_colors, symmetric, e_f_rates)
	
	"""
	Sleep
	"""	
	sleep_time = start_ts - time.time() 
	print "End configuration, sleep for {}".format(sleep_time)
	if sleep_time > 0:
		time.sleep(sleep_time)
	"""
	Start iperf connections
	"""	
	for user in range(n_users):
		dest_port = FIRST_TCP_PORT + user
		num_conn = fixed_conns[user]
		iperf_str = "iperf -c{} -P{} -t{} -p{}".format(SERVER_IP, num_conn, duration+5, dest_port)
		print "{}: {},{} --> {}".format(time.time() - start_ts,pc_ip,user,iperf_str)
		launch_bg(iperf_str)

# def run_program(pc_ip, intf, g_rates, bn_cap, fixed_conns,
# 				fixed_rtts, vr_limit, duration,
# 				marking, m_m_rates,queuelen, tech, start_ts=0):


# 	#print pc_ip,intf,g_rates, bn_cap, fixed_conns, fixed_rtts, vr_limit, duration, marking, m_m_rates, queuelen, tech, do_use_netem
	
# 	#-------------------- Clean any previous mess --------------------------
# 	killall("iperf") 
# 	sudo_cmd("sysctl -w net.ipv4.tcp_no_metrics_save=1")  # instruct linux to forget previous tcp sessions
# 	#-------------------- Apply meter and markers and netem on veths --------------------------
# 	n_users = len(g_rates)
# 	marker.veth_netem_marker(intf, bn_cap, fixed_rtts, vr_limit, queuelen, g_rates, m_m_rates, marking, tech)
# 	"""
# 	Start iperf connections
# 	"""		
# 	iperf_str = ""
# 	for user in range(n_users):
# 		# print "{}, user {} tries to connect to the server".format(pc_ip, user+1)
# 		dest_port = FIRST_TCP_PORT + user
# 		num_conn = fixed_conns[user]
# 		iperf_str = "(sleep {}; iperf -c{} -P{} -t{} -p{}) & ".format(start_ts - time.time(),SERVER_IP, num_conn, duration, dest_port)
# 		print iperf_str
# 		cmd(iperf_str)



# def run_program(pc_ip, intf, g_rates, bn_cap, fixed_conns,
# 				fixed_rtts, vr_limit, duration,
# 				marking, m_m_rates,queuelen, tech, start_ts=0):


# 	#print pc_ip,intf,g_rates, bn_cap, fixed_conns, fixed_rtts, vr_limit, duration, marking, m_m_rates, queuelen, tech, do_use_netem
	
# 	#-------------------- Clean any previous mess --------------------------
# 	killall("iperf") 
# 	sudo_cmd("sysctl -w net.ipv4.tcp_no_metrics_save=1")  # instruct linux to forget previous tcp sessions
# 	#-------------------- Apply meter and markers and netem on veths --------------------------
# 	n_users = len(g_rates)
# 	marker.veth_netem_marker(intf, bn_cap, fixed_rtts, vr_limit, queuelen, g_rates, m_m_rates, marking, tech)
# 	"""
# 	Start iperf connections
# 	"""	
# 	iperf_str = ""
# 	for user in range(n_users):
# 		dest_port = FIRST_TCP_PORT + user
# 		num_conn = fixed_conns[user]
# 		iperf_str = "iperf -c{} -P{} -t{} -p{}".format(SERVER_IP, num_conn, duration, dest_port)
# 		threading.Thread(target=iperf_thread, args=(iperf_str,start_ts)).start()


# def iperf_thread(iperf_str, start_ts):
# 	time.sleep(start_ts-time.time())
# 	cmd(iperf_str)

# def iperf_thread2(iperf_str, start_ts):
# 	cmd("sleep {}; {}".format(start_ts-time.time(),iperf_str))
	
	
def main(argv):
	intf = "eth0"
	start_ts = 0
	
	help_string = "Usage: -s <pc-ip> -i <interface> -g <guaranteed-rates> -C <bottleneck-capacity> \n\
	-P <tcp-connections>  -f <rtt-list> \n\
	-l <veth-rate-limit> -d<duration> -m<marking> -M<max-marking-rates>\n\
	-q<queuelen per user> -t <more-users-technology> -S<starting timestamp>\n\
	-K <symmetric> -E<expected fair rates>\n\
	g: list of grates\n\
	P: list of number of tcp connections \n\
	f: list of rtts\n\
	m:  type o markers"

	try:
		opts, args = getopt.getopt(argv,"hs:i:g:C:P:f:l:d:m:M:q:t:S:Q:K:E:")
	except getopt.GetoptError:
		print help_string
		sys.exit(2)

	for opt, arg in opts:
		if opt == '-h':
			print help_string
			sys.exit()
		elif opt in ("-s"):
			pc_ip = arg
		elif opt in ("-i"):
			intf = arg
		elif opt in ("-g"):
			g_rates = map(rate_to_int, arg.split(","))
		elif opt in ("-C"):
			bn_cap = rate_to_int(arg)
		elif opt in ("-P"):
			fixed_conns = map(int,arg.split(","))
		elif opt in ("-f"):
			fixed_rtts = map(float,arg.split(","))
		elif opt in ("-l"):
			vr_limit = rate_to_int(arg)
		elif opt in ("-d"):
			duration = int(arg)  
		elif opt in ("-m"):
			marking = arg
		elif opt in ("-M"):
			m_m_rates = map(rate_to_int, arg.split(","))
		elif opt in ("-q"):
			queuelen = int(arg)
		elif opt in ("-t"):
			tech = arg
		elif opt in ("-S"):
			start_ts = float(arg)
		elif opt in ("-Q"):
			num_colors = int(arg)
		elif opt in ("-K"):
			symmetric = my_bool(arg)
		elif opt in ("-E"):
			e_f_rates = map(rate_to_int, arg.split(","))


	#print starting_ip, intf, g_rates, bn_cap, policy, fixed_conns, range_rtts, curving, fixed_rtts, vr_limit, duration

	run_program(pc_ip, intf, g_rates, bn_cap, fixed_conns,
				fixed_rtts, vr_limit, duration,
				marking, m_m_rates,queuelen, tech,start_ts, 
				num_colors, symmetric, e_f_rates)

if __name__ == "__main__":
   main(sys.argv[1:])
