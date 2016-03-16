#!/usr/bin/python
"""
Applies a netem qdisc to an interface.
If necessary, adds markers (token buckets or iptables)
to virtual interfaces.
"""
from mylib import *
import tc_lib as tc
import iptables_lib as ipt
import marking_lib as ml

"""
Based on the TCP destination port, iptables rules make a generated
packet pass through a certain veth.
NetEm qdiscs are attached to each veth.
There is only DSMARK qdisc attached to eth0.
- iptables meter: the rate is measured by the firewall table and
	the DSMARK class is set by iptables.
- buckets markers: the rate is measured by tc filters on eth0.
	Each filter works for a certain TCP destination port. 

If TECH_NONE, there are no ovs and veths, so NetEm is not applied

"""
# -------------------- METER/MARKER WITH BUCKETS -----------------------#

"""
Create the token bucket filters that send packets to DSMARK classes.

Example:
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
def add_dsmark_filters(intf, dsmark_qdisc_id, rates, user, num_bands, 
	dest_port_tcp=0, veth_id=0):
	"""
	Each user have num_bands filters.
	The lookup priority depends on the user.
	Example:
	3 users, num_bands = 4
	Priority of filters:
	user1: 1  2  3  4
	user2: 5  6  7  8
	user3: 9  10 11 12

	Base priorities:
	user1: (1-1)*4 = 0
	user2: (2-1)*4 = 4
	user3: (3-1)*4 = 8
	The used prio is base_prio + DSCP and min(DSCP) == 1
	"""
	cumulative_rate = 0	
	user_base_prio = (user-1)*num_bands
	max_dscp_used = ml.max_dscp(rates)
	for rate in sorted(rates): # i=1-->num_bands
		dscp = rates[rate]
		prio = user_base_prio + dscp
		"""
		The default class is the highest DSCP.
		For all the others we need a filter to direct to classes
		"""
		if dscp<max_dscp_used:
			width = rate - cumulative_rate
			cumulative_rate += width
			burst = int(width/float(HZ))
			mtu = 2 * MAX_PACKET_SIZE
			tc.add_dsmark_filter(intf, dsmark_qdisc_id, prio, 
				width, burst, mtu, dscp, 
				protocol="tcp", dport=dest_port_tcp)	
			# add_dsmark_filter(intf, dsmark_qdisc_id, prio, width, burst, mtu, dscp, fw=veth_id)	
		else:
			tc.add_dsmark_filter(intf, dsmark_qdisc_id, prio, 
				0, 0, 0, dscp, 
				protocol="tcp", dport=dest_port_tcp)	
			# add_dsmark_filter(intf, dsmark_qdisc_id, prio, 0,0,0, dscp, fw=veth_id)	

# ------------------- METER/MARKER WITH IPTABLES -----------------------------#
"""
Create the set of iptables rules that act like a meter.
Packets are sent to an estimator and then classified
for the DSMARK qdisc. The DSMARK qdisc must be attached to eth0 root.

Example:

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
def iptables_meter_marker(rates, dest_port_tcp, interval, dsmark_qdisc_id):
	est_name = "EST{}".format(dest_port_tcp)
	"""
	All packets of the connection will be first 
	sent to an estimator named as the port
	"""
	ipt.send_to_estimator(est_name, "tcp", dest_port_tcp, interval)
	# send_to_estimator(est_name,"udp", dest_port_udp, interval)

	my_rates = dict(rates) 
	del my_rates[max(my_rates)] # Remove the highest rate
	my_rates[0] = 0
	for rate in reversed(sorted(my_rates)):
		dscp = my_rates[rate]+1
		if rate != min(my_rates):			
			ipt.classify_and_accept(est_name, "tcp", dest_port_tcp, dsmark_qdisc_id, dscp, rate)
		else:
			ipt.classify_and_accept(est_name, "tcp", dest_port_tcp, dsmark_qdisc_id, dscp)


def veth_netem_marker(intf, bn_cap, fixed_rtts, vr_limit, queuelen, 
	g_rates, m_m_rates, marking, tech, num_bands, do_symm, e_f_rates):

	tc.remove_qdiscs(intf)		
	ipt.flush_iptables()
	n_users = len(g_rates)

	# Configure the physical interfce
	if queuelen>0:
		set_queuelen(intf, queuelen*n_users)
		tc.add_pfifo_qdisc(intf, "root", 1)
	else:
		set_queuelen(intf, 1000) # default value

	# Create a single DSMARK qdisc
	dsmark_qdisc_id = 1
	if marking != NO_MARKERS:
		tc.add_dsmark_qdisc(intf, "root", dsmark_qdisc_id, 64, num_bands)
		for dscp in range(1, num_bands+1): # i=1-->8
			tc.change_dsmark_class(intf, dsmark_qdisc_id, dscp, dscp)

	# Set iptables, meters and netem
	for i in range(n_users):
		# user-specific IDs
		user = i+1
		dest_port_tcp = FIRST_TCP_PORT + i
		# dest_port_udp = FIRST_UDP_PORT + i
		netem_qdisc_id = user + 2
		veth_id = user
		veth_intf = "veth{}".format(veth_id)
		if_delay = fixed_rtts[i]
		"""
		EXAMPLE
		i=0, user 1 ---> port 5001
		veth1 <--- netem 3: 

		i=1, user 2 ---> port 5002
		veth2 <--- netem 4:
		"""

		if tech != TECH_NONE:
			"""
			Packets will be sent on interface based on destination port
			"""
			ipt.mark_port_based("tcp", dest_port_tcp, veth_id)

		if marking != NO_MARKERS:
			"""
			Calculate and show the metering thresholds for the user
			"""
			rates = ml.get_rates(g_rates[i], bn_cap, 
				m_m_rates[i], num_bands, do_symm, e_f_rates[i])
			ml.print_rates(rates, bn_cap)

			"""
			Apply meters
			"""
			if marking == IPTABLES_MARKERS:
				# put all measuring and classifying rules for the user
				iptables_meter_marker(rates, dest_port_tcp, 
					if_delay, dsmark_qdisc_id)
			elif marking == BUCKETS_MARKERS:
				# put filters for the user on eth0
				add_dsmark_filters(intf, dsmark_qdisc_id, 
					rates, user, num_bands, dest_port_tcp=dest_port_tcp)

		# -------------------- NetEm -----------------------
		"""
		Attach netem to each veth.
		By default, a veth has txqueuelen 0 (we keep it like that)
		"""
		if tech == TECH_NONE: # there are no veths
			continue

		tc.remove_qdiscs(veth_intf) # delete qdiscs from the veth
		set_queuelen(veth_intf, queuelen) # queuelen = 0

		if if_delay>1: # [ms] apply a delaying qdisc
			tc.add_netem_qdisc(
				veth_intf, "root", netem_qdisc_id, 
				vr_limit, if_delay, queuelen)
		else:
			if queuelen>0: # otherwise it creates a fifo of 1 packet!
				tc.add_pfifo_qdisc(veth_intf, "root", netem_qdisc_id)
		"""
		Alter the source IP of packets
		"""
		ipt.masquerade(veth_intf)	