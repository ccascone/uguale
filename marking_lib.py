
from mylib import *
from tc_lib import *

"""
This library creates the dict of rates {rate: DSCP}
example with 3 colors:

------------- <---4000
|			|
|	3		|
------------- <---2000
|	2		|
------------- <---1000
|	1		|
-------------

rates={
	1000 : 1
	2000 : 2
	4000 : 3
}

key is the threshold
value is the DSCP
"""


"""
Return the dict of rates
es.
rates = {
 	bn_cap or slightly greater : X+1
	mmr : X
	...
	rate3 :  3
	rate2 :  2
	g_rate :  1
"""
def get_rates(g_rate, bn_cap, m_m_rate, num_colors):

	rates={}
	delta = float(m_m_rate)/(num_colors-1)
	rates = {}
	rates[g_rate]=1
	for i in range(1,num_colors):
		dscp = i+1
		new_rate = g_rate + (i*delta)
		if (new_rate >= bn_cap) or (dscp==num_colors):
			new_rate = bn_cap

		rates[new_rate] = dscp
		if new_rate>=bn_cap:
			break
			
	return rates


"""
Parameters must be numbers, return string

if guard_bands == -1, do not use MMR --> mmr = (num_colors-1)*(C/float(num_colors))

Es. guard bands = 2

--------- <-- bn_cap
|		|
|		|
|	8	|
|		|
|		|
--------- <--mmr MAXIMUM MARKING RATE (maximum rate to consider "active")
|	7	|
---------
|	6	|
--------- <--mfr MAXIMUM FAIR RATE (maximum rate at wich an user will converge)
|	5	|
---------
|	4	|
---------
|	3	|
---------
|	2	|
---------
|	1	|
---------
"""
def get_marker_max_rate(g_rates, free_b, C, n_users, guard_bands, num_colors):

	# If not used, c must be divided simply in num_colors bands
	if guard_bands == -1 or guard_bands>=num_colors:
		return (num_colors-1)*(C/float(num_colors))

	g_max = max(map(rate_to_int, g_rates)) # maximum guaranteed rate [int] 
	mfr = g_max + ((free_b*C)/float(n_users)) # maximum fair rate at which an user will converge

	if guard_bands == 0:
		return mfr

	if (num_colors-guard_bands-1)>0:
		delta = mfr/float(num_colors-guard_bands-1)
	else:
		delta = mfr

	mmr = (mfr + (guard_bands*delta)) # maximum marking rate

	#print "MFS{} - DELTA{} - MMR {}".format(num_to_rate(mfr), num_to_rate(delta), num_to_rate(mmr))
	return min(mmr, C)





"""
Return the multipliers that will compensate the effect of rtt
This works only if everyone must obtain the same EFR
old law: return (0.3*np.log(x)) #LAW3
"""
def get_rtt_coefficients(rtts,C,n_users, strenght=0.15):
	"""
	goodput_1 / goodput_i = RTT_i / RTT_1 

	goodput_i = RTT_1/RTT_i * goodput_1
	we put goodput_1=1

	m_u = (c*rtt_u)/(N*rtt_1*r1)

	"""
	r=[] # list of estimated rates
	coeffs=[] # list of coefficients that compensate RTT
	rtt_min = min(rtts)

	for rtt in rtts:
		r.append(float(rtt_min)/rtt)

	c = np.sum(r)

	# see luca's thesis aproach/rtt compensation
	m = float(c)/(n_users*rtt_min)
	q = 0

	# If requested, multiply the angular coefficient time strenght
	# and center the line on the middle value
	if strenght != 1:
		x_mean = np.mean(rtts)
		y_mean = m*x_mean
		m = m*strenght
		q = y_mean - (m*x_mean)

	for i in range(n_users):
		mult = (m*rtts[i])+q
		coeffs.append(max(mult,0))
	# print m,q
	# print sorted(coeffs)

	"""
	If possible, normalize coefficients so that the middle rtt gets m_u=1
	by subtracting a fixed value.
	it is possible only if the min coeff does not become negative
	"""
	middle_rtt = np.mean([max(rtts),min(rtts)])
	val_middle = (m*middle_rtt)+q 
	norm_delta = val_middle - 1
	# print min(rtts), middle_rtt, max(rtts), val_middle, norm_delta
	if(min(coeffs)-norm_delta)>0.0:
		coeffs = map(lambda x: x-norm_delta, coeffs)
	# print sorted(coeffs)
	return coeffs




"""
find the maximum DSCP assigned in the dict
"""
def max_dscp(rates):
	maxd = 0
	for rate in rates:
		if rates[rate]>maxd:
			maxd = rates[rate]
	return int(maxd)



"""
print the dict of rates 
"""
def print_rates(rates, bn_cap):
	previous_rate = 0
	for rate in sorted(rates):
		dscp = rates[rate]
		delta = rate - previous_rate
		print "[{} - {}] \t---> DSCP {} ({} wide)".format(num_to_rate(previous_rate), num_to_rate(rate), dscp, num_to_rate(delta))
		previous_rate = rate


"""
Convert the dict of rates in a sorted list of rates expressed in byte/s
Udsed for python marker
[2000-3000] --> 3
[1000-2000]	--> 2
[0-1000] 	--> 1

es:{1000:1, 2000:2, 3000:3} ==> [0, 1000/8, 2000/8, 3000/8]
"""
def rates_to_list_bytes(rates):
	r = [0]
	for rate in sorted(rates):
		r.append(int(rate/8.0))
	return r




	

