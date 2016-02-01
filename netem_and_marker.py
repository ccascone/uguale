#!/usr/bin/python

from mylib import *
from tc_lib import *
from iptables_lib import *
from marking_lib import *
#import threading
#stop = threading.Event()


#------------------------------------- METER/MARKER WITH BUCKETS -------------------------------------#

"""
All packets that pass through the dsmark will
be classified by token bucket filters (no ports lookup)
"""
def add_dsmark_filters(intf, dsmark_qdisc_id, rates, user, num_colors, dest_port_tcp=0, veth_id=0,):
	"""
	------------- <---4000
	|			|
	|	3		|
	------------- <---2000
	|	2		|
	------------- <---1000
	|	1		|
	-------------

	rates={
		1000 : 1
		2000 : 2
		4000 : 3
	}

	=====> 	consume 1000, if ok 1 else
			consume 1000, if ok 2 else
			3
	"""
	cumulative_rate = 0	

	"""
	user1: prio 1 2 3 4 5 6 7 8
	user2: prio 9 10 11...
	"""
	user_base_prio = (user-1)*num_colors

	for rate in sorted(rates): # i=1-->8
		dscp = rates[rate]
		prio = user_base_prio + dscp
		"""
		The default class is the fighest DSCP.
		For all the others we need a filter to direct to classes
		"""
		if dscp<max_dscp(rates):
			width = rate-cumulative_rate
			cumulative_rate += width
			burst = int(width/float(HZ))
			mtu = 2*MAX_PACKET_SIZE
			add_dsmark_filter(intf, dsmark_qdisc_id, prio, width, burst, mtu, dscp, protocol="tcp", dport=dest_port_tcp)	
			# add_dsmark_filter(intf, dsmark_qdisc_id, prio, width, burst, mtu, dscp, fw=veth_id)	
		else:
			add_dsmark_filter(intf, dsmark_qdisc_id, prio, 0,0,0, dscp, protocol="tcp", dport=dest_port_tcp)	
			# add_dsmark_filter(intf, dsmark_qdisc_id, prio, 0,0,0, dscp, fw=veth_id)	

#------------------------------------- METER/MARKER WITH IPTABLES -------------------------------------#
"""
iptables will call the classify action that will send
packets to dsmark classes.
dsmark qdisc must be attached to eth0 root
"""
def iptables_meter_marker(rates, dest_port_tcp, interval, dsmark_qdisc_id):
	est_name = "EST{}".format(dest_port_tcp)
	"""
	All packets of the connection will be first 
	sent to an estimator named as the port
	"""
	ipt_send_to_estimator(est_name,"tcp", dest_port_tcp, interval)
	#ipt_send_to_estimator(est_name,"udp", dest_port_udp, interval)
	"""
	------------- <---4000
	|			|
	|	3		|
	------------- <---2000
	|	2		|
	------------- <---1000
	|	1		|
	-------------

	rates={
		1000 : 1
		2000 : 2
		4000 : 3
	}

	=====> 	rate >2000 : 3
			rate >1000 : 2
			other: 1
	"""

	my_rates = dict(rates) 
	del my_rates[max(my_rates)] # Remove the highest rate
	my_rates[0] = 0
	for rate in reversed(sorted(my_rates)):
		dscp = my_rates[rate]+1
		if rate != min(my_rates):			
			ipt_classify_and_accept(est_name, "tcp", dest_port_tcp, dsmark_qdisc_id, dscp, rate)
		else:
			ipt_classify_and_accept(est_name, "tcp", dest_port_tcp, dsmark_qdisc_id, dscp)



def veth_netem_marker(intf, bn_cap, fixed_rtts, vr_limit, queuelen, g_rates, m_m_rates, 
	marking, tech, num_colors, symmetric, e_f_rates):
	clean_interface_tc(intf)		
	flush_iptables()

	n_users = len(g_rates)

	"""
	Configure the physical interfce
	"""	
	if queuelen>0:
		set_queuelen(intf, queuelen*n_users)
		add_pfifo_qdisc(intf, "root", 1)
	else:
		set_queuelen(intf, 1000) # default value

	"""
	DSMARK
	"""
	dsmark_qdisc_id = 1
	if marking != NO_MARKERS:
		add_dsmark_qdisc(intf, "root", dsmark_qdisc_id, 64, num_colors)
		for dscp in range(1,num_colors+1): # i=1-->8
			change_dsmark_class(intf, dsmark_qdisc_id, dscp, dscp)

	# Set iptables and netem
	for i in range(n_users):
		
		"""
		user-specific IDs
		"""
		user = i+1
		dest_port_tcp = FIRST_TCP_PORT + i
		# dest_port_udp = FIRST_UDP_PORT + i
		netem_qdisc_id = user + 2
		veth_id = user
		veth_intf = "veth{}".format(veth_id)
		if_delay = fixed_rtts[i]

		if tech != TECH_NONE:
			"""
			Packets will be sent on interface based on destination port
			"""
			ipt_mark_port_based("tcp", dest_port_tcp, veth_id)


		if marking != NO_MARKERS:
			"""
			Calculate user parameters
			"""		
			rates = get_rates(g_rates[i], bn_cap, m_m_rates[i],num_colors, symmetric, e_f_rates[i])
			print_rates(rates, bn_cap)
			if marking == IPTABLES_MARKERS:
				# put all measuring and classifying rules for the user
				iptables_meter_marker(rates, dest_port_tcp, if_delay, dsmark_qdisc_id)
			elif marking == BUCKETS_MARKERS:
				#put filters for the interface
				add_dsmark_filters(intf, dsmark_qdisc_id, rates, user, num_colors, dest_port_tcp = dest_port_tcp)
		
		"""
		qdiscs
		"""
		clean_interface_tc(veth_intf)
		set_queuelen(veth_intf, queuelen)

		if tech != TECH_NONE:

			"""
			NetEm
			"""
			if if_delay>1:
				add_netem_qdisc(veth_intf, "root", netem_qdisc_id, vr_limit, if_delay, queuelen)
			else:
				if queuelen>0: # otherwise it creates a fifo of 1 packet!
					add_pfifo_qdisc(veth_intf,"root",netem_qdisc_id)
			"""
			Alter the source IP of packets
			"""
			ipt_masquerade(veth_intf)	
		



