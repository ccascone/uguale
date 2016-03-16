#!/usr/bin/python
import pickle, os, sys, getopt, math
import matplotlib.pyplot as plt
import numpy as np
import pylab as P
from scipy import interpolate
from mylib import *

def get_normalized_vals(vals, expected_fair_rate, C):	
	# return map(lambda x: ((x - expected_fair_rate)/expected_fair_rate)**2, vals)
	return map(lambda x: (x - expected_fair_rate)/float(C), vals)

def test_is_valid(test):
	# all users must arise within a timeout
	data = test["data"]
	params = test["params"]

	max_noshow_seconds = 5
	min_val = 100 # bit/s
	max_small_samples = 0.10

	expected_reports = float(params["duration"] - RECORD_BEGIN - RECORD_END)/IPERF_REPORT_INTERVAL
	max_noshow_reports = float(max_noshow_seconds) / IPERF_REPORT_INTERVAL

	flag = True

	if not data:
		print "Data is None"
		return False

	# Check if the SUM process (bwm-ng) has worked
	if len(data["SUM"]["total"]["t"])< (expected_reports/2.0):
		print "No SUM process"
		return False

	# Check if there are all iperf users
	if (len(data)-1)<params["n_users"]:
		print "ERROR: Expected {} active users, found {}".format(params["n_users"], len(data)-1) 
		flag = False

	for src in data:
		if src!="SUM":
			if data[src]["tcp"]["t"][0]>BIRTH_TIMEOUT:
				print "ERROR: {} born after birth timeout ({}s)".format(src, data[src]["tcp"]["t"][0])
				flag = False

			if data[src]["tcp"]["t"][-1]<params["duration"]-RECORD_END:
				print "ERROR: {} died prematurely ({}s)".format(src, data[src]["tcp"]["t"][-1])
				flag = False

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

	return flag

