#!/usr/bin/python
import pickle, os, sys, getopt
import numpy as np
import math
import matplotlib.mlab as mlab
import matplotlib.pyplot as plt
from mylib import *
from scipy import stats
import pylab as P
from scipy import interpolate
# from matplotlib.offsetbox import AnchoredOffsetbox, TextArea, VPacker

RESAMPLING_FREQUENCY = 10 

def get_normalized_vals(vals, expected_fair_rate, C):	
	# return map(lambda x: ((x - expected_fair_rate)/expected_fair_rate)**2, vals)
	return map(lambda x: (x - expected_fair_rate)/float(C), vals)

def test_is_valid(test):

	# all must birth within a timeout
	data = test["data"]
	params = test["params"]

	max_noshow_seconds = 5
	min_val = 100 # bit/s
	max_small_samples = 0.10

	flag = True

	if not data:
		print "Data is None"
		return False

	if (len(data)-1)<params["n_users"]:
		print "ERROR: Expected {} active users, found {}".format(params["n_users"],len(data)-1 ) 
		flag = False

	expected_reports =  float(params["duration"] - RECORD_BEGIN - RECORD_END)/IPERF_REPORT_INTERVAL
	max_noshow_reports = float(max_noshow_seconds) / IPERF_REPORT_INTERVAL

	for src in data:
		if src!="SUM":
			if data[src]["tcp"]["t"][0]>BIRTH_TIMEOUT:
				print "ERROR: {} born after birth timeout ({}s)".format(src,data[src]["tcp"]["t"][0])
				flag = False

			if data[src]["tcp"]["t"][-1]<params["duration"]-RECORD_END:
				print "ERROR: {} died prematurely ({}s)".format(src,data[src]["tcp"]["t"][-1])
				flag =  False

			sampleslen = len((trim_samples(data[src]["tcp"], params['duration']))[1])
			if math.fabs(sampleslen - expected_reports) > max_noshow_seconds:
				print "ERROR: expected {} samples (+\-{}), but {} has {}".format(expected_reports, max_noshow_reports, src, sampleslen)
				flag = False

			np_val_array = np.array(data[src]["tcp"]["val"])
			# check the number of small samples (if too many samples are too small, then somthing went wrong... maybe...)
			small_samples = len(np_val_array[np.where(np_val_array < min_val)])
			if small_samples > max_small_samples * len(data[src]["tcp"]["val"]):
				print "ERROR: too many low bitrate samples for {} ({} under {}bit/s)".format(
					src, small_samples, min_val)
				flag = False

	## TODO: check that the amount of 0 samples is less then a quota

	return flag

def trim_samples(samples, duration):
	"""
		Discard samples outside the RECORD_BEGIN-RECORD_END interval (specific to the duration).
		Takes all samples right after the RECORD_BEGIN instant, and al lsamples right before the RECORD_END instant.
	"""
	first = 0
	for i in range(len(samples["t"])):
		ts = samples["t"][i]
		if ts>RECORD_BEGIN:
			break
	first = i+1

	last_valid_instant = duration - RECORD_END

	last = 0
	for i in range(len(samples["t"])):
		ts = samples["t"][i]
		if ts > last_valid_instant:
			break
	last = i-1

	return [samples["t"][first:last],samples["val"][first:last]]


def get_jain_index(thrs, efrs):
	x = map(lambda i : float(i[0])/i[1], zip(thrs, efrs))
	num = (np.sum(x))**2
	den = len(thrs)*np.sum(map(lambda y:y**2,x))
	return float(num)/den


