#!/usr/bin/python
import getopt
import re
import subprocess
import sys
import threading
import time

from mylib import *

"""
This program plot the bands of packet received by some hosts.
"""
sem_data = threading.Semaphore(1)  # semaphore for operations on data
stop = threading.Event()  # event to stop threads

directions = ["in", "out"]
modalities = ["i", "p"]

"""
execute tdpdump and parse data to create a dict like:
{"IP:port": Bytes}
"""


def tcpdump_thread(data, intf, direct, modality):
    cmd = "sudo tcpdump ip -i {} -v -P {} -K -n -s 0".format(intf, direct)
    reg1 = re.compile(".*tos 0x([0-9,a-f]{1,2}),.*, length ([0-9]{1,20})")
    reg2 = re.compile(
        ".* ([0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3})\.[0-9]{1,10} > [0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.([0-9]{1,10}):")
    tos = 0
    src_ip = ""
    src_id = ""
    dst_port = ""
    length = 0

    for line in runPexpect(cmd):
        if stop.is_set():
            break
        """
        Every packet trigger 2 lines. The second begin with a space
        """
        m = reg1.match(line)
        if m is not None:
            """
            Example line:
            12:16:30.565026 IP (tos 0x0, ttl 58, id 7265, offset 0, flags [DF], proto TCP (6), length 40)
            """
            tos = int(m.groups()[0], 16)
            length = int(m.groups()[1])
        else:
            m2 = reg2.match(line)
            if m2 is not None:
                """
                Example line:
                 104.16.105.85.80 > 192.168.1.132.59438: Flags [F.], seq 2144417321, ack 3540285043, win 34, length 0
                """
                src_ip = str(m2.groups()[0].strip())
                dst_port = str(m2.groups()[1].strip())

                src_id = "{}->{}".format(src_ip, dst_port)

                if src_ip != "0.0.0.0":
                    if modality == "i":
                        print "{} sent a packet sized {}B marked with DSCP {}".format(src_id, length, tos >> 2)
                    else:
                        with sem_data:
                            # print "Add ip"
                            if src_id not in data:
                                data[src_id] = {}
                            # data[src_id]["lengths"]=[]

                            # print "Add TOS"
                            if tos not in data[src_id]:
                                data[src_id][tos] = 0

                            # print "Add B"
                            data[src_id][tos] += length
                        # data[src_id]["lengths"].append(length)
                        # print length
            tos = 0
            src_ip = ""
            src_id = ""
            dst_port = ""
            length = 0


"""
Show data collected during an interval intv
then reset data
"""


def visualize_thread(data, intv):
    """
    Plotting loop
    """
    time.sleep(1)
    subprocess.call("clear", shell=True)
    while not stop.is_set():
        time.sleep(intv)
        with sem_data:
            data_copy = data.copy()
            data.clear()

        print_str = ""
        for src in sorted(data_copy):
            tot = 0
            for tos in data_copy[src]:
                tot += data_copy[src][tos]
            if tot > 0:
                rate = num_to_rate_int((tot * 8) / intv)
                print_str += "Timestamp {}: {} sending at {}bps\n".format(time.time(), src, rate)
                for tos in sorted(data_copy[src]):
                    perc = (data_copy[src][tos] * 100) / tot
                    rate_perc = num_to_rate_int((data_copy[src][tos] * 8) / intv)
                    print_str += "DSCP {}: {} % , {}bps\n".format(tos >> 2, perc, rate_perc)

        if print_str != "":
            print print_str
        else:
            print "{}: No packets\n".format(time.time())


"""
Listen for user commands
"""


def keyboard_listener(data):
    quit = "q"
    reset = "r"
    cmd = ""
    while cmd != quit:
        cmd = str(raw_input("Command:"))
        if cmd == quit:
            stop.set()
        elif cmd == reset:
            with sem_data:
                data = {}
        else:
            print "Invalid command"


def run_program(intf, direct, modality, intv):
    """
    thread 1 : execute and parse tcpdump
    thread 2 : print data
    """
    sudo_cmd("killall tcpdump")
    stop.clear()
    data = {}

    threads = {
        "tcpdump": threading.Thread(target=tcpdump_thread, args=(data, intf, direct, modality))
    }

    if modality == "p":
        threads["visualize"] = threading.Thread(target=visualize_thread, args=(data, intv))
    for key in threads:
        threads[key].daemon = False
        threads[key].start()
    try:
        keyboard_listener(data)
    except (KeyboardInterrupt, SystemExit):  # executed only in case of exceptions
        stop.set()
    finally:  # always executed
        stop.set()
        sudo_cmd("killall tcpdump")
        for key in threads:
            threads[key].join()
        print "All joined, end"
    # subprocess.call("clear", shell=True)


def main(argv):
    intf = "eth0"
    direct = "in"
    modality = "p"
    intv = 2.0
    help_string = "Usage: -i <intf> -d <direction: in or out>"

    try:
        opts, args = getopt.getopt(argv, "hi:d:")
    except getopt.GetoptError:
        print help_string
        sys.exit(2)

    for opt, arg in opts:
        if opt == '-h':
            print help_string
            sys.exit()
        elif opt in ("-i"):
            intf = arg
        elif opt in ("-d"):
            direct = arg

    if (direct not in directions) or (intf == ""):
        print help_string
        sys.exit(2)

    run_program(intf, direct, modality, intv)


if __name__ == "__main__":
    main(sys.argv[1:])
