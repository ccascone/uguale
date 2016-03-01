#!/usr/bin/python
from mylib import *
from marking_lib import *
import os, pickle, sys, getopt
import view_result as vr
import test as tt

def calc_all_files(folder):

	for file_name in os.listdir("./{}/".format(folder)):
		if file_name[-2:] == ".p":
			instance_name = file_name[:-2]
			print "Processing {}...".format(instance_name)
			my_test = pickle.load(open("{}/{}".format(folder,file_name),"rb"))
			if not vr.test_is_valid(my_test):
				print "ERROR: invalid test! Skipping..."
				continue
			tt.append_to_csv(my_test["params"], vr.get_stats(my_test))

def main(argv):
	folder =  "/"
	help_string = "Usage: -f <folder>"

	try:
		opts, args = getopt.getopt(argv,"hf:")
	except getopt.GetoptError:
		print help_string
		sys.exit(2)

	for opt, arg in opts:
		if opt == '-h':
			print help_string
			sys.exit()
		elif opt in ("-f"):
			folder = arg

	calc_all_files(folder)

if __name__ == "__main__":
   main(sys.argv[1:])