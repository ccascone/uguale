#!/usr/bin/python
import getopt
import sys

from cmdlib import cmd
from new.uconf import *


def configure_uguale(controller, queuelen, num_queues):
    """
    Creates an OVS bridge named brUG, connected to the given controller and attached to num_queues queues served by a
    priority scheduler. Moreover, sets queuelen for all SW_INTFS to queuelen pkts.

    :param controller: controller string
    :param queuelen: queue lenght in packets
    :param num_queues: number of priority queues
    :return:
    """
    # Set the switch in secure-mode
    # it will need a controller, stop to learn
    cmd("ovs-vsctl set-fail-mode brUG secure")

    # Delete current flows and QoS configurations
    cmd("ovs-ofctl -O openflow13 del-flows brUG")
    cmd("ovs-vsctl --all destroy queue")
    cmd("ovs-vsctl --all destroy qos")

    # Set the queuelen
    for intf in SW_INTFS:
        cmd("ifconfig {} txqueuelen {}".format(intf, queuelen))
        cmd("tc qdisc del dev {} root".format(intf))

    # Create N Round robin queues on eth4 with ovs-vsctl
    qos = "ovs-vsctl set port {} qos=@newqos -- \
    --id=@newqos create qos type=linux-htb other-config:max-rate={} \
    queues=".format(BN_IFNAME, BN_BITRATE)

    for i in range(1, num_queues + 1):  # i=1..8
        qos += "{}=@q{}".format(i, i)
        if i < num_queues:
            qos += ","
        else:
            qos += " -- "

    for i in range(1, num_queues + 1):
        qos += "--id=@q{} create queue other-config:min-rate=600 other-config:max-rate={}".format(i, BN_BITRATE)
        if i < num_queues:
            qos += " -- "

    cmd(qos)

    # Substitute the round robin queues with prio queues
    cmd("ifconfig {} txqueuelen {}".format(BN_IFNAME, queuelen))
    cmd("tc qdisc del dev {} root".format(BN_IFNAME))
    cmd("tc qdisc add dev {} root handle 1: prio bands {}".format(BN_IFNAME, num_queues + 1))

    # Connect to the controller
    cmd("ovs-vsctl set-controller brUG tcp:{}".format(controller))

    # OLD SH COMMANDS:
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
    #
    # Verifiy queues
    # ovs-vsctl list qos
    # ovs-vsctl list queue
    #
    # Verify kernel queues
    # tc qdisc show dev eth4
    # tc class show dev eth4
    #
    # Check flows
    # sleep 5
    # ovs-ofctl -O openflow13 dump-flows brUG


def main(argv):
    controller = "127.0.0.1:6633"
    queuelen = 100
    num_queues = 8
    help_string = "Usage: -c <ip:port controller> -q <queuelen> -n<num_queues>"

    try:
        opts, args = getopt.getopt(argv, "hc:q:n:")
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
