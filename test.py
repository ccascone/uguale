#!/usr/bin/python
import plot_server as ps
import numpy as np
from mylib import *
from marking_lib import *
import time, threading, os, pickle, random, sys, getopt, datetime
import view_result as vr


def append_to_csv(params, stats):

	rows_to_write = []
	if not os.path.isfile(RESULTS_CSV_FILENAME):
		rows_to_write.append(PARAMS_COLUMNS+STATS_COLUMNS)

	rows_to_write.append([])
	for key in PARAMS_COLUMNS:
		if key in params:
			value = params[key]
		elif key not in params and key == "bands":
			value = 8 
		elif key not in params and key == "strength":
			value = 1 
		else:
			value = "unknown"
		rows_to_write[-1].append(value)

	if len(stats)>0:
		rows_to_write[-1].extend([stats[c] for c in STATS_COLUMNS])
	else:
		rows_to_write[-1].extend([-1]*len(STATS_COLUMNS))

	with open(RESULTS_CSV_FILENAME,"a") as f:
		for row in rows_to_write:
			f.write(";".join(map(str, row))+"\n")


"""
Pass parameters to hosts
"""
def clients_thread(params):
	time.sleep(2)
	"""
	Extract data from params
	"""
	g_rates = list(params["g_rates"])
	fixed_rtts = list(params["fixed_rtts"])
	fixed_conns = list(params["fixed_conns"])
	m_m_rates = list(params["m_m_rates"])

	"""
	Example:
	host_idxs = [1,2,3]
	fixed_rtts = [1,2,3,4,5,6,7,8,9]
	              ----- ----- -----
	                h1    h2   h3	
	"""
	for host in sorted(ADDRESSES):
		fixed_rtts_host = []
		fixed_conns_host = []	
		g_rates_host = []	
		m_m_rates_host = []
		for i in range(params["users_p_h"]):
			fixed_rtts_host.append(fixed_rtts.pop(0))
			fixed_conns_host.append(fixed_conns.pop(0))	
			g_rates_host.append(g_rates.pop(0))
			m_m_rates_host.append(m_m_rates.pop(0))

		str_ssh = "python start_users.py -s{} -g{} -C{} -P{} -l{} -f{} -d{} -m{} -M{} -q{} -t{} -S{} -Q{}".format(
			host, 
			",".join(g_rates_host), # ---> from here we obtain users per host
			params["bn_cap"], #-C
			",".join(map(str, fixed_conns_host)), #-P
			params["vr_limit"], #-l
			",".join(map(str,fixed_rtts_host)), #-f
			params["duration"],#-d
			params["marking"], #-m
			",".join(m_m_rates_host), #-M
			params["queuelen"], #-q
			params["tech"], #-t
			params["start_ts"],#-S
			params["bands"]) 

		print str_ssh

		cmd_ssh(host, str_ssh)	

		print "Called {}".format(host)