def get_stats(test):
	"""
	Recover useful parameters and initialize variables
	"""
	t_vals = []
	t_ts = []
	normalized_vals = []
	joint_vals = []
	data = test["data"]
	params = test["params"]
	#free_b = params["free_b"]
	#rate_to_int(params["g_rates"][i])
	
	efrs = map(rate_to_int, params["e_f_rates"])
	C = rate_to_int(params["bn_cap"])
	duration = test["params"]["duration"]
	
	means = []
	stds = []
	percentiles = []
	ips=[]
	ids=[]

	jain_idxs = []


	"""
	Extract data from dict and trim it
	Find the minimum lenght array
	"""
	i=0
	t_ini = 0# the biggest first timestamp
	t_end = sys.maxint	 #the smallest last timestamp
	min_length = sys.maxint # min number of samples per user

	for src in sorted(data):
		if src == "SUM":
			continue
		trimmed_ts, trimmed_vals = trim_samples(data[src]["tcp"], duration)		
		t_ts.append(trimmed_ts)
		t_vals.append(trimmed_vals)		

		t_ini = max(math.ceil(trimmed_ts[0]),t_ini)
		t_end = min(math.floor(trimmed_ts[-1]),t_end)
		min_length = min(min_length, len(trimmed_ts))

		ips.append(src)
		ids.append(i)
		i+=1


	# high frequency resampling
	# hf_vals = []
	# hf_ts = np.linspace(
	# 	t_ini, 
	# 	t_end, 
	# 	int(t_end-t_ini)*IPERF_REPORT_INTERVAL*RESAMPLING_FREQUENCY)# min, max, n_samples


	resampled_vals = []
	resampled_ts = np.linspace(
		t_ini, 
		t_end, 
		int(t_end-t_ini)*IPERF_REPORT_INTERVAL)# min, max, n_samples


	# t_vals cointains trimmed data["tcp"]["val"] ordered by ids
	for i in range(len(t_vals)):	
		vals = get_normalized_vals(t_vals[i], efrs[i], C)
		normalized_vals.append(vals)
		"""
		to calculate the distribution of samples
		we join all values of all users in a list
		"""
		joint_vals.extend(vals)

		"""
		for the mean, dev, percentile graph we 
		save this values for each user
		"""
		means.append(np.mean(vals))
		stds.append(np.std(vals))

		"""
		resample the signal to obtain syncronized samples
		"""
		f = interpolate.interp1d(t_ts[i],t_vals[i]) # interpolation function

		# """
		# method 1: value is the average on each IPERF_REPORT_INTERVAL of the high frequency resampled signal
		# """
		# hf_v = f(hf_ts) # high frequency signal
		# r_v = [np.mean(hf_v[j:j+RESAMPLING_FREQUENCY]) for j in range(0,len(hf_v),RESAMPLING_FREQUENCY)] 
		# print len(hf_v), len(r_v)
		# hf_vals.append(hf_v)
		# resampled_vals.append(r_v)

		"""
		method 2: resample directly at each IPERF_REPORT_INTERVAL
		"""
		r_v = f(resampled_ts)
		# print len(r_v)
		resampled_vals.append(r_v)

	
	total_goodput = []
	for t in range(len(resampled_ts)):
		rates_t = [resampled_vals[i][t] for i in range(len(resampled_vals))]  # rates in a certain t
		jain_idxs.append(get_jain_index(rates_t,efrs))
		total_goodput.append(np.sum(rates_t))


	jain_idx_mean = np.mean(jain_idxs)
	jain_idx_var = np.var(jain_idxs)

	"""
	Ratio goodput/throughput
	"""
	bwm_ng= data["SUM"]["total"]
	f = interpolate.interp1d(bwm_ng["t"],bwm_ng["val"])
	total_throughput = f(resampled_ts)

	ratio_gt = [ float(total_goodput[i]) / total_throughput[i] for i in range(len(total_goodput))]
	ratio_gt_mean = np.mean(ratio_gt)
	ratio_gt_var = np.var(ratio_gt) 

	"""
	Stats on aggregated normalized samples
	"""	
	global_percentile = np.percentile(map(math.fabs, joint_vals), 90)
	global_mean = np.mean(joint_vals)
	global_std = np.std(joint_vals)
	global_var = np.var(joint_vals)
	global_abs_mean = np.mean(np.fabs(joint_vals))

	"""
	Measured distribution
	"""
	density = stats.kde.gaussian_kde(joint_vals) #,20*step
	x = np.linspace(-1,1,DISTR_BINS)
	measured_distr = density(x)
	# the frequency must be normalized
	# e.g if I have 10 samples on 1000 in an interval,
	# I want the value for that interval to be 1% = 0.01 instead of 10
	# so we can compare test with different users--> total samples
	# measured_distr = map(lambda x: x/len(joint_vals), measured_distr)

	# new_x=np.arange(-1,+1+STEP/10,STEP/10)
	# smooth_distr = spline(stat["x_for_distribution"],measured_distr,new_x)

	"""
	Reference distribution
	"""
	ref_distr = mlab.normpdf(x,REF_MEAN,REF_STD_DEV)
	corr = np.correlate(ref_distr,measured_distr)[0]


	"""
	Aggregate users with the same RTT and do stats
	es. {
	 50ms : vals = [...], mean=X, std=Y
	 100ms : vals = [...], mean=R, std=U
	}
	"""
	fixed_rtts = params["fixed_rtts"]	
	same_rtts = {}	
	for i in ids:
		if ("netem" in params and not params["netem"]): 
			rtt = RTT_NO_NETEM
		else:
			rtt = fixed_rtts[i]

		if rtt not in same_rtts:
			same_rtts[rtt] = {}
			same_rtts[rtt]["vals"] = []
		same_rtts[rtt]["vals"].extend(normalized_vals[i])

	for rtt in same_rtts:
		same_rtts[rtt]["mean"] = np.mean(same_rtts[rtt]["vals"])
		same_rtts[rtt]["std"] = np.std(same_rtts[rtt]["vals"])


	"""
	Aggregate users with the same n of conns and do stats
	"""
	fixed_conns = params["fixed_conns"]
	same_conns = {}
	for i in ids:
		conn = fixed_conns[i]
		if conn not in same_conns:
			same_conns[conn] = {}
			same_conns[conn]["vals"] = []
		same_conns[conn]["vals"].extend(normalized_vals[i])

	for conn in same_conns:
		same_conns[conn]["mean"] = np.mean(same_conns[conn]["vals"])
		same_conns[conn]["std"] = np.std(same_conns[conn]["vals"])


	"""
	save all stat in a dict
	"""
	stat={
		"joint_vals"		: joint_vals,
		"jain_idx_mean"		: jain_idx_mean,
		"jain_idx_var"		: jain_idx_var,
		"ratio_gt_mean"		: ratio_gt_mean,
		"ratio_gt_var"		: ratio_gt_var,
		"global_mean"		: global_mean,
		"global_var"		: global_var,
		"global_std"		: global_std,
		"global_percentile"	: global_percentile,
		"global_abs_mean"	: global_abs_mean,
		"measured_distr"	: measured_distr,
		"means"				: means, 
		"stds"				: stds, 
		"percentiles"		: percentiles,
		"ips"				: ips,
		"ids"				: ids,
		"same_rtts"			: same_rtts,
		"same_conns"		: same_conns,
		"samples_per_user"	: min_length,
		"distr_corr" 		: corr 
	}

	return stat

