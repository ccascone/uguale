#!/usr/bin/python
import time, threading, os, pickle, random, sys, getopt, datetime
import plot_server as ps
import marking_lib as ml
import view_result as vr
from mylib import *

"""
Pass parameters to hosts
"""
def clients_thread(params):
	time.sleep(1) # Let the server start 
	g_rates = list(params["g_rates"])
	fixed_rtts = list(params["fixed_rtts"])
	fixed_conns = list(params["fixed_conns"])
	m_m_rates = list(params["m_m_rates"])
	e_f_rates = list(params["e_f_rates"])
	list_users = list(params["list_users"])

	for user_index in range(len(list_users)):

		n_host = list_users[user_index] # n of clients to emulate on the pc
		if n_host == 0:
			continue

		ip_address = (sorted(ADDRESSES))[user_index]
		fixed_rtts_host = []
		fixed_conns_host = []	
		g_rates_host = []	
		m_m_rates_host = []
		e_f_rates_host = []

		for i in range(n_host):
			fixed_rtts_host.append(fixed_rtts.pop(0))
			fixed_conns_host.append(fixed_conns.pop(0))	
			g_rates_host.append(g_rates.pop(0))
			m_m_rates_host.append(m_m_rates.pop(0))
			e_f_rates_host.append(e_f_rates.pop(0))

		str_ssh = "python start_users.py -d{} -t{} -P{} -T{} -C{} -m{} -b{} -G{} -M{} -E{} -Q{} -K{}".format(
			params["duration"],	params["start_ts"],

			",".join(map(str, fixed_conns_host)),
			",".join(map(str, fixed_rtts_host)),
			params["vr_limit"], params["markers"],

			params["bn_cap"],
			",".join(g_rates_host),
			",".join(m_m_rates_host),
			",".join(e_f_rates_host),
			params["num_bands"], params["do_symm"])

		cmd_ssh_bg(ip_address, str_ssh)	

