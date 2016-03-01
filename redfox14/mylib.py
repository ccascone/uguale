import os, re, pexpect, subprocess, math, time
import numpy as np

FNULL = open(os.devnull, "w")
NETWORK_PREFIX = "192.168.200"
NETWORK_PREFIX_16 = "192.168"

"""
TO UPDATE IN COUPLE!
"""
HOST_IDS = [1,3]
STARTING_IPS = [110,130] 

SERVER_ID = 4
SWITCH_ID = 98
SERVER_IP = "{}.{}".format(NETWORK_PREFIX, SERVER_ID)
SWITCH_IP = "{}.{}".format(NETWORK_PREFIX, SWITCH_ID)
# debug = False
FIRST_TCP_PORT = 5001
FIRST_UDP_PORT = 5201
NUM_VETHS = 10
HZ 	= 250 	# [Hz] frequency of tokens update
MTU = 1500 	# [Byte] maximum transfer unit of the physical layer
UDP_PACKET_SIZE = 1470 		# [Byte] packet size of UDP datagrams genererated by iperf
MAX_PACKET_SIZE = 64*1024 	# [Byte] maximum packet size of TCP packets [at 1Gbps]

NO_MARKERS = "no_markers"
BUCKETS_MARKERS = "buckets_markers"
IPTABLES_MARKERS = "iptables_markers"
PYTHON_MARKERS = "python_markers"

TECH_OVS = "ovs"
TECH_BR = "br"
TECH_VLANS = "vlans"
TECH_NONE = "none"

IPERF_REPORT_INTERVAL = 1 
DURATION = 180 # duration of tests
MAX_TRIES = 3 # max failed tries to declare a test/configuration failed

STARTING_IP = 110 # first emulated host is .110
RTT_NO_NETEM = 0.3 # rtt to be saved if netem is not used

STANDALONE = "standalone"
UGUALE = "uguale"

RESULTS_CSV_FILENAME = "results.csv"

RECORD_BEGIN 	= 35 # seconds to discard at the begin
RECORD_END 		= 3*IPERF_REPORT_INTERVAL # seconds to discard at the end
BIRTH_TIMEOUT = 20 # every user must be born within this interval
HIST_BINS = 500 # width of histogram steps
DISTR_BINS = HIST_BINS*10 # width of distribution steps
REF_MEAN = 0 # the reference distribution has zero mean
REF_STD_DEV = 0.001 # the reference distribution has a low standard deviation

SYNC_TIME = 10


PARAMS_COLUMNS = [
	"start_ts", "cookie", "switch_type", "bn_cap", "free_b",
	"vr_limit", "n_users","range_rtts", "range_conns",
	"duration", "marking", "bands","comp_rtt","strength","guard_bands",
	"queuelen", "queuelen_switch", "tech"]

STATS_COLUMNS = [
	"jain_idx_mean","jain_idx_var", 
	"ratio_gt_mean","ratio_gt_var",
	"global_mean", "global_var","global_std","global_percentile", "global_abs_mean", 
	"distr_corr","samples_per_user"]


# pc1 --->192.168.200.1 ---> [110,119]
# pc2 --->192.168.200.2 ---> [120,129]
# pc3 --->192.168.200.3 ---> [130,139]
ADDRESSES = {}
index_pc = 0
for pc in HOST_IDS:
	pc_ip = "{}.{}".format(NETWORK_PREFIX,pc)
	ADDRESSES[pc_ip] = []
	for i in range(NUM_VETHS):
		addr_id = STARTING_IPS[index_pc] + i
		addr_str = "{}.{}".format(NETWORK_PREFIX,addr_id)
		ADDRESSES[pc_ip].append(addr_str)
	index_pc +=1

#------------------------ PRINTING/CONVERSIONS -------------------------#