"""
Create the desctiption text
starting from test parameters and stats
"""
def get_text(params, stat):
	text_width = 45
	import textwrap as tw
	separator = "\n"
	text = ""

	# connections
	users = map(lambda x: x+1, stat["ids"])
	text += "USERS\n"
	for i in range(len(users)):
		if ("netem" in params and not params["netem"]):
			text += "User {}: {}c, {}ms\n".format(users[i],int(params["fixed_conns"][i]),RTT_NO_NETEM)
		else:	
			text += "User {}: {}c, {}ms\n".format(users[i],int(params["fixed_conns"][i]),int(params["fixed_rtts"][i]))

	# parameters
	text += "\nCONFIGURATION\n"
	for param in params:
		if param != "fixed_conns" and param != "fixed_rtts":
			value = params[param]
			if (isinstance(value,list) or isinstance(value,tuple)) and len(value)>2 and len(set(value))==1:
				text += "{} : [{}]*{}{}".format(param, value[0],len(value),separator)
			else:
				text += separator.join(tw.wrap("{} : {}".format(param, value), text_width)) + separator

	# statistics
	text += "\nSTATISTICS\n"
	for key in STATS_COLUMNS:
		val = stat[key]
		text+= "{} : ".format(key)
		if float(val)==val and val<10:
			text += "{0:.7f}".format(val)
		else:
			text += "{}".format(int(val))	
		text+= separator		
		
	return text


