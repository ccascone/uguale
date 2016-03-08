#!/usr/bin/python
"""
Prepares a PC to simulate many users by creating an internal 
OVS switch with virtual interfaces.
"""
import sys, getopt, time
from mylib import *

def run_program(pc_ip):
	killall("iperf")
	sudo_cmd("sysctl -w net.ipv4.tcp_no_metrics_save=1")  # instruct linux to forget previous tcp sessions

	print "Creating br0"
	sudo_cmd("ovs-vsctl add-br br0")
	sudo_cmd("ovs-vsctl set-fail-mode br0 standalone")
	sudo_cmd("ifconfig br0 {} up".format(pc_ip))
	sudo_cmd("ovs-vsctl add-port br0 eth0")
	sudo_cmd("ifconfig eth0 0.0.0.0 up")	
	sudo_cmd("ip rule flush")
	sudo_cmd("ip rule add from all table main priority 32766")
	sudo_cmd("ip rule add from all table default priority 32767")
	time.sleep(1)

	print "Setting up veths"
	for i in range(NUM_VETHS):
		veth_id = i + 1
		veth_ip = ADDRESSES[pc_ip][i]
		veth_intf="veth{}".format(veth_id)
		sudo_cmd("ovs-vsctl add-port br0 veth{} -- set interface veth{} type=internal".format(veth_id, veth_id))
		sudo_cmd("ifconfig veth{} {} up".format(veth_id, veth_ip))
		sudo_cmd("ip rule add fwmark {} table {}".format(veth_id, veth_id))
		sudo_cmd("ip route add default dev {} table {}".format(veth_intf, veth_id))
		sudo_cmd("sysctl -w net.ipv4.conf.{}.rp_filter=2".format(veth_intf))
	time.sleep(1)

	sudo_cmd("ip route flush cache")
	sudo_cmd("ip route flush table main")
	sudo_cmd("ip route add default dev br0")

def main(argv):
	help_string = "Usage: -s<pc-ip>"
	try:
		opts, args = getopt.getopt(argv, "hs:")
	except getopt.GetoptError:
		print help_string
		sys.exit(2)

	for opt, arg in opts:
		if opt == '-h':
			print help_string
			sys.exit()
		elif opt in ("-s"):
			pc_ip = arg

	run_program(pc_ip)

if __name__ == "__main__":
	main(sys.argv[1:])