"""
Conversion es. "45.5m"--> 45500000
The rate can contain an integer.
Return an int because a bitrate is always integer
"""
def rate_to_int(rate_str):
	try:
		return int(float(rate_str))
	except ValueError:
		regex_rate = re.compile("([0-9]{1,20}.[0-9]{1,20})([m,g,k]{0,1})")
		m = regex_rate.match(rate_str)
		num = float(m.groups()[0])
		mult = m.groups()[1]

		if mult=="k":
			return int(num*10**3)
		if mult=="m":
			return int(num*10**6)
		if mult=="g":
			return int(num*10**9)

"""
Conversion es. 1000-->1.0k
"""
def num_to_rate(rate_int):
	if rate_int<10**3:
		return str(rate_int)
	if rate_int<10**6:
		return str(rate_int/10.0**3)+"k"
	if rate_int<10**9:
		return str(rate_int/10.0**6)+"m"
	return str(rate_int/10.0**9)+"g"

"""
Conversion es. 1000-->1k
"""
def num_to_rate_int(rate_int):
	if rate_int<10**3:
		return str(int(rate_int))
	if rate_int<10**6:
		return str(int(rate_int/10**3))+"k"
	if rate_int<10**9:
		return str(int(rate_int/10**6))+"m"
	return str(int(rate_int/10**9))+"g"

"""
Insert a timestamp and a return.
"""
def my_log(text,t0=0):
	print "{}: {}\r".format(time.time()-t0,text)


#------------------------ EXECUTION OF EXTERNAL PROGRAMS -------------------------#

"""
Executes a programm (command string) and returns output lines
"""
def runPexpect(exe):
	child = pexpect.spawn(exe, timeout = None)
	for line in child:
		yield line

"""
Executes a command in background (no output!)
"""
def launch_bg(command, do_print=False):
	if do_print:
		print command
	return subprocess.Popen(command.split(),stdout=FNULL)


"""
Execute a command in the terminal
"""
def cmd(command):
	subprocess.call(command, shell=True) 

def sudo_cmd(command):
	subprocess.call("sudo {}".format(command), shell=True) 

"""
Open a new terminal (xterm) and execute an ssh commands from it
"""
# def cmd_ssh(pc_ip,command):
# 	cmd_str = "(xterm -hold -e \"ssh {} '{}'\") & ".format(pc_ip, command)
# 	cmd(cmd_str)
# 	print cmd_str

# def cmd_ssh(pc_ip,command):
# 	cmd_str = "ssh {} '{}' &".format(pc_ip, command)
# 	cmd(cmd_str)
# 	print cmd_str



# def cmd_ssh2(pc_ip,command):
# 	cmd_str = "ssh {} '{}' &".format(pc_ip, command)
# 	cmd(cmd_str)
# 	print cmd_str

def cmd_ssh(host, remoteCmd):
	# localCmd = "/usr/bin/ssh", host, "<<", "EOF\n{}\nEOF".format(remoteCmd)
	localCmd = "/usr/bin/ssh", host, remoteCmd
	print "*** Executing SSH command: {}".format(localCmd)
	try:
		result = subprocess.check_output(
			localCmd, stderr=subprocess.STDOUT, shell=False)
	except subprocess.CalledProcessError as e:
		result = e.output
		print "*** Error with SSH command {}: {}".format(localCmd, result)
	return result


def cmd_ssh_bg(host, remoteCmd):
	# localCmd = "/usr/bin/ssh", host, "<<", "EOF\n{}\nEOF".format(remoteCmd)
	localCmd = "/usr/bin/ssh", host, remoteCmd
	print "*** Executing SSH command in BG: {}".format(localCmd)
	subprocess.Popen(
			localCmd, stdout=FNULL, stderr=FNULL, shell=False)


#------------------------ OTHER UTILITIES -------------------------#

""" 
Effectivelly kill all process with given name 
and optional arguments (used to launch the process)
"""
def killall(process_name, arg=None):
	if arg is not None:
		grep_str = "{}.*{}".format(process_name, arg)
	else:
		grep_str = str(process_name)
	cmd_str = "for pid in $(ps -ef | grep \""+grep_str+"\" | awk '{print $2}'); do sudo kill -9 $pid; done"
	cmd(cmd_str)