def plot_file(test, stat, instance_name, new_folders, do_save):
	params = dict(test["params"])

	new_params = cast_value(params)

	text = get_text(new_params,stat)

	subplots = {
		"gen" : {
			"position"	: 222,
			"title"		: "Users",
			"xlabel"	: "User ID",
			"ylabel"	: "Distance from EFR normalized w.r.t. bottleneck capacity"
			
		},
		"distr" : {
			"position"	: 221,
			"title"		: "Distribution of rates",
			"xlabel"	: "Distance from EFR normalized w.r.t. bottleneck capacity",
			"ylabel"	: "Normalized count"
		},
		"rtts" : {
			"position"	: 223,
			"title"		: "Rate dependence from the Round Trip Time",
			"xlabel"	: "RTT",
			"ylabel"	: "Distance from EFR normalized w.r.t. bottleneck capacity"
		},
		"conns" : {
			"position"	: 224,
			"title"		: "Rate dependence from the number of TCP connections",
			"xlabel"	: "Number of TCP connections",
			"ylabel"	: "Distance from EFR normalized w.r.t. bottleneck capacity"
		}
	}

	height = 16
	width = int(height*(16/9.0))
	

	ax = {} # subplots
	fig = plt.figure(1, figsize=(width,height))
	for key in subplots:
		ax[key] = fig.add_subplot(subplots[key]["position"])
		ax[key].set_ylabel(subplots[key]["ylabel"])
		ax[key].set_xlabel(subplots[key]["xlabel"])
		ax[key].set_title(subplots[key]["title"])
		ax[key].grid(True)

	# +y
	# |
	# |
	# |
	# ------+ x
	border = 0.045 # as % of 1 that is the total figure size

	# # text may be long
	# if len(params["m_m_rates"])>2 and len(set(params["m_m_rates"]))>1:
	# 	end_plots = 0.7 - border # We must leave space for the legend
	# else:
	# 	end_plots = 0.85 - border # We must leave space for the legend

	end_plots = 0.85 - border # We must leave space for the legend

	fig.subplots_adjust(left=border,bottom=border,right=end_plots,top=1-border)


	users = map(lambda x: x+1, stat["ids"])
	fixed_rtts = test["params"]["fixed_rtts"]
	fixed_conns = test["params"]["fixed_conns"]
	mean_rate = stat["global_mean"]
	y_lims = [-0.15,+0.15] # values in plots

	#----------------------------- GENERAL ----------------------------------------

	x_min = 0
	x_max = max(users)+1

	ax["gen"].set_xlim([x_min,x_max])
	ax["gen"].xaxis.set_ticks(sorted(users))	
	ax["gen"].set_ylim(y_lims)	
	ax["gen"].errorbar(users, stat["means"], stat["stds"], linestyle="None", marker="o", color="black")
	ax["gen"].plot([x_min,x_max],[mean_rate,mean_rate], linestyle="--", color="red", label="Measured mean")
	ax["gen"].legend()


	#----------------------------- DISTRIBUTION + HISTOGRAM----------------------------------------

	n, bins, rectangles  = P.hist( stat["joint_vals"], 
			bins = np.linspace(-1,+1, HIST_BINS), 
			normed = True, 
			edgecolor = 'black',
			facecolor = 'grey',
			antialiased = True,
			alpha = 0.3
			)

	ax["distr"].plot(np.linspace(-1,+1, DISTR_BINS), stat["measured_distr"], 
			label="Estimated PDF",
			color = 'black',
			linewidth = 1.5,
			antialiased = True
			)

	max_y = max(max(stat["measured_distr"]),max(n))*1.10
	ax["distr"].plot([mean_rate,mean_rate],[0,max_y], linestyle="--", color="red", label="Measured mean")

	ax["distr"].legend()	
	ax["distr"].set_xlim([-0.25,+0.25])	
	ax["distr"].set_ylim([0,max_y])	

	# ref_distr = mlab.normpdf(stat["x_for_distribution"],REF_MEAN,REF_STD_DEV)

	# ax["distr"].plot(stat["x_for_distribution"], ref_distr,  
	# 		label="Reference distribution",
	# 		color = 'red',
	# 		linewidth = 1,
	# 		antialiased = True,
	# 		linestyle = "--"
	# 		)

	# normed means that the area sums to 1
	# but we want to normalize such that the max height is 1 = 100% of samples in that interval
	# for item in rectangles:
	# 	item.set_height(item.get_height()/len(stat["joint_vals"]))

	# ax["distr"].set_ylim([0,max(stat["measured_distr"])*1.2])	


	#----------------------------- RTTS ----------------------------------------


	same_rtts = stat["same_rtts"]
	means_same_rtts = []
	dev_same_rtts  = []
	for rtt in sorted(same_rtts):
		means_same_rtts.append(same_rtts[rtt]["mean"])
		dev_same_rtts.append(same_rtts[rtt]["std"])

	x_min = 0
	x_max = max(fixed_rtts)+min(fixed_rtts)
	if len(same_rtts)>1:
		keys = sorted(same_rtts.keys())
		delta = keys[1]-keys[0]
		x_min = max(0,keys[0]-delta)
		x_max = keys[-1]+delta
	
	ax["rtts"].set_xlim([x_min,x_max])	
	ax["rtts"].xaxis.set_ticks(sorted(same_rtts))
	ax["rtts"].set_ylim(y_lims)
	ax["rtts"].errorbar(sorted(same_rtts), means_same_rtts, dev_same_rtts, linestyle="None", marker="o", color="black")
	ax["rtts"].plot([x_min,x_max],[mean_rate,mean_rate], linestyle="--", color="red", label="Measured mean")
	ax["rtts"].legend()
	
	#----------------------------- CONNS ----------------------------------------
	x_min = max(0,min(fixed_conns)-1)
	x_max = max(fixed_conns)+1

	same_conns = stat["same_conns"]
	means_same_conns = []
	dev_same_conns  = []
	for conn in sorted(same_conns):
		means_same_conns.append(same_conns[conn]["mean"])
		dev_same_conns.append(same_conns[conn]["std"])

	ax["conns"].set_xlim([x_min,x_max])	
	ax["conns"].xaxis.set_ticks(sorted(same_conns))
	ax["conns"].set_ylim(y_lims)
	ax["conns"].errorbar(sorted(same_conns), means_same_conns, dev_same_conns, linestyle="None", marker="o", color="black")
	ax["conns"].plot([x_min,x_max],[mean_rate,mean_rate], linestyle="--", color="red", label="Measured mean")
	ax["conns"].legend()

	#----------------------------- TEXTS ----------------------------------------

	plt.figtext(end_plots+(border/2), 1-border-0.01,  text, va = 'top' , ha = 'left', bbox = {'facecolor':'white', 'pad':20})
	# p = patches.Rectangle((1.02,0),0.3,0.3)
	# fig.set_patch(p)

	#----------------------------- SAVE ----------------------------------------


	"""
	filename
	"""
	if do_save:
		quality = "Q{}".format(int(stat["global_abs_mean"]*10**6))
		fig_filename="{}/{}_{}.png".format(new_folders[0],quality,instance_name)
		plt.savefig(fig_filename, format="PNG")

		timestamp = str(params["start_ts"]).replace(".","_")
		pdf_filename="{}/{}.pdf".format(new_folders[1],timestamp)
		plt.savefig(pdf_filename, format="PDF")

		print quality, timestamp

	else:	
		plt.show(block=True)

	"""
	Reset for future graphs
	"""
	plt.cla()
	plt.clf()
	plt.close()


