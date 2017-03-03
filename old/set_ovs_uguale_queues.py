#!/usr/bin/python
import getopt
import subprocess
import sys


# Execute a command in the terminal
def sudo_cmd(command):
    subprocess.call("sudo {}".format(command), shell=True)


def configure_uguale_queues(queuelen, num_queues):
    # Substitute the round robin queues with prio queues
    sudo_cmd("ifconfig eth4 txqueuelen {}".format(queuelen))
    sudo_cmd("tc qdisc del dev eth4 root")
    sudo_cmd("tc qdisc add dev eth4 root handle 1: prio bands {}".format(num_queues + 1))


def main(argv):
    queuelen = 100
    num_queues = 8
    help_string = "Usage: -q <queuelen> -n<num_queues>"

    try:
        opts, args = getopt.getopt(argv, "hc:q:n:")
    except getopt.GetoptError:
        print help_string
        sys.exit(2)

    for opt, arg in opts:
        if opt == '-h':
            print help_string
            sys.exit()
        elif opt in ("-q"):
            queuelen = int(arg)
        elif opt in ("-n"):
            num_queues = int(arg)

    configure_uguale_queues(queuelen, num_queues)


if __name__ == "__main__":
    main(sys.argv[1:])