"""
Appenzeller:
q_opt= (RTT*C)/sqrt(n_flows)
"""
def optimal_queue_len(rtts, conns, C):
	rtt_sec = np.mean(rtts)/1000.0
	num_flows = np.sum(conns)
	length_bit = (rtt_sec*C)/float(math.sqrt(num_flows))
	length_pacc = int(length_bit/float(8*MTU)) # bit --> bytes --> packets
	# print rtt_sec, num_flows, C, length_bit, length_pacc
	length_pacc = max(num_flows*2, length_pacc) 
	return min(length_pacc, 10000)

def limit_interface(limit, intf):
	if limit=="100.0m":
		sudo_cmd("ethtool -s {} advertise 0x008 autoneg on speed 100 duplex full".format(intf))
	else:
		sudo_cmd("ethtool -s {} advertise 0x020 autoneg on speed 1000 duplex full".format(intf))

def update_hosts_code():
	for host in ADDRESSES:
		cmd("scp *.py redfox@{}:~".format(host))	
		cmd("scp *.sh redfox@{}:~".format(host))	

"""
The script called prepare the PCs to emulate many users
with the passed technology
"""
def set_up_hosts(tech):
	for host in sorted(ADDRESSES):
		str_ssh = "python set_up_host.py -s{} -t{}".format(host,tech)
		cmd_ssh(host, str_ssh)

"""
This code must be mantained on a separate script
because we will temporary lose connection with the PC.
It simply delete OVS on the pc
"""
def reset_hosts():
	for host in sorted(ADDRESSES):
		str_ssh = "sudo sh /redfox-automations/all/reset_net_conf"
		cmd_ssh_bg(host, str_ssh)

def reset_switch():
	cmd_ssh_bg(SWITCH_IP,"sudo sh reset_redfox0.sh")
	time.sleep(2)


def reboot_redfox14():
	cmd_ssh_bg(SWITCH_IP,"sudo sh /redfox-automations/redfox0/reboot_redfox14")
	time.sleep(2)


def get_instance_name(configuration):
	params_filename = [
		["cookie", 			"test"	],
		["bn_cap", 			"cap"	],
		["free_b",			"fb"	], 	
		["users_p_h", 		"uph"	],
		["range_rtts", 		"rtt"	],
		["range_conns", 	"conn"	],
		["duration", 		"dur"	],
		["repetition", 		"rep"	],
		["bands",			"b"		],
		["guard_bands", 	"gb"	],
		["marking", 		"mr"	],
		["tech",			"tc"	],
		["queuelen",		"q"		],
		["queuelen_switch",	"qsw"	],
		["switch_type",		"t"		],
		["comp_rtt",		"crtt"	],
		["strength", 		"s"],
	]
	instance_name = ""
	for key in params_filename:
		param = key[0]
		short_name = key[1]
		value = str(configuration[param]).replace(" ","") 
		instance_name += ("{}{}_".format(short_name,value))
	instance_name = instance_name[:-1]
	return instance_name


def set_queuelen(intf, length):
	sudo_cmd("ifconfig {} txqueuelen {}".format(intf, int(length)))	

def my_bool(val):
	if val in ["True","true",True,1]:
		return True
	return False

def cast_value(value):
	if isinstance(value,list) or isinstance(value,tuple):
		# i'm a list
		return [cast_value(v) for v in value]
	elif isinstance(value, dict):
		return {key:cast_value(value[key]) for key in value}
	else:
		# i'm a scalar
		value = str(value)
		try:
			return int(value)
		except ValueError:
			try:
				return round(float(value),3)
			except ValueError:
				regex_float_rate = re.compile("([0-9]{1,20}.[0-9]{1,20})([m,g,k]{0,1})")
				m = regex_float_rate.match(value)
				if m:
					return "{:.3f}{}".format(float(m.groups()[0]), m.groups()[1])
				else:
					return value