# #------------------------------------- METER/MARKER WITH PYTHON -------------------------------------#

# def find_band(rate,rates, num_rates):
# 	for i in range(num_rates): #0,1,2
# 		if rates[i]<=rate<rates[i+1]:
# 			return i+1
# 	return num_rates


# def active_marker_thread(intf, dsmark_qdisc_id, rates, if_delay):
# 	# Read the bitrate every delay and change marking
# 	delay = (if_delay/1000.0)*1.1

# 	min_time = 0.003 # minimum time needed by the system to do a cycle (without sleep)

# 	# Prepare the list of rates
# 	num_rates = len(rates)
# 	r = rates_to_list_bytes(rates)
# 	cmd = "tc -s qdisc show dev {}".format(intf)
# 	#reg = re.compile(".*Sent (.*) bytes.*")

# 	old_t = time.time()
# 	old_bytes = 0
# 	old_band = -1
# 	old_rate = 0
# 	min_diff = 0#int((r[-1]-r[-2])/10)
# 	print rates, r

# 	"""
# 	qdisc mq 0: root 
# 	 Sent 12775504 bytes 167278 pkt (dropped 0, overlimits 0 requeues 2) 
# 	 backlog 0b 0p requeues 2 
# 	qdisc pfifo_fast 0: parent :1 bands 3 priomap  1 2 2 2 1 2 0 0 1 1 1 1 1 1 1 1
# 	 Sent 12775504 bytes 167278 pkt (dropped 0, overlimits 0 requeues 2) 
# 	 backlog 0b 0p requeues 2 

# 	"""
# 	while not stop.is_set():

# 		"""
# 		Sleep only if necessary and by the amount remaining
# 		"""
# 		small_delta_t = time.time() - old_t
# 		if (small_delta_t + min_time) < delay:
# 			time.sleep(delay - (small_delta_t+min_time))

# 		line = os.popen(cmd).read().strip().split("\n")[1]
# 		new_t = time.time()
# 		new_bytes = int(line.split(" ")[2])
	
# 		delta_bytes = new_bytes - old_bytes
# 		delta_t = new_t - old_t
# 		new_rate = int(delta_bytes/delta_t)	
# 		#print "Delta {}ms, rate {}".format(int(delta_t*1000),num_to_rate_int(new_rate*8))		

# 		if abs(new_rate-old_rate)>min_diff:
# 			new_band = find_band(new_rate, r, num_rates)
# 			if new_band!=old_band:
# 				change_dsmark_class(intf, dsmark_qdisc_id, 1, new_band)
# 				old_band = new_band
# 				old_rate = new_rate
# 		old_bytes = new_bytes
# 		old_t = new_t
			




		
# def run_program_python(intf, g_rates, bn_cap, policy, range_rtts, curving, fixed_rtts, lr_limit, pc_ip, marker_max_rate):
# 	n_users = len(g_rates)
# 	clean_interface_tc(intf)		
# 	flush_iptables()
# 	stop.clear()
# 	threads={}

# 	for i in range(n_users):		
# 		"""
# 		Calculate user-specific IDs
# 		"""
# 		user = i+1
# 		dest_port_tcp = FIRST_TCP_PORT + i
# 		dest_port_udp = FIRST_UDP_PORT + i
# 		dsmark_qdisc_id = 1
# 		netem_qdisc_id = 2
# 		veth_id = user
# 		veth_intf = "veth{}".format(veth_id)

# 		if_delay = get_if_delay(range_rtts, fixed_rtts, i)

# 		"""
# 		Calculate user parameters
# 		"""		
# 		rates = get_rates(g_rates[i], bn_cap, policy, range_rtts, curving, if_delay, marker_max_rate)
# 		print_rates(rates, bn_cap)		

# 		"""
# 		Packets will be sent on interface based on destination port
# 		"""
# 		ipt_mark_port_based("tcp", dest_port_tcp, veth_id)
		
# 		"""
# 		Attach a netem to root of the veth
# 		"""
# 		clean_interface_tc(veth_intf)	
# 		sudo_cmd("ifconfig {} txqueuelen {}".format(veth_intf, QUEUELEN))	

# 		# DSMARK ON TOP
# 		add_dsmark_qdisc(veth_intf, "root",dsmark_qdisc_id, 2, 1)
# 		change_dsmark_class(veth_intf, dsmark_qdisc_id, 1, 1)
# 		add_netem_qdisc(veth_intf, dsmark_qdisc_id, netem_qdisc_id, lr_limit, if_delay)
		
# 		# # NETEM ON TOP
# 		# add_netem_qdisc(veth_intf, "root", netem_qdisc_id, lr_limit, if_delay)	
# 		# add_dsmark_qdisc(veth_intf, netem_qdisc_id, dsmark_qdisc_id, 2, 1)
# 		# change_dsmark_class(veth_intf, dsmark_qdisc_id, 1, 1)

# 		"""
# 		Alter the source IP of packets
# 		"""
# 		ipt_masquerade(veth_intf)

# 		"""
# 		Prepare the thread
# 		"""
# 		threads[veth_intf] = threading.Thread(target=active_marker_thread, args=(veth_intf, dsmark_qdisc_id, rates, if_delay))
# 		threads[veth_intf].start()


