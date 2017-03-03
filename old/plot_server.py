#!/usr/bin/python
import getopt
import inspect
import sys
import threading
from threading import Timer

import matplotlib
import matplotlib.pyplot as plt
from numpy import ones, vstack
from numpy.linalg import lstsq
from scipy import interpolate

from cmdlib import killall, iterate_cmd_out
from mylib import *

"""
This program executes an iperf TCP, UDP server and
shows the bandwidth used by each source IP.
Since it aggregate flows, an iperf client must create at least 
2 connection to be displayed.  
"""

sem_data = threading.Semaphore(1)  # semaphore for operations on data
stop = threading.Event()  # event to stop every thread
pause = threading.Event()  # event to pause the visualizations
global t0  # unix timestamp of the reference instant
clients_id = []  # list of all couples (ip-port) that identify an user
DEATH_TOLERANCE = 2 * IPERF_REPORT_INTERVAL  # time with no reports after which a user is considered dead
T = IPERF_REPORT_INTERVAL * 0.8  # reports in [t-T,t+T] are burned
max_time_window = 60  # The graph keeps expanding until max_time_window [seconds], then data and graph are reset
SMOOTH_WINDOW = 16  # number of samples to be smoothed
DENSITY_LINSPACE = 4  # resampling frequency


def print_legend(subp, num_flows):
    if num_flows == 1:
        title = "1 user"
    else:
        title = "{} users".format(num_flows)

    subp.legend(
        bbox_to_anchor=(1.03, 1),
        loc=2,
        borderaxespad=0.,
        title=title)


def smooth(list_x, window_len=10, window='hanning'):
    """smooth the data using a window with requested size.

    This method is based on the convolution of a scaled window with the signal.
    The signal is prepared by introducing reflected copies of the signal
    (with the window size) in both ends so that transient parts are minimized
    in the begining and end part of the output signal.

    input:
        x: the input signal
        window_len: the dimension of the smoothing window; should be an odd integer
        window: the type of window from 'flat', 'hanning', 'hamming', 'bartlett', 'blackman'
            flat window will produce a moving average smoothing.

    output:
        the smoothed signal

    example:

    t=linspace(-2,2,0.1)
    x=sin(t)+randn(len(t))*0.1
    y=smooth(x)

    see also:

    np.hanning, np.hamming, np.bartlett, np.blackman, np.convolve
    scipy.signal.lfilter

    TODO: the window parameter could be the window itself if an array instead of a string
    NOTE: length(output) != length(input), to correct this: return y[(window_len/2-1):-(window_len/2)] instead of just y.
    """

    """
    if x.ndim != 1:
        raise ValueError, "smooth only accepts 1 dimension arrays."

    if x.size < window_len:
        raise ValueError, "Input vector needs to be bigger than window size."
    """

    if window_len < 3:
        return list_x

    if len(list_x) < window_len:
        return list_x

    if not window in ['flat', 'hanning', 'hamming', 'bartlett', 'blackman']:
        raise ValueError, "Window is on of 'flat', 'hanning', 'hamming', 'bartlett', 'blackman'"

    x = np.array(list_x)
    s = np.r_[x[window_len - 1:0:-1], x, x[-1:-window_len:-1]]
    # print(len(s))
    if window == 'flat':
        w = np.ones(window_len, 'd')
    else:
        w = eval('np.' + window + '(window_len)')

    y = np.convolve(w / w.sum(), s, mode='valid')

    sm = list(y[(window_len / 2 - 1):-(window_len / 2)])
    len_sm = len(sm)
    len_x = len(list_x)
    if len_sm == len_x:
        return sm
    if len_sm < len_x:
        sm += [0] * (len_x - len_sm)
        return sm
    else:
        return sm[:len_x]


# Return true if the line is valid, false otherwise
def is_valid_iperf_tcp_line(cols, report_interval):
    if len(cols) < 8:
        return False
    # Summation line
    if (cols[2], cols[4], cols[5][0]) != ("0", "0", "-"):
        return False
    # Invalid report interval - end of transmission reports
    intvs = cols[6].split("-")
    intv0 = float(intvs[0])
    intv1 = float(intvs[1])
    if intv1 - intv0 != float(report_interval):
        return False
    return True


