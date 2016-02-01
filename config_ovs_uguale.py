#!/usr/bin/python

import sys, getopt, subprocess

"""
Execute a command in the terminal
"""
def cmd(command):
	subprocess.call("sudo {}".format(command), shell=True) 


def configure_uguale(controller, queuelen, num_queues):

	# Set the switch in secure-mode: it will need a controller, stop to learn
	cmd("ovs-vsctl set-fail-mode br0 secure")

	# Delete flows and QoS
	cmd("ovs-ofctl -O openflow13 del-flows br0")
	cmd("ovs-vsctl --all destroy queue")
	cmd("ovs-vsctl --all destroy qos")

	# Set the queuelen
	for i in [1,2,3,4]:
		cmd("ifconfig eth{} txqueuelen {}".format(i,queuelen))
		cmd("tc qdisc del dev eth{} root".format(i))

	# Create N RR queues with OVS

	qos = "ovs-vsctl set port eth4 qos=@newqos -- \
	--id=@newqos create qos type=linux-htb other-config:max-rate=1000000 \
	queues="

	for i in range(1,num_queues+1): #i=1..8
		qos += "{}=@q{}".format(i,i)
		if i<num_queues:
			qos +=","
		else:
			qos +=" -- "

	for i in range(1,num_queues+1):
		qos+= "--id=@q{} create queue other-config:min-rate=600 other-config:max-rate=1000000".format(i)
		if i < num_queues:
			qos += " -- "

	cmd(qos)

	# ovs-vsctl set port eth4 qos=@newqos -- \
	# --id=@newqos create qos type=linux-htb other-config:max-rate=1000000 \
	# queues=1=@q1,2=@q2,3=@q3,4=@q4,5=@q5,6=@q6,7=@q7,8=@q8 -- \
	# --id=@q1 create queue other-config:min-rate=600 other-config:max-rate=1000000 -- \
	# --id=@q2 create queue other-config:min-rate=600 other-config:max-rate=1000000 -- \
	# --id=@q3 create queue other-config:min-rate=600 other-config:max-rate=1000000 -- \
	# --id=@q4 create queue other-config:min-rate=600 other-config:max-rate=1000000 -- \
	# --id=@q5 create queue other-config:min-rate=600 other-config:max-rate=1000000 -- \
	# --id=@q6 create queue other-config:min-rate=600 other-config:max-rate=1000000 -- \
	# --id=@q7 create queue other-config:min-rate=600 other-config:max-rate=1000000 -- \
	# --id=@q8 create queue other-config:min-rate=600 other-config:max-rate=1000000


	# Verifiy queues
	#ovs-vsctl list qos
	#ovs-vsctl list queue

	# Substitute them with prio queues
	cmd("ifconfig eth4 txqueuelen {}".format(queuelen))
	cmd("tc qdisc del dev eth4 root")
	cmd("tc qdisc add dev eth4 root handle 1: prio bands {}".format(num_queues+1))

	# Verify kernel queues
	#tc qdisc show dev eth4
	#tc class show dev eth4

	# Connect to the controller
	cmd("ovs-vsctl set-controller br0 tcp:{}".format(controller))

	# Check flows
	#sleep 5
	#ovs-ofctl -O openflow13 dump-flows br0


def main(argv):

	controller = "127.0.0.1:6633"
	queuelen = 100
	num_queues = 8
	help_string = "Usage: -c <ip:port controller> -q <queuelen> -n<num_queues>"
	
	try:
		opts, args = getopt.getopt(argv,"hc:q:n:")
	except getopt.GetoptError:
		print help_string
		sys.exit(2)

	for opt, arg in opts:
		if opt == '-h':
			print help_string
			sys.exit()
		elif opt in ("-c"):
			controller = arg
		elif opt in ("-q"):
			queuelen = int(arg)
		elif opt in ("-n"):
			num_queues = int(arg)

	configure_uguale(controller, queuelen, num_queues)

if __name__ == "__main__":
   main(sys.argv[1:])