def trim_samples(samples, duration):
	"""
	Discard samples outside the RECORD_BEGIN-RECORD_END interval 
	(specific to the duration).
	Takes all samples right after the RECORD_BEGIN instant, 
	and al lsamples right before the RECORD_END instant.
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

	return [samples["t"][first:last], samples["val"][first:last]]


def get_jain_index(thrs, efrs):
	x = map(lambda i: float(i[0])/i[1], zip(thrs, efrs))
	num = (np.sum(x))**2
	den = len(thrs)*np.sum(map(lambda y: y**2, x))
	return float(num)/den


def get_stats(test):

	t_vals = []
	t_ts = []
	normalized_vals = []
	joint_vals = []
	data = test["data"]
	params = test["params"]
	efrs = map(rate_to_int, params["e_f_rates"])
	link_c = rate_to_int(params["vr_limit"])
	duration = params["duration"]
	means = []
	stds = []
	ips=[]
	ids=[]
	jain_idxs = []

	"""
	Extract data from dict and trim it
	Find the minimum lenght array
	"""
	i=0
	t_ini = 0 # the biggest first timestamp
	t_end = sys.maxint	 # the smallest last timestamp

	for src in sorted(data):
		if src == "SUM":
			continue
		trimmed_ts, trimmed_vals = trim_samples(data[src]["tcp"], duration)		
		t_ts.append(trimmed_ts)
		t_vals.append(trimmed_vals)		

		t_ini = max(math.ceil(trimmed_ts[0]), t_ini)
		t_end = min(math.floor(trimmed_ts[-1]), t_end)

		ips.append(src)
		ids.append(i)
		i+=1

	resampled_vals = []
	resampled_ts = np.linspace(
		t_ini, 
		t_end, 
		int(t_end-t_ini)*IPERF_REPORT_INTERVAL)# min, max, n_samples

	# t_vals cointains trimmed data["tcp"]["val"] ordered by ids
	for i in range(len(t_vals)):	
		vals = get_normalized_vals(t_vals[i], efrs[i], link_c)
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
		f = interpolate.interp1d(t_ts[i], t_vals[i]) # interpolation function

		"""
		resample directly at each IPERF_REPORT_INTERVAL
		"""
		r_v = f(resampled_ts)
		resampled_vals.append(r_v)

	total_goodput = []
	for t in range(len(resampled_ts)):
		rates_t = [resampled_vals[i][t] for i in range(len(resampled_vals))]  # rates in a certain t
		jain_idxs.append(get_jain_index(rates_t, efrs))
		total_goodput.append(np.sum(rates_t))

	jain_idx_mean = np.mean(jain_idxs)
	jain_idx_var = np.var(jain_idxs)

	"""
	Throughput
	"""
	bwm_ng= data["SUM"]["total"]
	trimmed_ts_bwm, trimmed_vals_bwm = trim_samples(bwm_ng, duration)
	normalized_throughput = map(lambda x: x/float(link_c), trimmed_vals_bwm)
	thr_mean = np.mean(normalized_throughput)
	thr_var = np.var(normalized_throughput)

	"""
	Goodput
	"""
	normalized_goodput = map(lambda x: x/float(link_c), total_goodput)
	good_mean = np.mean(normalized_goodput)
	good_var = np.var(normalized_goodput)

	"""
	Ratio goodput/throughput
	The throughput must be resampled in the same instants of the goodput 
	"""

	f = interpolate.interp1d(bwm_ng["t"], bwm_ng["val"])
	resampled_throughput = f(resampled_ts)
	ratio_gt = [float(total_goodput[i]) / resampled_throughput[i] for i in range(len(total_goodput))]
	ratio_gt_mean = np.mean(ratio_gt)
	ratio_gt_var = np.var(ratio_gt) 

	"""
	Stats on aggregated normalized samples
	"""	
	distr_mean = np.mean(joint_vals)
	distr_std = np.std(joint_vals)
	distr_var = np.var(joint_vals)
	distr_mse = np.mean(map(np.square, joint_vals))

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
		"thr_mean"			: thr_mean, 
		"thr_var"			: thr_var, 
		"good_mean"			: good_mean, 
		"good_var"			: good_var, 
		"ratio_gt_mean"		: ratio_gt_mean, 
		"ratio_gt_var"		: ratio_gt_var, 
		"distr_mean"		: distr_mean, 
		"distr_var"			: distr_var, 
		"distr_std"			: distr_std, 
		"distr_mse"			: distr_mse, 
		"means"				: means, 
		"stds"				: stds, 
		"ips"				: ips, 
		"ids"				: ids, 
		"same_rtts"			: same_rtts, 
		"same_conns"		: same_conns
	}

	return stat

"""
Create the desctiption text
starting from test parameters and stats
"""
def get_text(params, stat, brief=False):
	import textwrap as tw
	text_width = 45	
	separator = "\n"
	text = ""

	"""
	1st PARAGRAPH: user: #c, rtt
	"""
	users = map(lambda x: x+1, stat["ids"])
	text += "USERS\n"
	for i in range(len(users)):
		text += "User {}: {}c, {}ms\n".format(
			users[i], int(params["fixed_conns"][i]), int(params["fixed_rtts"][i]))

	"""
	2nd PARAGRAPH: list of test parameters 

	params_to_show  : list of parameters to be considered
	params_to_show2 : list of names to print for the considered parameters 
	"""
	if brief:
		if params["do_symm"] and params["switch_type"] == UGUALE:
			params_to_show = PARAMS_BRIEF_SYMM
			params_to_show2 = PARAMS_BRIEF_SYMM_SHOW
		elif params["switch_type"] == STANDALONE:
			params_to_show = PARAMS_BRIEF_STANDALONE
			params_to_show2 = PARAMS_BRIEF_STANDALONE_SHOW
		else:
			params_to_show = PARAMS_BRIEF
			params_to_show2 = PARAMS_BRIEF_SHOW

	else: # print every parameter in raw format
		params_to_show = params.keys()
		params_to_show2 = params.keys()

	text += "\nCONFIGURATION\n"	
	i = 0
	for param in params_to_show:

		# params already considered in the 1st paragraph
		if params in ["fixed_conns", "fixed_rtts"]:
			continue

		if param not in params:
			value == "unknown"
		else:
			value = params[param]

		"""
		Modify parameter value for unusual configurations
		"""
		if params["switch_type"] == STANDALONE:
			if param == "markers":
				value = NO_MARKERS
			elif param == "guard_bands":
				value = -1
			elif param == "do_comp_rtt":
				value = False
			elif param == "free_b":
				value = 0.0
			elif param == "num_bands":
				value == 1

		# compatibility for old tests
		if params["switch_type"] == UGUALE and "num_bands" not in params:
			value = 8

		if param == "do_comp_rtt" and len(set(params["fixed_rtts"]))==1:
			value = False

		param2 = params_to_show2[i] # parameter's name to print

		# abbreviate lists of identical elements 
		if ((isinstance(value, list) or isinstance(value, tuple)) and 
			len(value)>2 and 
			len(set(value))==1):
			text += "{}: [{}]*{}{}".format(param2, value[0], len(value), separator)
		else:
			unity = ""
			if param in ["queuelen"]:
				unity = "pkt"
			text += separator.join(tw.wrap("{}: {} {}".format(param2, value, unity), text_width)) + separator
		i+=1

	"""
	3rd paragraph: list of statistics
	"""
	text += "\nSTATISTICS\n"
	i=0
	for key in STATS_BRIEF:
		val = stat[key]
		text+= "{}: ".format(STATS_BRIEF_SHOW[i])
		if float(val)==val and val<10:
			text += "{0:.7f}".format(val)
		else:
			text += "{}".format(int(val))	
		text+= separator
		i+=1

	return text[:-1]


def plot_file(test, stat, instance_name, new_folders, do_save):

	params = dict(test["params"])
	new_params = cast_value(params)
	text = get_text(new_params, stat, brief=True)

	subplots = {
		"distr": {
			"position"	: 221, 
			"title"		: "(a)", 
			"xlabel"	: "Distance from OFR normalized w.r.t. bottleneck capacity", 
			"ylabel"	: "Discrete distribution"
		}, 
		"gen": {
			"position"	: 222, 
			"title"		: "(b)", 
			"xlabel"	: "User ID", 
			"ylabel"	: "Distance from OFR normalized w.r.t. bottleneck capacity"
		}, 
		"rtts": {
			"position"	: 223, 
			"title"		: "(c)", 
			"xlabel"	: "RTT [ms]", 
			"ylabel"	: "Distance from OFR normalized w.r.t. bottleneck capacity"
		}, 
		"conns": {
			"position"	: 224, 
			"title"		: "(d)", 
			"xlabel"	: "Number of TCP connections", 
			"ylabel"	: ""
		}
	}

	height = 11
	width = height * 1.7
	hor_border = 0.10 # as % of 1 that is the total figure size
	ver_border = 0.05
	end_plots = 0.8 # We must leave space for the legend
	y_lims = [-0.10, +0.10] # values in plots
	x_lims = [-0.15, +0.15] # used for histograms	

	ax = {} # subplots
	fig = plt.figure(1, figsize=(width, height))
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

	fig.subplots_adjust(left=hor_border*0.5, bottom=ver_border, 
		right=end_plots, top=1-(ver_border*0.66))

	users = map(lambda x: x+1, stat["ids"])
	fixed_rtts = test["params"]["fixed_rtts"]
	fixed_conns = test["params"]["fixed_conns"]
	mean_rate = stat["distr_mean"]

	# ----------------------------- GENERAL ----------------------------------------

	x_min = 0
	x_max = max(users)+1

	ax["gen"].set_xlim([x_min, x_max])
	ax["gen"].xaxis.set_ticks(sorted(users))	
	ax["gen"].set_ylim(y_lims)	
	ax["gen"].errorbar(users, stat["means"], stat["stds"], 
		linestyle="None", marker="o", color="black", label="Mean/std")
	ax["gen"].legend()
	ax["gen"].axhline(linewidth=1, color="black")       

	# ----------------------------- DISTRIBUTION + HISTOGRAM----------------------------------------

	n, bins, rectangles = P.hist(
		stat["joint_vals"], 
		bins=np.linspace(-1, +1, HIST_BINS), 
		normed=True, 
		edgecolor='black', 
		facecolor='black', 
		antialiased=True, 
		alpha=1)

	max_y = max(n)*1.10
	ax["distr"].plot([mean_rate, mean_rate], [0, max_y], 
		color="red", label="Mean", linewidth=1.5)
	ax["distr"].legend()
	ax["distr"].set_xlim(x_lims)	
	ax["distr"].set_ylim([0, max_y])	

	stat_text = ""
	key2 = ["Mean", "Var", "Std", "MSE"]
	i=0
	for key in ["distr_mean", "distr_var", "distr_std", "distr_mse"]:
		val = stat[key]
		stat_text+= "{}: ".format(key2[i])
		if float(val)==val and val<10:
			stat_text += "{0:.7f}".format(val)
		else:
			stat_text += "{}".format(int(val))	
		stat_text+= "\n"
		i+=1

	ax["distr"].text(x_lims[0]+0.01, max_y*0.97, stat_text, ha="left", va="top")

	# ----------------------------- RTTS ----------------------------------------

	same_rtts = stat["same_rtts"]
	means_same_rtts = []
	dev_same_rtts = []
	for rtt in sorted(same_rtts):
		means_same_rtts.append(same_rtts[rtt]["mean"])
		dev_same_rtts.append(same_rtts[rtt]["std"])

	x_min = 0
	x_max = max(fixed_rtts)+min(fixed_rtts)
	if len(same_rtts)>1:
		keys = sorted(same_rtts.keys())
		delta = keys[1]-keys[0]
		x_min = max(0, keys[0]-delta)
		x_max = keys[-1]+delta

	ax["rtts"].set_xlim([x_min, x_max])	

	"""
	If there are many RTT, the x-axis has no space to display all labels
	"""
	if len(same_rtts)>18:
		"""
		Alternate from the first. If it is even, it won't be nice :-(
		"""
		ax["rtts"].xaxis.set_ticks(sorted(same_rtts)[::2])		
	else:
		ax["rtts"].xaxis.set_ticks(sorted(same_rtts))

	ax["rtts"].set_ylim(y_lims)
	ax["rtts"].errorbar(sorted(same_rtts), means_same_rtts, dev_same_rtts, 
		linestyle="None", marker="o", color="black", label="Mean/std")
	ax["rtts"].legend()
	ax["rtts"].axhline(linewidth=1, color="black")       

	# ----------------------------- CONNS ----------------------------------------
	x_min = max(0, min(fixed_conns)-1)
	x_max = max(fixed_conns)+1

	same_conns = stat["same_conns"]
	means_same_conns = []
	dev_same_conns = []
	for conn in sorted(same_conns):
		means_same_conns.append(same_conns[conn]["mean"])
		dev_same_conns.append(same_conns[conn]["std"])

	ax["conns"].set_xlim([x_min, x_max])	
	ax["conns"].xaxis.set_ticks(sorted(same_conns))
	ax["conns"].set_ylim(y_lims)
	ax["conns"].errorbar(sorted(same_conns), means_same_conns, dev_same_conns, 
		linestyle="None", marker="o", color="black", label="Mean/std")
	ax["conns"].legend()
	ax["conns"].axhline(linewidth=1, color="black")        
	# ----------------------------- TEXTS ----------------------------------------

	plt.figtext(end_plots+(0.33*hor_border), 1-(0.66*ver_border)-0.01, 
		text, va='top', ha='left', bbox={'facecolor': 'white', 'pad': 20})

	# ----------------------------- SAVE ----------------------------------------

	"""
	filename
	"""
	if do_save:
		quality = "Q{}".format(int(stat["distr_mse"]*10**8))
		timestamp = str(params["start_ts"]).replace(".", "_")

		fig_filename="{}/{}_{}_{}.png".format(new_folders[0], quality, 
			instance_name, timestamp)
		plt.savefig(fig_filename, format="PNG")

		pdf_filename="{}/{}.pdf".format(new_folders[1], timestamp)
		plt.savefig(pdf_filename, format="PDF")

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

	test = pickle.load(open("{}/{}".format(folder, pickle_name), "rb"))

	if not test_is_valid(test):
		print "ERROR: invalid test! Skipping..."
		return

	stat = get_stats(test)
	plot_file(test, stat, instance_name, new_folders, do_save)


def plot_all_files(folder, do_save):

	new_folders = ["./{}/fig/".format(folder), "./pdf_results/"]
	for n_f in new_folders:
		if do_save and not os.path.exists(n_f):
			os.makedirs(n_f)

	for file_name in os.listdir("./{}/".format(folder)):
		if file_name[-2:] == ".p":
			instance_name = file_name[:-2]
			print "Processing {}...".format(instance_name)

			test = pickle.load(open("{}/{}".format(folder, file_name), "rb"))
			ts = (str(test["params"]["start_ts"])).replace(".", "_")
			skip = False

			for pdf_name in os.listdir(new_folders[1]):
				if pdf_name.find(ts)!=-1:
					skip=True
					print "Existing pdf!"
					break

			if not skip:
				plot_single_file(
					instance_name=instance_name, 
					pickle_name=file_name, 
					folder=folder, 
					do_save=do_save)


def main(argv):
	folder = "/"
	do_save = False
	help_string = "Usage: -f <folder> -s <do-save>\n\
	foder: absolute path or starting from where the program is executed\n\
	do-save: 1 to save file, 0 to show only"

	try:
		opts, args = getopt.getopt(argv, "hf:s:")
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

	plot_all_files(folder, do_save)

if __name__ == "__main__":
	main(sys.argv[1:])