# Return true if the line is valid, false otherwise
def is_valid_iperf_udp_line(cols, report_interval):
    if len(cols) != 14 or int(cols[13]) != 0:
        return False
    # Invalid report interval - end of transmission reports
    intvs = cols[6].split("-")
    intv0 = float(intvs[0])
    intv1 = float(intvs[1])
    if intv1 - intv0 != float(report_interval):
        return False
    return True


# ------------------------------ SUM OF FLOWS -------------------------------------#


# Find the first index where time >= t
# data is a time list
# if it does not exist, return -1

def first_index_geq(data, t):
    index = -1
    for i in range(len(data)):
        if data[i] >= t:
            index = i
            break
            # print "First index in {} where val >= {} is in pos {}".format(data,t,index)
    return index


# Find to which flows belong t and its index
# data is data[uid]
def find_timestamp(data, t):
    prot = "tcp"
    index = -1
    try:
        index = data[prot]["t"].index(t)
    except ValueError:
        prot = "udp"
        index = data[prot]["t"].index(t)
    finally:
        return [prot, index]


# def is_sorted(data):
#   if sorted(data)!=data:
#       return False
#   return True

# Delete samples around t and insert the new sample in the right position
# data is data[uid][prot]
def fire(data, t):
    # update the series of the protocol
    begin = first_index_geq(data["t"], t - T)
    end = first_index_geq(data["t"], t + T)
    if end - begin > 0:
        print "Fire in [{}:{}], {} are to delete -->".format(begin, end, data["t"][begin:end]),
        del (data["t"][begin:end])
        del (data["val"][begin:end])
        print "{}".format(data["t"])


# insert t,val in the correct position of data
# data is data[uid][x]
def insert_value(data, t, val):
    index = first_index_geq(data["t"], t)
    if index == -1:
        data["t"].append(t)
        data["val"].append(val)
    else:
        data["t"].insert(index, t)
        data["val"].insert(index, val)


def get_other(prot):
    if prot == "tcp":
        return "udp"
    return "tcp"


# return the value that link values of data around t in t
# return 0 if a line cannot be traced
# data is data[uid][prot]
def line_around_t(data, t):
    i2 = first_index_geq(data["t"], t)
    if i2 > 0:
        x_coords = (data["t"][i2 - 1], data["t"][i2])
        y_coords = (data["val"][i2 - 1], data["val"][i2])
        A = vstack([x_coords, ones(len(x_coords))]).T
        m, c = lstsq(A, y_coords)[0]
        # print "Line Solution is y = {m}x + {c}".format(m=m,c=c)
        return (m * t) + c
    return -1


# Append a 0 sample if last received sample is too far
# return True is a ded is declared, False otherwise
# Data is data[uid][prot]
def update_death_flows(data, t):
    if len(data["t"]) > 0:
        last_t = data["t"][-1]
        if t - last_t >= DEATH_TOLERANCE:
            data["t"].append(last_t + IPERF_REPORT_INTERVAL)
            data["val"].append(0)
            return True
    return False


def update_sum(data, t, val, uid, prot, singles):
    # print "Begin with {}".format(data[prot]["t"])
    other = get_other(prot)
    # delete samples around t because they are fake
    fire(data[prot], t)
    # insert the new poit
    insert_value(data[prot], t, val)
    # add the new point in total
    insert_value(data["total"], t, val)
    # declare as singles all totals in the burned interval
    # print "---------------------------"
    # print "Start update with {} singles".format(len(singles))
    declare_as_singles(data["total"]["t"], t - T, t + T, singles)
    # print "After singles in fire, {}".format(len(singles))
    # see if the other flow is dead and declare it
    if update_death_flows(data[other], t):
        # if something changed, declare these points as singles
        declare_as_singles(data["total"]["t"], data[other]["t"][-2], data[other]["t"][-1], singles)
    # update singles: sort and delete samples too old
    singles = update_singles(singles)
    # print "After update, {}".format(len(singles))
    # try to solve all singles
    singles = solve_singles(data, singles)
    # print "After solution, {}".format(len(singles))

    return singles


# print "End with {}".format(data[prot]["t"])

# ------------------------------ SINGLES -------------------------------------#