def start_test(folder, cookie, do_save, range_conns, range_rtts, list_rtts, 
	list_conns, bn_cap, vr_limit, users_phs, free_bs, repetitions, various_guaranteed, 
	queuelens, gbs, comp_rtts, visualizations, queuelens_switch, switch_types, markers,colors):

	restore_switch()
	restore_hosts()
	killall("iperf")
	killall("xterm")
	killall("bwm-ng")
	# restore_hosts() # delete ovs on hosts
	update_hosts_code() # send the update programs code to all PCs

	#------------------------------------ TECHNOLOGY SETTINGS --------------------------------
	"""
	How to emulate many users
	ovs: veths linked with ovs to eth0
	br: same as before, but with linux bridge
	vlans: veths used by vlans
	none: no veth are created
	"""
	tech= TECH_OVS

	#------------------------------------ BEGIN TEST --------------------------------

	"""
	We can have two modalities for both rtt and conns:
	- rtt and conns will vary in a range : in each instance users will have values distributed in the range
	- rtt and conns will be fixed : in each instance every user will have the same value (baselines)
	This setting is automatic and based on the LISTS passed
	"""
	if len(list_rtts)==0:
		list_rtts=[0]
		keep_same_rtts = False
	else:
		keep_same_rtts = True

	if len(list_conns)==0:
		list_conns=[0]
		keep_same_conns = False
	else:
		keep_same_conns = True

	"""
	Rate limit the bottleneck link 
	"""
	limit_interface(vr_limit,"eth0")

	"""
	Generate the configurations list
	"""
	configurations = []
	for visualization in visualizations:
		for free_b in free_bs:
			for users_ph in users_phs:							
				for conns in list_conns:
					for rtts in list_rtts:	
						for guard_bands in gbs:
							for comp_rtt in comp_rtts:	
								for queuelen in queuelens:
									for queuelen_switch in queuelens_switch:
										for switch_type in switch_types:
											for num_colors in colors:
												for marking in markers:
													for strength in [0.15]:

														"""
														How to mark packets
														BUCKETS_MARKERS cascade of token bucket filters
														IPTABLES_MARKERS iptables estimator
														NO_MARKERS
														"""

														"""
														Certain parameters are useless in standalone mode so we skip combinations.
														"""
														if switch_type == STANDALONE:
															if (marking != NO_MARKERS or free_b != free_bs[0] or 
																guard_bands != gbs[0] or comp_rtt != comp_rtts[0] or 
																num_colors != colors[0]):
																continue
														
														"""
														If UGUALE is used, markers are mandatory 
														"""
														if (switch_type == UGUALE and marking == NO_MARKERS):
															continue

														"""
														coherence guard bands and number of colors
														"""
														if (switch_type == UGUALE and guard_bands>=num_colors):
															continue

														n_users = users_ph*len(ADDRESSES)
														C = rate_to_int(bn_cap)
														free_C = C*(1.0 - free_b) # capacity to use for guaranteed rates

														#------------------------ GUARANTEED RATES ----------------------

														if not various_guaranteed:
															g_u = num_to_rate(free_C/float(n_users))
															g_rates = [g_u]*n_users
														else:
															"""
															Distribute g_u such as each one is double of the other
															Es. 3 users per host, C = 50Mb
															base = [1,2,3,1,2,3,1,2,3]
															sum_base = 15
															50/15 = 3.33
															g_rates = base * 3.33 = [3.33, 6.66m 9.99, 13.33, 16.66] whose sum is C 
															"""
															base = (range(1,users_ph+1))*len(ADDRESSES)
															sum_base = np.sum(base)
															mult = float(free_C)/sum_base
															g_rates = map(num_to_rate,map(lambda x: x*mult, base))


														#------------------------ RTTS ----------------------
														"""
														If the range has zero difference, all users have the same rtt
														If not, RTTs will be equally distributed in the range
														"""	
														if keep_same_rtts:
															range_rtts=[rtts,rtts]	

														delta_rtts = range_rtts[1]-range_rtts[0]
														if delta_rtts == 0:
															fixed_rtts = [range_rtts[0]]*n_users
														else:
															step = delta_rtts/float(n_users-1)
															fixed_rtts = []
															for i in range(n_users):
																fixed_rtts.append(range_rtts[0]+(i*step))	
															random.shuffle(fixed_rtts)

														"""
														If all users have the same rtts, 
														comp_rtts can be true or false
														and now it is true
														the compensate-rtts has no meaning
														"""
														if len(set(fixed_rtts))==1 and len(comp_rtts)>1 and comp_rtt:
															continue

														#------------------------CONNECTIONS ----------------------
														if keep_same_conns:
															range_conns = [conns,conns]
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
															fixed_conns = []
															conn_list = range(range_conns[0],range_conns[1]+1)
															i=0
															for u in range(n_users):
																fixed_conns.append(conn_list[i])
																i=(i+1)%len(conn_list)
															random.shuffle(fixed_conns)										

														#------------- EXPECTED FAIR RATES + COMP RTTS + MAXIMUM MARKING RATES ------------
														e_f_rates = [] #expected fair rates
														m_m_rates = [] # maximum marking rates
														coeffs = [] # coefficients that compensate rtt

														if comp_rtt:
															coeffs = get_rtt_coefficients(fixed_rtts,C,n_users, strength)
														else:
															coeffs = [1]*n_users

														for i in range(n_users):
															g_dr = rate_to_int(g_rates[i])
															efr = g_dr+((free_b*C)/float(n_users))
															e_f_rates.append(num_to_rate(efr))
															mmr_normal = get_marker_max_rate(g_rates, free_b, C, n_users, guard_bands,num_colors) 
															mmr = mmr_normal*coeffs[i]
															m_m_rates.append(num_to_rate(mmr))


														if queuelen_switch == -1:
															qsw = optimal_queue_len(fixed_rtts, fixed_conns, C)
														else:
															qsw = queuelen_switch


														configuration={
															"cookie"		: cookie, 
															"bn_cap"		: bn_cap, 	
															"vr_limit"		: vr_limit, 	
															"users_p_h"		: users_ph, 	
															"n_users"		: n_users, 	
															"g_rates"		: g_rates, 			
															"range_rtts"	: range_rtts, 	
															"fixed_rtts"	: fixed_rtts, 	
															"range_conns"	: range_conns, 
															"fixed_conns"	: fixed_conns, 	
															"free_b"		: free_b, 																				
															"duration"		: DURATION, 
															"marking"		: marking,
															"m_m_rates"		: m_m_rates,
															"guard_bands"	: guard_bands,
															"e_f_rates"		: e_f_rates,
															"queuelen"		: queuelen,
															"queuelen_switch": qsw,
															"tech"			: tech,
															"switch_type"	: switch_type,
															"visualization" : visualization,
															"comp_rtt" 		: comp_rtt,
															"strength"		: strength,
															"bands"			: num_colors	
														}

														configurations.append(configuration)

		
	"""
	Calculate Estimated time
	"""
	num_tests = len(configurations)*repetitions
	secs = num_tests*DURATION
	print "{} Tests, total duration: [{},{}]".format(
		num_tests, 
		datetime.timedelta(seconds = secs),
		datetime.timedelta(seconds = secs*MAX_TRIES))
	random.shuffle(configurations)	

	# try:	
	if tech != TECH_NONE:
		set_up_hosts(tech)
	for repetition in range(repetitions):
		for configuration in configurations:

			configuration["repetition"] = repetition
			instance_name = get_instance_name(configuration)
			pickle_name = "{}.p".format(instance_name)
			file_name = "{}/{}".format(folder, pickle_name)

			if os.path.isfile(file_name):
				print "Skip, existing test instance {}".format(instance_name)
				continue

			restore_switch()
			#---------------------- CONFIGURE SWITCH ----------------------#


			if configuration["switch_type"]==STANDALONE:
				cmd_ssh(
					SWITCH_IP, 
					"sudo sh config_ovs_standalone.sh {}".format(configuration["queuelen_switch"]))
				time.sleep(2)

			elif configuration["switch_type"]==UGUALE:

				cmd_ssh(SWITCH_IP, "sudo ryu-manager /home/redfox/ryu/ryu/app/lucab/uguale.py")
				time.sleep(2)

				cmd_ssh(
					SWITCH_IP,  
					"sudo sh config_ovs_uguale.sh {} {}".format(
						"127.0.0.1:6633",
						configuration["queuelen_switch"]))
				time.sleep(4)

			else:
				print "No valid switch to configure, exiting"
				return
				

			print("Executing {} ...".format(instance_name))

			for curr_try in range(MAX_TRIES):
				print "Try number {}...".format(curr_try)
				killall("iperf")
				killall("xterm")
				configuration["start_ts"] = time.time()+SYNC_TIME
				clients=threading.Thread(target=clients_thread, args=(configuration,))
				clients.start()
				tcp_ports = range(FIRST_TCP_PORT,FIRST_TCP_PORT+configuration["users_p_h"])
				udp_ports = []
				data = ps.run_server("eth0", tcp_ports, udp_ports, 
					interactive = False, 
					duration = configuration["duration"]+SYNC_TIME, 
					do_visualize = configuration["visualization"],
					expected_users = configuration["n_users"],
					check_time = BIRTH_TIMEOUT + SYNC_TIME)

				# if not data:
				# 	print "No data saved, test failed"
				# 	continue


				#---------------------- SAVING ----------------------#				
				test={"params":configuration, "data":data}

				if vr.test_is_valid(test):
					print "Valid test"
					if do_save:
						if not os.path.exists(folder):
							os.makedirs(folder)
						# Save the test in a file
						pickle.dump(test, open(file_name,"wb"))
						# append results to CSV
						stats = vr.get_stats(test)
						append_to_csv(configuration, stats)
					break # exit from current tries
				else:
					print "Errors in data, test failed"
					if curr_try == MAX_TRIES-1:
						print "Test failed too many times... skipping to next test!"
						append_to_csv(configuration, [])

	# except (KeyboardInterrupt):
	# 	print "Test interrupted"
	# finally:
	# 	print "Test terminated"
	# 	if len(failed_configurations)>0:
	# 		print "Failed tests:", failed_configurations

	# 	# restore_switch()
	# 	restore_hosts()
	# 	killall("iperf")
	# 	killall("xterm")
	# 	killall("bwm-ng")
	# 	killall("python")