def start_test(
		folder, cookie, do_save, do_visualize,
		range_conns, list_conns, range_rtts, list_rtts, list_users,
		vr_limit, list_markers,
		list_queuelen, switch_type,
		list_num_bands, list_guard_bands, bn_cap, 
		list_free_b, list_do_comp_rtt, do_symm, list_symm_width):

	# ------------------------------------ RESET THE NETWORK --------------------------------
	reset_switch()
	reset_pcs()
	for host in ADDRESSES:
		cmd("scp *.py redfox@{}:~".format(host))	
		cmd("scp *.sh redfox@{}:~".format(host))

	strength = 0.15
	repetitions = 1
	n_users = sum(list_users)
	tech = TECH_OVS

	if len(list_conns)>0:
		do_use_conns_list = True
	else:
		do_use_conns_list = False

	if len(list_rtts)>0:
		do_use_rtts_list = True
	else:
		do_use_rtts_list = False

	# ------------------------------------ PREPARE TEST CONFIGURATIONS --------------------------------
	"""
	Generate the configurations list
	"""
	configurations = []

	for markers in list_markers:
		for queuelen in list_queuelen:
			for num_bands in list_num_bands:
				for guard_bands in list_guard_bands:
					for free_b in list_free_b:
						for symm_width in list_symm_width:
							for do_comp_rtt in list_do_comp_rtt:

								# ----------- Skip useless standalone configs. ----------
								if switch_type == STANDALONE:
									if (
										(len(list_markers)>1 and markers != NO_MARKERS) or
										(num_bands != list_num_bands[0]) or									
										(free_b != list_free_b[0]) or 
										(guard_bands != list_guard_bands[0]) or
										(free_b != list_free_b[0]) or 
										(do_comp_rtt != list_do_comp_rtt[0])
									):					
										print "Wrong standalone configuration, skip test"
										continue
								# ----------- Skip useless uguale configs. ----------
								else:
									if markers == NO_MARKERS:
										print "UGUALE without markers, skip test"
										continue

									if guard_bands>num_bands:
										print "guard_bands > num_bands, skip test"
										continue	

									if do_symm and num_bands % 2!=0:
										print "Only even num_bands, skip test"
										continue

								# ----------------TCP CONNECTIONS ---------------
								fixed_conns = []
								if not do_use_conns_list:
									delta_conns = range_conns[1]-range_conns[0]
									if delta_conns == 0:
										fixed_conns = [range_conns[0]]*n_users
									else:
										"""
										es. range=[2,8] = (2,3,4,5,6,7,8)
										#uguali=len(users)/delta(range) 
										7 users --> (2,3,4,5,6,7,8)
										9 users --> (2,3,4,5,6,7,8,2,3)
										if not divisible, return to random
										"""
										conn_list = range(range_conns[0], range_conns[1]+1)
										i=0
										for u in range(n_users):
											fixed_conns.append(conn_list[i])
											i=(i+1) % len(conn_list)
										random.shuffle(fixed_conns)	
								else:
									fixed_conns = list_conns
									range_conns = [min(list_conns), max(list_conns)]	

								# ------------------------ RTTS ----------------------
								"""
								If the range has zero difference, all users have the same rtt
								If not, RTTs will be equally distributed in the range
								"""	
								fixed_rtts = []
								if not do_use_rtts_list:
									delta_rtts = range_rtts[1]-range_rtts[0]
									if delta_rtts == 0:
										fixed_rtts = [range_rtts[0]]*n_users
									else:
										step = delta_rtts/float(n_users-1)
										for i in range(n_users):
											fixed_rtts.append(range_rtts[0]+(i*step))	
										random.shuffle(fixed_rtts)
								else:
									fixed_rtts = list_rtts
									range_rtts = [min(list_rtts), max(list_rtts)]

								if (len(set(fixed_rtts))==1 and 
									len(list_do_comp_rtt)>1 and 	
									do_comp_rtt):
									print "Useless RTT compensation, skip test"
									continue

								# --------------- BANDS ASSIGNMENT ----------------

								g_rates = [] # guaranteed rates
								e_f_rates = [] # expected fair rates
								m_m_rates = [] # maximum markers rates
								coeffs = [] # compensate rtt coefficients

								C = rate_to_int(bn_cap)
								free_C = C*(1.0 - free_b) # capacity to use for guaranteed rates
								g_rate = free_C/float(n_users)
								g_rates = [num_to_rate(g_rate)]*n_users

								e_f_rate = C/float(n_users)
								e_f_rates = [num_to_rate(e_f_rate)]*n_users

								m_m_rate = ml.get_marker_max_rate(
										C, n_users, g_rates, e_f_rates, 
										num_bands, guard_bands, do_symm, symm_width) 

								"""
								Detect if symmetric_width was modified
								and write a consistent value
								"""	
								symw = symm_width
								if do_symm:
									if num_bands == 2: # all the bandwidth is used
										symw = num_to_rate(m_m_rate)
									else:
										symw_i = rate_to_int(symw)
										symw = num_to_rate(min(symw_i, m_m_rate))

								# --------------- RTT COMPENSATION ----------------
								coeffs = [1]*n_users
								if do_comp_rtt and not do_symm:
									coeffs = ml.get_rtt_coefficients(
											fixed_rtts, C, n_users, strength)

								for i in range(n_users):						
									m_m_rate = m_m_rate * coeffs[i]								
									m_m_rates.append(num_to_rate(m_m_rate))

								if queuelen == -1:
									qsw = optimal_queue_len(fixed_rtts, fixed_conns, C)
								else:
									qsw = queuelen

								# --------------- SAVE EFFECTIVE PARAMETERS ----------------
								configuration={
									"cookie"		: cookie, 

									"fixed_conns"	: fixed_conns, 	
									"fixed_rtts"	: fixed_rtts, 
									"list_users"	: list_users,
									"n_users"		: n_users,
									"range_conns"	: range_conns,
									"range_rtts"	: range_rtts,

									"vr_limit"		: vr_limit, 
									"markers"		: markers,
									"tech"			: tech,

									"queuelen"		: qsw,
									"switch_type"	: switch_type,

									"num_bands"		: num_bands,
									"guard_bands"	: guard_bands,
									"bn_cap"		: bn_cap, 	
									"free_b"		: free_b, 
									"do_comp_rtt" 	: do_comp_rtt,
									"strength"		: strength,
									"do_symm"		: do_symm,
									"symm_width"	: symw,

									"g_rates"		: g_rates, 				
									"m_m_rates"		: m_m_rates,
									"e_f_rates"		: e_f_rates,

									"duration"		: DURATION
								}

								configurations.append(configuration)

	random.shuffle(configurations)	

	"""
	Calculate Estimated time
	"""
	num_tests = len(configurations)

	if num_tests == 0:
		print "No tests, exit"
		return

	secs = num_tests*DURATION
	print "{} Tests, total duration: {}".format(
		num_tests, datetime.timedelta(seconds=secs))

	"""
	Set the network
	"""
	limit_interface(vr_limit, "eth0")

	if tech == TECH_OVS:
		i = 0
		for ip_address in sorted(ADDRESSES):
			if list_users[i] > 0:
				str_ssh = "python create_ovs_and_veths.py -s{}".format(ip_address)
				cmd_ssh(ip_address, str_ssh)
			i += 1

	if switch_type == UGUALE:
		# Start the controller
		cmd_ssh_bg(
			SWITCH_IP, 
			"sudo ryu-manager /home/redfox/controller_code/uguale.py")
		time.sleep(2)

		# Put the switch in UGUALE mode
		cmd_ssh(
			SWITCH_IP,  
			"python config_ovs_uguale.py -c{} -q{} -n{}".format(
				"127.0.0.1:6633",
				100,
				MAX_NUM_BANDS))

	try:
		for repetition in range(repetitions):
			for configuration in configurations:
				configuration["repetition"] = repetition
				instance_name = get_instance_name(configuration)
				pickle_name = "{}.p".format(instance_name)
				file_name = "{}/{}".format(folder, pickle_name)

				if os.path.isfile(file_name):
					print "Skip, existing test instance {}".format(instance_name)
					continue

				# ---------------------- CONFIGURE SWITCH ----------------------#

				print("Executing {} ...".format(instance_name))
				print configuration

				print "Configuring queues on the switch"
				if configuration["switch_type"] == STANDALONE:					
					cmd_ssh(
						SWITCH_IP, 
						"sudo sh set ovs_standalone_queues.sh {}".format(configuration["queuelen"]))

				elif configuration["switch_type"] == UGUALE:
					cmd_ssh(
						SWITCH_IP,  
						"python set_ovs_uguale_queues.py -q{} -n{}".format(
							configuration["queuelen"],
							MAX_NUM_BANDS))

				for curr_try in range(MAX_TRIES):
					print "Try number {}...".format(curr_try)

					configuration["start_ts"] = time.time()+SYNC_TIME
					clients=threading.Thread(target=clients_thread, args=(configuration,))
					clients.start()

					tcp_ports = range(FIRST_TCP_PORT, FIRST_TCP_PORT+max(list_users))
					udp_ports = []

					print "Starting the server"
					data = ps.run_server(
						"eth0", tcp_ports, udp_ports,
						interactive=False, 
						duration=configuration["duration"]+SYNC_TIME+2, 
						do_visualize=do_visualize,
						expected_users=n_users,
						check_time=BIRTH_TIMEOUT + SYNC_TIME)

					# ---------------------- SAVING ----------------------#				
					test={"params": configuration, "data": data}

					if vr.test_is_valid(test):
						print "Valid test"
						if do_save:
							if not os.path.exists(folder):
								os.makedirs(folder)
							# Save the test in a file
							pickle.dump(test, open(file_name, "wb"))
							# append results to CSV
							stats = vr.get_stats(test)
							append_to_csv(configuration, stats)
						break # exit from current tries
					else:
						print "Errors in data, test failed"
						if curr_try == MAX_TRIES-1:
							print "Test failed too many times... skipping to next test!"
							append_to_csv(configuration, [])
	except (KeyboardInterrupt, SystemExit):
		print "Test interrupted"
	finally:
		print "Test terminated"
		reset_switch()
		reset_pcs()
		limit_interface("1g", "eth0")