# Declare as singles the totals between [t1,t2]
# data is data[uid][total]["t"]
def declare_as_singles(data, t1, t2, singles):
    # print len(singles),
    begin = first_index_geq(data, t1)
    end = first_index_geq(data, t2)
    if begin < 0:
        print ""
        return
    if end < 0:
        end = len(data)
    for i in range(begin, end):
        singles.append(data[i])
        # print len(singles)


# Order singles and delete old singles
def update_singles(singles):
    # list(set()) eliminate duplicates
    s = sorted(list(set(singles)))
    last_t = s[-1]
    first_valid = first_index_geq(s, last_t - max_time_window)
    if first_valid > 0:
        # print "delete old singles {},".format(len(singles)),
        del s[:first_valid]
    # print len(singles)
    return s


# Solve the list of singles
# data is data[uid]
def solve_singles(data, singles):
    solved_singles = []
    for single in singles:
        prot, index = find_timestamp(data, single)
        val1 = data[prot]["val"][index]
        val2 = line_around_t(data[get_other(prot)], single)

        # we have to be sure that already exists
        index_in_total = data["total"]["t"].index(single)
        data["total"]["val"][index_in_total] = val1 + val2
        if val2 > 0:
            solved_singles.append(single)

    s = list(singles)
    for single in solved_singles:
        del s[s.index(single)]
    return s


# ------------------------------ END SUM OF FLOWS -------------------------------------#

"""
Execute an iperf server and parse its data
"""


def iperf_tcp_thread(data, port, singles):
    print "iperf tcp server on port {} started".format(port)
    report_interval = IPERF_REPORT_INTERVAL
    cmd = "iperf -s -i{} -fk -yC -p{}".format(report_interval, port)

    tzeros = {}  # first timestamp of each user

    for line in iterate_cmd_out(cmd):
        if stop.is_set():
            break
        """
        example line:
        0              1             2    3             4     5    6     7          8
        20150803124132,10.100.13.214,5001,10.100.13.162,56695,4,0.0-17.4,1005453312,463275664

        0: timestamp
        1: server_ip
        2: server_port
        3: client_ip
        4: client_port
        5: connection id (for iperf)
        6: time-interval
        7: bytes transferred in the interval
        8: rate in the interval
        """
        cols = line.split(",")

        if not is_valid_iperf_tcp_line(cols, report_interval):
            continue

        ip, rate_bps = str(cols[3]), float(cols[8])
        uid = ip  # "{}-{}".format(ip, port)

        # iperf date is formatted, get the corresponding unix timestamp
        stamp = time.time() - t0

        val_tcp = rate_bps  # float(num_bytes * 8) / float(report_interval)

        with sem_data:
            if uid not in data:
                data[uid] = new_client_data()

            intvs = cols[6].split("-")
            intv0 = float(intvs[0])
            intv1 = float(intvs[1])

            if intv0 == 0.0 or uid not in tzeros:
                tzeros[uid] = stamp - report_interval

            stamp = tzeros[uid] + intv1

            if uid not in singles:
                singles[uid] = []
            singles[uid] = update_sum(data[uid], t=stamp, val=val_tcp, uid=uid, prot="tcp", singles=singles[uid])

    print "iperf tcp server on port {} terminated, stop = {}".format(port, stop)