def plot_single_file(instance_name, pickle_name, folder, do_save):

	new_folders = ["./{}/fig/".format(folder), "./pdf_results/"]
	for n_f in new_folders:
		if do_save and not os.path.exists(n_f):
			os.makedirs(n_f)

	print "Processing {}...".format(instance_name)
	test = pickle.load(open("{}/{}".format(folder,pickle_name),"rb"))
	if not test_is_valid(test):
		print "ERROR: invalid test! Skipping..."
		return

	# """
	# If all users have the same rtts, 
	# the compensate-rtts has no meaning
	# """
	# if len(set(params["fixed_rtts"]))==1 and params["comp_rtt"]:
	# 	print "Useless test"
	# 	return

	if test["params"]["marking"] == BUCKETS_MARKERS:
		print "Token bucket, skipping"
		return
	stat = get_stats(test)
	plot_file(test, stat, instance_name, new_folders, do_save)


def plot_all_files(folder, do_save):

	for file_name in os.listdir("./{}/".format(folder)):
		if file_name[-2:] == ".p":
			instance_name = file_name[:-2]
			skip = False
			# for image_name in os.listdir(folder):
				# if image_name.find(instance_name)!=-1:
				# 	skip=True
				# 	break
			if not skip:
				plot_single_file(
					instance_name=instance_name,
					pickle_name=file_name,
					folder=folder,
					do_save=do_save)


def main(argv):
	folder =  "/"
	do_save = False
	help_string = "Usage: -f <folder> -s <do-save>\n\
	foder: absolute path or starting from where the program is executed\n\
	do-save: 1 to save file, 0 to show only"

	try:
		opts, args = getopt.getopt(argv,"hf:s:")
	except getopt.GetoptError:
		print help_string
		sys.exit(2)

	for opt, arg in opts:
		if opt == '-h':
			print help_string
			sys.exit()
		elif opt in ("-f"):
			folder = arg
		elif opt in ("-s"):
			do_save_int = int(arg)

	if do_save_int==1:
		do_save=True

	plot_all_files(folder,do_save)

if __name__ == "__main__":
   main(sys.argv[1:])