def main(argv):

	help_string = "TEST PARAMETERS:\n\
	-f<folder> -c<cookie> -s<do save> -v<do visualize>\n\
	USERS:\n\
	-p<range conns:L> -P<list conns:L>\n\
	-t<range rtts:L>  -T<list rtts:L>\n\
	-u<users for each pc:L>\n\
	USER FEATURES:\n\
	-C<interface limit>\n\
	-m<markers:no_markers/buckets_markers/iptables_markers:L>\n\
	SWITCH:\n\
	-q<queue lenght:L> -S<standalone/uguale>\n\
	BANDS ASSIGNMENT:\n\
	-Q<number of bands:L> 	-g<guard bands:L>\n\
	-b<bottleneck capacity> -F<free bandwidth:L>\n\
	-r<do compensate rtt:L>\n\
	-k<do do_symm bands assignment> -w<symmetric width:L>\n\
	\n\
	NOTES:\n\
	- If conns/rtts lists are given, ranges are not considered\n\
	- Queue lenght can be a number or -1 to use the optimal value\n\
	- Parameters marked with <:L> can be lists"

	try:
		opts, args = getopt.getopt(argv,
			"hf:c:s:v:p:P:t:T:u:C:m:q:S:Q:g:b:F:r:k:w:")
	except getopt.GetoptError:
		print help_string
		sys.exit(2)

	# --------------- DEFAULT VALUES -------------
	folder = str(time.time)
	cookie = "test"
	do_save = False
	do_visualize = False

	range_conns = []
	list_conns = []
	range_rtts = []
	list_rtts = []
	list_users = [1, 1, 1]

	vr_limit = "100m"
	list_markers = ["no_markers"]

	list_queuelen = [-1]
	switch_type = "standalone"

	list_num_bands = [8]
	list_guard_bands = [2]
	bn_cap = "94.1m"
	list_free_b = [0.5]
	list_do_comp_rtt = [False]
	do_symm = False
	list_symm_width = ["20m"]

	for opt, arg in opts:
		if opt == '-h':
			print help_string
			sys.exit()

		elif opt in ("-f"):
			folder = arg
		elif opt in ("-c"):
			cookie = arg
		elif opt in ("-s"):
			do_save = my_bool(arg)
		elif opt in ("-v"):
			do_visualize = my_bool(arg)

		elif opt in ("-p"):
			range_conns = map(int, arg.split(","))
		elif opt in ("-P"):
			list_conns = map(int, arg.split(","))
		elif opt in ("-t"):
			range_rtts = map(float, arg.split(","))
		elif opt in ("-T"):
			list_rtts = map(float, arg.split(","))
		elif opt in ("-u"):
			list_users = map(int, arg.split(","))

		elif opt in ("-C"):
			vr_limit = arg
		elif opt in ("-m"):
			list_markers = arg.split(",")

		elif opt in ("-q"):
			list_queuelen = map(int, arg.split(","))
		elif opt in ("-S"):
			switch_type = arg

		elif opt in ("-Q"):
			list_num_bands = map(int, arg.split(","))
		elif opt in ("-g"):
			list_guard_bands = map(int, arg.split(","))
		elif opt in ("-b"):
			bn_cap = arg
		elif opt in ("-F"):
			list_free_b = map(float, arg.split(","))
		elif opt in ("-r"):
			list_do_comp_rtt = map(my_bool, arg.split(","))	
		elif opt in ("-k"):
			do_symm = my_bool(arg)
		elif opt in ("-w"):
			list_symm_width = arg.split(",")

	n_users = sum(list_users)

	if((len(range_rtts)==0 and len(list_rtts)==0) # no rtt given
	or (len(range_conns)==0 and len(list_conns)==0) # no conns given
	or (len(range_conns)>0 and len(range_conns)!=2) # range must have 2 boundaries
	or (len(range_rtts)>0 and len(range_rtts)!=2)  # range must have 2 boundaries
	or (len(list_rtts)>0 and len(list_rtts)!= n_users) # the list should have a value for each user
	or (len(list_conns)>0 and len(list_conns)!= n_users) # the list should have a value for each user
	or (len(list_users)!=len(HOST_IDS))): # a number for each PC
		print "Wrong users configuration"
		print help_string
		sys.exit(2)	

	for marker in list_markers:
		if marker not in MARKING_TYPES:
			print "Wrong markers type"
			print help_string
			sys.exit(2)	

	if switch_type not in SWITCH_TYPES:
		print "Wrong switch type"
		print help_string
		sys.exit(2)	

	if max(list_num_bands)>MAX_NUM_BANDS:
		print "The maximim number of bands is {}".format(MAX_NUM_BANDS)
		print help_string
		sys.exit(2)	

	print(
		folder, cookie, do_save, do_visualize,
		range_conns, list_conns, range_rtts, list_rtts, list_users,
		vr_limit, list_markers,
		list_queuelen, switch_type,
		list_num_bands, list_guard_bands, bn_cap, 
		list_free_b, list_do_comp_rtt, do_symm, list_symm_width)

	start_test(
		folder, cookie, do_save, do_visualize,
		range_conns, list_conns, range_rtts, list_rtts, list_users,
		vr_limit, list_markers,
		list_queuelen, switch_type,
		list_num_bands, list_guard_bands, bn_cap, 
		list_free_b, list_do_comp_rtt, do_symm, list_symm_width)

if __name__ == "__main__":
	main(sys.argv[1:])