def iperf_udp_thread(data, port, singles):
    print "iperf udp server on port {} started".format(port)
    report_interval = IPERF_REPORT_INTERVAL
    cmd = "iperf -s -i{} -fk -yC -u -p{}".format(report_interval, port)
    tzeros = {}
    for line in iterate_cmd_out(cmd):
        if stop.is_set():
            break
        """
        example line: (len=14)
        0              1             2    3             4     5    6     7       8       9     10 11  12    13
        20150803222713,192.168.100.4,5002,192.168.100.2,36823,3, 5.0-6.0,24990,  199920, 0.011,0, 17, 0.000,0
        20150804101346,10.100.13.162,5002,10.100.13.214,47833,11,4.0-5.0,1249500,9996000,0.025,0, 850,0.000,0

        0:  timestamp
        1:  server_ip
        2:  server_port
        3:  client_ip
        4:  client_port
        5:  connection-id (for iperf)
        6:  time-interval
        7:  bytes ?
        8:  bandwidth ?
        9:  jitter ?
        10: lost datagrams ?
        11: total datagrams ?
        12: lost percentage ?
        13: out-of-order diagrams ?
        """

        cols = line.split(",")
        if not is_valid_iperf_udp_line(cols, report_interval):
            continue

        ip, num_bytes = str(cols[3]), int(cols[7])
        uid = ip  # "{}-{}".format(ip, port)

        # iperf date is formatted, get the corresponding unix timestamp
        stamp = time.time() - t0

        val_udp = float(num_bytes * 8) / float(report_interval)

        with sem_data:
            if uid not in data:
                data[uid] = new_client_data()

            intvs = cols[6].split("-")
            intv0 = float(intvs[0])
            intv1 = float(intvs[1])

            """
            UDP is connectionless so the first sample may be lost
            We take as t0 the first datagram effectively arrived
            """
            if intv0 == 0.0 or uid not in tzeros:
                tzeros[uid] = stamp - report_interval

            stamp = tzeros[uid] + intv1

            if uid not in singles:
                singles[uid] = []
            singles[uid] = update_sum(data[uid], t=stamp, val=val_udp, uid=uid, prot="udp", singles=singles[uid])

    print "iperf udp server on port {} terminated".format(port)


"""
Start, parse and save bwm-ng
"""


def bwm_ng_thread(data, interface):
    print "bwm-ng thread started"
    cmd = "bwm-ng -u bits -T rate -t 1000 -I {} -d 0 -c 0 -o csv".format(interface)

    for line in iterate_cmd_out(cmd):
        if stop.is_set():
            break
        """
        example line:
        0          1    2       3         4         5     6   7     8      9      10 11 12  13  14 15
        1437515226;eth0;1620.00;123595.00;125215.00;24719;324;25.00;110.00;135.00;22;5;0.00;0.00;0;0
        1437515226;total;1620.00;123595.00;125215.00;24719;324;25.00;110.00;135.00;22;5;0.00;0.00;0;0

        0: unix timestamp   *
        1: interface
        2: bytes_out/s      *
        3: bytes_in/s
        4: bytes_total/s
        5: bytes_in
        6: bytes_out
        7: packets_out/s
        8: packets_in/s
        9: packets_total/s
        10: packets_in
        11: packets_out
        12: errors_out/s
        13: errors_in/s
        14: errors_in
        15: errors_out

        Timestamps has a resolution in seconds, so we take a report every second

        bwm t0:1437516400.0
        png t0:1437517839.21

        ping stamp:0.200218200684
        bwm stamp: 1.0

        The first (like) 10 timestamps comes at 1ms distance,
        the others every 1sec

        Also if passing the -u bits option, rate reamins is in byte/s

        """
        # Parsing
        if line.find("total") == -1:  # only reports, not the total
            cols = line.split(";")
            stamp = int(cols[0]) - t0
            rate = float(cols[3]) * 8  # conversion byte/s --> bit/s

            with sem_data:
                data["t"].append(stamp)
                data["val"].append(rate)

    print "bwm-ng thread terminated"


"""
data = {
		"tcp"       : {"t":[], "val":[]},
		"udp"       : {"t":[], "val":[]},
		"total"     : {"t":[], "val":[]}
	}
the key "SUM" has only the dict "total"
"""


