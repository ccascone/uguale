from mylib import *

"""
This library contain all the functions
necessary to use iptables
"""

def flush_iptables():
	sudo_cmd("iptables -F")
	sudo_cmd("iptables -F -t mangle")
	sudo_cmd("iptables -F -t nat")

def print_iptables():
	sudo_cmd("iptables -nL")
	sudo_cmd("iptables -nL -t mangle")
	sudo_cmd("iptables -nL -t nat")

# modify the ip address of packet exiting the interface with the IP address of the interface
def ipt_masquerade(intf):
	sudo_cmd("iptables -t nat -A POSTROUTING -o {} -j MASQUERADE".format(intf))


# classify and accept packets over the threshold rate with a certain dport 
# if no threshold is passed, match only the dport
def ipt_classify_and_accept(est_name, protocol, dest_port, qdisc_id, class_id, rate = -1):
	
	if rate>0:
		match_on_rate = "-m rateest --rateest {} --rateest-gt --rateest-bps {} ".format(est_name, rate)
	else:
		match_on_rate = ""

	command1 = "iptables -A OUTPUT -p {} -m {} --dport {} {}-j CLASSIFY --set-class {}:{}".format(
				protocol, protocol, dest_port, match_on_rate, qdisc_id, class_id)

	command2 = "iptables -A OUTPUT -p {} -m {} --dport {} {}-j ACCEPT".format(
				protocol, protocol, dest_port, match_on_rate)

	sudo_cmd(command1)
	sudo_cmd(command2)
	

"""
Mark packets based on destination port 
so they will be looked up with other routing tables
"""
def ipt_mark_port_based(protocol, dest_port, dest_intf_id):
	command = "iptables -t mangle -A OUTPUT -p {} --dport {} -j MARK --set-mark {}".format(
				protocol, dest_port, 
				dest_intf_id)
	sudo_cmd(command)	


"""
The minimum interval is 250ms
Send all packets to a certain estimator
"""
def ipt_send_to_estimator(est_name, protocol, dest_port, interval):
	command = "iptables -A OUTPUT \
		-p {} \
		-m {} --dport {} \
		-j RATEEST --rateest-name {} \
		--rateest-interval {}ms \
		--rateest-ewmalog {}ms".format(
			protocol, 
			protocol,dest_port, 
			est_name, 
			interval, 
			interval*2)
	sudo_cmd(command)