def restore_switch():
	cmd_ssh(SWITCH_IP,"sudo sh config_ovs_standalone.sh 1000")
	time.sleep(2)
	cmd_ssh(SWITCH_IP,"sudo killall ryu-manager")	
	time.sleep(1)

def main(argv):

	do_save = False
	cookie = "test"
	folder = ""
	range_rtts = []
	range_conns = []
	list_rtts = []
	list_conns = []

	"""
	Notes:
	- the visualization does not impact the view_result
	- in average better results with queue 100
	"""

	help_string = "Usage: -f <folder> -c <cookie> -s <do-save>\n\
	-t<range-rtts> -P<range-conn>\n\
	-L<list-rtts> -C<list-conns>\n\
	-b<bottleneck capacity> -v<veth limit>\n\
	-u<users per host> -F<free bandwidth>\n\
	-r<number of repetitions> -g<various guaranteed>\n\
	-q<queuelens> -G<guard bands> -R <compensate-rtts>\n\
	-V<visualization> -S<queuelens on switch> -U<switch:standalone/uguale>\n\
	-M<markers:no_markers/buckets_markers/iptables_markers>\n\
	-Q<number of colors>\n\
	folder: folder to save files\n\
	cookie: special message to save\n\
	do-save: 1 to save \n\
	If lists are given, ranges are not considered\n\
	various guaranteed: true if g_u varies for each user, false if they must be the same\n\
	queuelens: queue lenght for every user on the PC\n\
	markers:  NO_MARKERS/BUCKETS_MARKERS/IPTABLES_MARKERS\n\
	queuelens_switch : number or -1 to use the optimal value"
	
	try:
		opts, args = getopt.getopt(argv,"hf:c:s:t:P:L:C:b:v:u:F:r:g:q:G:R:V:S:U:M:Q:")
	except getopt.GetoptError:
		print help_string
		sys.exit(2)

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
		elif opt in ("-t"):
			range_rtts = map(float,arg.split(","))
		elif opt in ("-P"):
			range_conns = map(int,arg.split(","))
		elif opt in ("-L"):
			list_rtts = map(float,arg.split(","))
		elif opt in ("-C"):
			list_conns = map(int,arg.split(","))
		elif opt in ("-b"):
			bn_cap = arg	
		elif opt in ("-v"):
			vr_limit = arg	
		elif opt in ("-u"):
			users_phs = map(int,arg.split(","))
		elif opt in ("-F"):
			free_bs = map(float,arg.split(","))
		elif opt in ("-r"):
			repetitions = int(arg)
		elif opt in ("-g"):
			various_guaranteed = my_bool(arg)
		elif opt in ("-q"):
			queuelens = map(int,arg.split(","))
		elif opt in ("-G"):
			gbs = map(int,arg.split(","))
		elif opt in ("-R"):
			comp_rtts = map(my_bool,arg.split(","))
		elif opt in ("-V"):
			visualizations = map(my_bool,arg.split(","))
		elif opt in ("-S"):
			queuelens_switch = map(int,arg.split(","))	
		elif opt in ("-U"):
			switch_types = arg.split(",")
		elif opt in ("-M"):
			markers = arg.split(",")
		elif opt in ("-Q"):
			colors = map(int,arg.split(","))		



	if ((folder == "" and do_save==True) # trying to save nowhere
	or (len(range_rtts)==0 and len(list_rtts)==0) # no rtt given
	or (len(range_conns)==0 and len(list_conns)==0) #no conns given
	or (len(range_conns)>0 and len(range_conns)!=2) # range must have 2 boundaries
	or (len(range_rtts)>0 and len(range_rtts)!=2)):	
		print folder, do_save, range_rtts, list_rtts, range_conns, list_conns
		print help_string
		sys.exit(2)	

	start_test(folder, cookie, do_save, range_conns, range_rtts, list_rtts, list_conns, 
		bn_cap, vr_limit, users_phs, free_bs, repetitions, various_guaranteed, 
		queuelens, gbs, comp_rtts, visualizations, queuelens_switch, switch_types, markers,colors)

if __name__ == "__main__":
   main(sys.argv[1:])