def execute_matplotlib(data):
    """
    Parameters
    """
    x_lim_left = 0
    x_lim_right = 1
    wtw = 2  # white time window
    wus = 1.1  # white upper space

    """
    Variables initialization
    """
    lines = {}  # lines to plot
    ax = {}  # subplots

    fig = plt.figure(1, figsize=(18, 16))
    plt.ion()
    plt.show(block=False)

    subplots = {
        "tcp-udp": {
            "position": 211,
            "title": "Per-user TCP/UDP raw rate",
            "ylabel": "bit/s"
        },
        "total": {
            "position": 212,
            "title": "Per-user smoothed rate ({}s window)".format(
                (SMOOTH_WINDOW * IPERF_REPORT_INTERVAL) / DENSITY_LINSPACE),
            "ylabel": "bit/s"
        }
    }

    """
    Subplots initialization
    """
    mkfunc = lambda x, pos: '%1.1fM' % (x * 1e-6) if x >= 1e6 else '%1.1fK' % (x * 1e-3) if x >= 1e3 else '%1.1f' % x
    mkformatter = matplotlib.ticker.FuncFormatter(mkfunc)
    for key in subplots:
        ax[key] = fig.add_subplot(subplots[key]["position"])
        ax[key].set_ylabel(subplots[key]["ylabel"])
        ax[key].set_title(subplots[key]["title"])
        ax[key].grid()
        ax[key].yaxis.set_major_formatter(mkformatter)

    fig.subplots_adjust(
        left=0.08,
        bottom=0.03,
        top=0.93,
        right=0.80)

    lines["SUM"] = {}
    lines["SUM"]["total"], = ax["tcp-udp"].plot([], [], label="SUM", color="black")
    print_legend(ax["tcp-udp"], 0)

    print "Matplotlib started"
    while not stop.is_set():
        time.sleep(IPERF_REPORT_INTERVAL)
        if pause.is_set():
            continue

        now = int(time.time() - t0)

        if now > 40 and now < 43:
            plt.savefig("esempio_{}".format(now), format="PDF")

        """
        Update axis and do reset
        """
        x_lim_right = int(now + wtw)

        """
        If x_lim_right exceed max_time_window,
        start to slide:
            - update x_lim_left
            - delete out-of-graph data
        """
        if x_lim_right > max_time_window:
            x_lim_left = x_lim_right - max_time_window

        """
        Update lines
        """
        with sem_data:

            """
            Dinamically set the graph height
            """
            for key in subplots:
                if x_lim_right > max_time_window:
                    if key == "tcp-udp" and len(data["SUM"]["total"]["val"]) > x_lim_left:
                        max_y = np.max(data["SUM"]["total"]["val"][x_lim_left:])
                    else:
                        max_y = 1
                        for uid in data:
                            if uid != "SUM" and len(data[uid]["total"]["val"]) > x_lim_left:
                                new_max = np.max(data[uid]["total"]["val"][x_lim_left:])
                                if new_max > max_y:
                                    max_y = new_max
                else:
                    if key == "tcp-udp" and len(data["SUM"]["total"]["val"]) > 0:
                        max_y = np.max(data["SUM"]["total"]["val"])
                    else:
                        max_y = 1
                        for uid in data:
                            if uid != "SUM" and len(data[uid]["total"]["val"]) > 0:
                                new_max = np.max(data[uid]["total"]["val"])
                                if new_max > max_y:
                                    max_y = new_max

                ax[key].set_ylim(0, max(1, max_y) * wus)
                ax[key].set_xlim(x_lim_left, x_lim_right)

            for src in data:
                if src != "SUM" and src not in lines:
                    lines[src] = {}
                    src_color = ""
                    for key in sorted(data[src]):
                        if key == "tcp":
                            lines[src][key], = ax["tcp-udp"].plot([], [], label=src)
                            src_color = lines[src][key].get_color()
                        elif key == "total":
                            lines[src][key], = ax["total"].plot([], [], color=src_color, antialiased=True)
                        elif key == "udp":
                            lines[src][key], = ax["tcp-udp"].plot([], [], color=src_color, linestyle="--")

                for key in data[src]:
                    first_index = max(0, first_index_geq(data[src][key]["t"], x_lim_left) - 2)
                    last_index = max(0, len(data[src][key]["t"]) - 1)
                    x = list(data[src][key]["t"][first_index:last_index])
                    y = list(data[src][key]["val"][first_index:last_index])

                    if src != "SUM" and key == "total" and len(x) > (SMOOTH_WINDOW / DENSITY_LINSPACE) + 1:
                        f = interpolate.interp1d(x, y)
                        new_x = np.linspace(min(x), max(x), (x_lim_right - x_lim_left) * DENSITY_LINSPACE)
                        new_y = smooth(f(new_x), window_len=SMOOTH_WINDOW)
                        lines[src][key].set_data(new_x, new_y)
                    else:
                        lines[src][key].set_data(x, y)

        print_legend(ax["tcp-udp"], update_alive_flows(data))
        fig.canvas.draw()

    plt.close()
    print "Matplotlib terminated"


