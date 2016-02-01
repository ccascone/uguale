# parameter1: IP:PORT of the controlles
# parameter2: queuelen
# parameter3: number of queues
# es: 10.100.13.162:6633 100

# Set the switch in secure-mode: it will need a controller, stop to learn
sudo ovs-vsctl set-fail-mode br0 secure

# Delete flows and QoS
ovs-ofctl -O openflow13 del-flows br0
ovs-vsctl --all destroy queue
ovs-vsctl --all destroy qos

# Set the queuelen
for i in 1 2 3 4
do
	ifconfig eth$i txqueuelen $2
    tc qdisc del dev eth$i root
done

# Create N RR queues with OVS



ovs-vsctl set port eth4 qos=@newqos -- \
--id=@newqos create qos type=linux-htb other-config:max-rate=1000000 \
queues=1=@q1,2=@q2,3=@q3,4=@q4,5=@q5,6=@q6,7=@q7,8=@q8 -- \
--id=@q1 create queue other-config:min-rate=600 other-config:max-rate=1000000 -- \
--id=@q2 create queue other-config:min-rate=600 other-config:max-rate=1000000 -- \
--id=@q3 create queue other-config:min-rate=600 other-config:max-rate=1000000 -- \
--id=@q4 create queue other-config:min-rate=600 other-config:max-rate=1000000 -- \
--id=@q5 create queue other-config:min-rate=600 other-config:max-rate=1000000 -- \
--id=@q6 create queue other-config:min-rate=600 other-config:max-rate=1000000 -- \
--id=@q7 create queue other-config:min-rate=600 other-config:max-rate=1000000 -- \
--id=@q8 create queue other-config:min-rate=600 other-config:max-rate=1000000


# Verifiy queues
#ovs-vsctl list qos
#ovs-vsctl list queue

# Substitute them with prio queues
ifconfig eth4 txqueuelen $2
tc qdisc del dev eth4 root
tc qdisc add dev eth4 root handle 1: prio bands 9

# Verify kernel queues
#tc qdisc show dev eth4
#tc class show dev eth4

# Connect to the controller
ovs-vsctl set-controller br0 tcp:$1

# Check flows
#sleep 5
#ovs-ofctl -O openflow13 dump-flows br0
