#!/usr/bin/python
"""
Set of functions executing tc calls
"""
from mylib import *

"""
Delete all qdiscs from an interface
"""
def remove_qdiscs(intf):
	sudo_cmd("tc qdisc del dev {} root".format(intf))

"""
Print the tc configuration (qdiscs, classes and filters)
applied to an interface.
"""
def print_tc_configuration(intf, qdiscs=[]):
	print "---------- tc configuration for {} ----------".format(intf)
	print "---------- qdiscs ----------"
	sudo_cmd("tc qdisc show dev {}".format(intf))
	print "---------- classes ---------"
	sudo_cmd("tc class show dev {}".format(intf))
	if len(qdiscs)>0:
		print "---------- filters ---------"
		for parent in qdiscs:
			sudo_cmd("tc filter show dev {} parent {}:".format(intf, parent))

# ------------------------------------- DSMARK --------------------------------------#
"""
Creates a DSMARK qdisc
"""
def add_dsmark_qdisc(intf, parent_id, dsmark_qdisc_id, num_classes, default_class):
	command = "tc qdisc add dev {} {} handle {}: dsmark indices {} default {}".format(
			intf, parent_string(parent_id), dsmark_qdisc_id, num_classes, default_class)
	sudo_cmd(command)

"""
The DSMARK qdisc is created with num_classes empty classes.
This functions create the real DSMARK classes attached to that qdisc.
"""
def change_dsmark_class(intf, dsmark_qdisc_id, dsmark_class_id, dscp):
	command = "tc class change dev {} parent {}: classid {}:{} dsmark mask 0xff value {}".format(
			intf, dsmark_qdisc_id, dsmark_qdisc_id, dsmark_class_id, hex(dscp << 2))
	sudo_cmd(command)

"""
Add a tc filter (that send packets to a certain DSMARK class
"""
def add_dsmark_filter(intf, dsmark_qdisc_id, prio, 
	rate, burst, mtu, dsmark_class_id, protocol="", dport=0, fw=-1):

	# Apply the filter only to certain packets
	match_field = ""
	if protocol!="" and dport!=0: # match a destination port
		match_field = "u32 match ip dport {} 0xffff".format(dport)		
	elif fw!=-1: # match a firewall mark
		match_field = "handle {} fw".format(fw)
	else: # match all
		match_field = "u32 match ip protocol 0 0"	

	# Match on the measured rate
	police_field = ""
	if (rate>0 and burst>0 and mtu>0):
		police_field = "police rate {}bit burst {} mtu {} continue ".format(
			rate, burst, mtu)
		# note the space at the and of the string

	command = "tc filter add dev {} parent {}: protocol ip prio {} {} {}classid {}:{}".format(
		intf, dsmark_qdisc_id, prio, match_field, police_field, 
		dsmark_qdisc_id, dsmark_class_id)
	print command
	sudo_cmd(command)

# ------------------------------------- NETEM --------------------------------------#
"""
Add a netem qdisc to an interface
"""
def add_netem_qdisc(intf, parent_id, netem_qdisc_id, rate=0, delay=0, limit=0):

	if rate==0 and delay==0:
		print "NetEm called without limiting parameters"
		return

	my_rate, my_delay, my_limit = "", "", ""

	if rate>0:
		my_rate = "rate {}".format(rate)

	if delay>0:
		my_delay = "delay {}ms".format(delay)

	if limit>0:
		my_limit = "limit {}".format(limit)

	command = "tc qdisc add dev {} {} handle {}: netem {} {} {}".format(
		intf, parent_string(parent_id), netem_qdisc_id, my_delay, my_rate, my_limit)

	sudo_cmd(command)

"""
Add a packet FIFO qdisc to an interface
"""
def add_pfifo_qdisc(intf, parent_id, pfifo_id):
	command = "tc qdisc add dev {} {} handle {}: pfifo".format(
		intf, parent_string(parent_id), pfifo_id)
	sudo_cmd(command)

"""
Return the parent string to be used in tc commands
"""
def parent_string(parent_id):
	if parent_id=="root":
		return parent_id
	else:
		return "parent {}:".format(parent_id)
