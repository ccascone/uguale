#!/usr/bin/python

import sys, getopt, time
from mylib import *

"""
Prepare a PC to simulate many users by creating 
an internal bridge, veths and restoring connectivity.
Create veth1 to veth10 with ip es. .30 to .39
"""

def set_up_host_ovs(pc_ip, intf):
	killall("iperf")
	sudo_cmd("sysctl -w net.ipv4.tcp_no_metrics_save=1")  # instruct linux to forget previous tcp sessions

	print "Deleting br0"
	sudo_cmd("ovs-vsctl del-br br0") # By deleting a bridge, also its internal interfaces will be deleted 
	time.sleep(0.5)

	print "Creating br0"
	sudo_cmd("ovs-vsctl add-br br0")
	sudo_cmd("ovs-vsctl set-fail-mode br0 standalone")
	sudo_cmd("ifconfig br0 {} up".format(pc_ip))
	sudo_cmd("ovs-vsctl add-port br0 {}".format(intf))
	sudo_cmd("ifconfig {} 0.0.0.0 up".format(intf))	
	flush_ip_rule()
	time.sleep(0.5)

	print "Setting up veths"
	for i in range(NUM_VETHS):
		veth_id = i+1
		veth_ip = ADDRESSES[pc_ip][i]
		veth_intf="veth{}".format(veth_id)
		sudo_cmd("ovs-vsctl add-port br0 veth{} -- set interface veth{} type=internal".format(veth_id, veth_id))
		sudo_cmd("ifconfig veth{} {} up".format(veth_id, veth_ip))
		sudo_cmd("ip rule add fwmark {} table {}".format(veth_id, veth_id))
		sudo_cmd("ip route add default dev {} table {}".format(veth_intf, veth_id))
		sudo_cmd("sysctl -w net.ipv4.conf.{}.rp_filter=2".format(veth_intf))
	time.sleep(0.5)

	sudo_cmd("ip route flush cache")
	sudo_cmd("ip route flush table main")
	sudo_cmd("ip route add default dev br0")

def set_up_host_none(pc_ip, intf):
	killall("iperf")
	sudo_cmd("sysctl -w net.ipv4.tcp_no_metrics_save=1")  # instruct linux to forget previous tcp sessions
	sudo_cmd("ovs-vsctl del-br br0") # By deleting a bridge, also its internal interfaces will be deleted 
	sudo_cmd("ifconfig {} {} up".format(intf,pc_ip))
	flush_ip_rule()

def flush_ip_rule():
	sudo_cmd("ip rule flush")
	sudo_cmd("ip rule add from all table main priority 32766")
	sudo_cmd("ip rule add from all table default priority 32767")

def main(argv):
	intf = "eth0"
	help_string = "Usage: -s <pc-ip> -i <interface> -t<ovs/br/vlans/none>"

	try:
		opts, args = getopt.getopt(argv,"hs:i:t:")

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
		elif opt in ("-t"):
			tech = arg


	if tech == "ovs":
		set_up_host_ovs(pc_ip, intf)
	elif tech == "br":
		set_up_host_br(pc_ip, intf)
	elif tech == "vlans":
		set_up_host_vlans(pc_ip, intf)
	elif tech == "none":
		set_up_host_none(pc_ip, intf)
	else:
		print help_string
		sys.exit(2)

if __name__ == "__main__":
	main(sys.argv[1:])



# def set_up_host_br(host_id, intf):
# 	killall("iperf")

# 	print "Deleting br0"
# 	sudo_cmd("ip link set br0 down") 
# 	sudo_cmd("brctl delbr br0") # By deleting a bridge, also its internal interfaces will be deleted 
# 	sudo_cmd("ip link del br0") 

# 	#sudo_cmd("ip route add default dev br0")

# 	print "Creating br0"
# 	sudo_cmd("brctl addbr br0")
# 	sudo_cmd("brctl stp br0 off")
# 	sudo_cmd("ifconfig br0 {}.{} up".format(NETWORK_PREFIX, host_id))
# 	sudo_cmd("brctl addif br0 {}".format(intf))
# 	sudo_cmd("ifconfig {} 0.0.0.0 up".format(intf))	
# 	flush_ip_rule()

# 	print "Setting up veths"
# 	for i in range(NUM_VETHS):
# 		veth_id = i+1
# 		veth_intf="veth{}".format(veth_id)
# 		veth_linux = "br{}".format(veth_intf)
# 		veth_ip = (host_id*NUM_VETHS)+i

# 		print veth_id, veth_intf, veth_linux, veth_ip

# 		sudo_cmd("ip link set {} down".format(veth_intf))
# 		sudo_cmd("ip link del {}".format(veth_intf))
# 		sudo_cmd("ip link set {} down".format(veth_linux))
# 		sudo_cmd("ip link del {}".format(veth_linux))

# 		sudo_cmd("ip link add {} type veth peer name {}".format(veth_intf, veth_linux))
# 		sudo_cmd("brctl addif br0 {}".format(veth_linux))

# 		sudo_cmd("ifconfig {} {}.{} up".format(veth_intf, NETWORK_PREFIX, veth_ip))
# 		sudo_cmd("ifconfig {} 0.0.0.0 up".format(veth_linux, NETWORK_PREFIX, veth_ip))

# 		sudo_cmd("ip rule add fwmark {} table {}".format(veth_id, veth_id))
# 		sudo_cmd("ip route add default dev {} table {}".format(veth_intf, veth_id))

# 		sudo_cmd("sysctl -w net.ipv4.conf.{}.rp_filter=2".format(veth_intf))
# 		#sudo_cmd("sysctl -w net.ipv4.conf.{}.rp_filter=2".format(veth_linux))

# 	sudo_cmd("ip route flush cache")
# 	sudo_cmd("ip route flush table main")
# 	sudo_cmd("ip route add default dev br0")



# def set_up_host_vlans(host_id, intf):

# 	flush_ip_rule()

# 	sudo_cmd("ip route flush cache")
# 	sudo_cmd("ip route flush table main")
# 	sudo_cmd("ip route add 192.168.1.0/24 dev {}".format(intf))

# 	for i in range(NUM_VETHS):
# 		vlan_id = (i+1)*NUM_VETHS
# 		vlan_intf = "{}.{}".format(intf, vlan_id)
# 		user_id = (host_id*NUM_VETHS)+i
# 		vlan_ip = "{}.{}.{}".format(NETWORK_PREFIX_16, vlan_id, user_id)

# 		print vlan_intf, vlan_ip

# 		#sudo_cmd("ip link set {} down".format(vlan_intf))
# 		#sudo_cmd("ip link del {}".format(vlan_intf))
# 		#time.sleep(1)
		
# 		sudo_cmd("ip link add link {} {} type vlan id {}".format(intf,vlan_intf,vlan_id))
# 		#time.sleep(1)
		
# 		sudo_cmd("ifconfig {} {} up".format(vlan_intf, vlan_ip))
# 		sudo_cmd("ip route add {}.{}.0/24 dev {}".format(NETWORK_PREFIX_16,vlan_id, vlan_intf))