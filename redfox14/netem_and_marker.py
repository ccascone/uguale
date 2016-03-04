#!/usr/bin/python

from mylib import *
import tc_lib as tc
import iptables_lib as ipt
import marking_lib as ml

#-------------------- METER/MARKER WITH BUCKETS -----------------------#

"""
All packets that pass through the dsmark will
be classified by token bucket filters (no ports lookup)
"""
def add_dsmark_filters(intf, dsmark_qdisc_id, rates, user, num_bands, 
	dest_port_tcp=0, veth_id=0,):
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
	user_base_prio = (user-1)*num_bands

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
			tc.add_dsmark_filter(intf, dsmark_qdisc_id, prio, width, burst, mtu, dscp, protocol="tcp", dport=dest_port_tcp)	
			# add_dsmark_filter(intf, dsmark_qdisc_id, prio, width, burst, mtu, dscp, fw=veth_id)	
		else:
			tc.add_dsmark_filter(intf, dsmark_qdisc_id, prio, 0,0,0, dscp, protocol="tcp", dport=dest_port_tcp)	
			# add_dsmark_filter(intf, dsmark_qdisc_id, prio, 0,0,0, dscp, fw=veth_id)	

#------------------- METER/MARKER WITH IPTABLES -----------------------------#
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
	ipt.send_to_estimator(est_name,"tcp", dest_port_tcp, interval)
	#send_to_estimator(est_name,"udp", dest_port_udp, interval)
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
			ipt.classify_and_accept(est_name, "tcp", dest_port_tcp, dsmark_qdisc_id, dscp, rate)
		else:
			ipt.classify_and_accept(est_name, "tcp", dest_port_tcp, dsmark_qdisc_id, dscp)



def veth_netem_marker(intf, bn_cap, fixed_rtts, vr_limit, 
	queuelen, g_rates, m_m_rates, marking, 
	tech, num_bands, do_symm, e_f_rates):
	
	tc.clean_interface(intf)		
	ipt.flush_iptables()

	n_users = len(g_rates)

	"""
	Configure the physical interfce
	"""	
	if queuelen>0:
		set_queuelen(intf, queuelen*n_users)
		tc.add_pfifo_qdisc(intf, "root", 1)
	else:
		set_queuelen(intf, 1000) # default value

	"""
	DSMARK
	"""
	dsmark_qdisc_id = 1
	if marking != NO_MARKERS:
		tc.add_dsmark_qdisc(intf, "root", dsmark_qdisc_id, 64, num_bands)
		for dscp in range(1,num_bands+1): # i=1-->8
			tc.change_dsmark_class(intf, dsmark_qdisc_id, dscp, dscp)

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
			ipt.mark_port_based("tcp", dest_port_tcp, veth_id)


		if marking != NO_MARKERS:
			"""
			Calculate user parameters
			"""		
			rates = ml.get_rates(g_rates[i], bn_cap, m_m_rates[i],num_bands, do_symm, e_f_rates[i])
			ml.print_rates(rates, bn_cap)
			if marking == IPTABLES_MARKERS:
				# put all measuring and classifying rules for the user
				iptables_meter_marker(rates, dest_port_tcp, if_delay, dsmark_qdisc_id)
			elif marking == BUCKETS_MARKERS:
				#put filters for the interface
				add_dsmark_filters(intf, dsmark_qdisc_id, rates, user, num_bands, dest_port_tcp = dest_port_tcp)
		
		"""
		qdiscs
		"""
		tc.clean_interface(veth_intf)
		set_queuelen(veth_intf, queuelen)

		if tech != TECH_NONE:

			"""
			NetEm
			"""
			if if_delay>1:
				tc.add_netem_qdisc(veth_intf, "root", netem_qdisc_id, vr_limit, if_delay, queuelen)
			else:
				if queuelen>0: # otherwise it creates a fifo of 1 packet!
					tc.add_pfifo_qdisc(veth_intf,"root",netem_qdisc_id)
			"""
			Alter the source IP of packets
			"""
			ipt.masquerade(veth_intf)	