def update_alive_flows(data):
    num = 0
    with sem_data:
        now = time.time() - t0
        del clients_id[:]
        for src in data:
            if src != "SUM":
                for key in data[src]:
                    if (len(data[src][key]["t"]) > 0 and
                                abs(now - data[src][key]["t"][-1]) <= DEATH_TOLERANCE * 4 and
                                data[src][key]["val"][-1] > 0):
                        clients_id.append(src)
                        break
        num = len(clients_id)
    return num


def new_client_data():
    data = {
        "tcp": {"t": [], "val": []},
        "udp": {"t": [], "val": []},
        "total": {"t": [], "val": []},
    }
    return data


def set_data():
    data = {}
    data["SUM"] = {"total": {"t": [], "val": []}}
    return data


def keyboard_listener_thread():
    print "Keyboard listener started"
    quit = "q"
    save = "s"
    p = "p"
    cmd = ""
    try:
        while cmd != quit:
            cmd = str(raw_input("Command: "))
            if cmd == quit:
                stop_server()
            elif cmd == p:
                if pause.is_set():
                    pause.clear()
                else:
                    pause.set()
            elif cmd == save:
                plt.savefig("plot-" + str(time.time()) + ".pdf", format="PDF")

    except (KeyboardInterrupt):  # executed only in case of exceptions
        stop_server()
    finally:
        print "Keyboard listener terminated"


def check_number_of_users(data, expected_users):
    if update_alive_flows(data) < expected_users:
        stop_server()


def run_server(interface, tcp_ports, udp_ports, interactive, duration, do_visualize, expected_users=-1, check_time=1):
    pause.clear()
    stop.clear()
    data = set_data()
    singles = {}  # timestamps of sums executed without an element for each uid
    threads = {}
    killall("iperf")
    killall("bwm-ng")
    global t0
    t0 = time.time()

    threads["bwm-ng"] = threading.Thread(target=bwm_ng_thread, args=(data["SUM"]["total"], interface))

    for p in tcp_ports:
        threads["iperf_tcp_" + str(p)] = threading.Thread(target=iperf_tcp_thread, args=(data, p, singles))
    for p in udp_ports:
        threads["iperf_udp_" + str(p)] = threading.Thread(target=iperf_udp_thread, args=(data, p, singles))

    # if interactive, no timer is used because the user will stop the server
    timer = Timer(duration, stop_server)
    first_check = Timer(check_time, check_number_of_users, args=(data, expected_users))
    if interactive:
        threads["keyboard"] = threading.Thread(target=keyboard_listener_thread)
    else:
        timer.start()
        if expected_users > 0:
            first_check.start()

    # start threads and matplotlib
    for t in threads:
        threads[t].start()
    if do_visualize:
        execute_matplotlib(data)

    # wait for the end of the experiment
    try:
        print "Running server processes..."
        while not stop.is_set():
            time.sleep(1)
            # it should be stop.wait()
    except (KeyboardInterrupt):  # executed only in case of exceptions
        print "Server interrupted by user"
        stop_server()
        data = None
    finally:
        print "Server terminated"
        timer.cancel()
        killall("iperf")
        killall("bwm-ng")
        return data


def stop_server():
    stop.set()
    print 'caller name:', inspect.stack()[1][3]


def main(argv):
    tcp_ports = [5001]
    udp_ports = [5002]
    interface = "eth0"
    interactive = True
    duration = 0
    do_visualize = True
    help_string = "Usage: plot_server.py -i <interface> -t <tcp ports> -u <udp ports> \
	-v <do-visualize> -d <duration> -x <interactive>"

    try:
        opts, args = getopt.getopt(argv, "hi:t:u:v:d:x:")
    except getopt.GetoptError:
        print help_string
        sys.exit(2)

    for opt, arg in opts:
        if opt == '-h':
            print help_string
            sys.exit()
        elif opt in ("-i"):
            interface = arg
        elif opt in ("-t"):
            tcp_ports = arg.split(",")
        elif opt in ("-u"):
            udp_ports = arg.split(",")
        elif opt in ("-v"):
            do_visualize = my_bool(arg)
        elif opt in ("-d"):
            duration = int(arg)
        elif opt in ("-x"):
            interactive = my_bool(arg)

    run_server(interface, tcp_ports, udp_ports, interactive, duration, do_visualize)


if __name__ == "__main__":
    main(sys.argv[1:])
