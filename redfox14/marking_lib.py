#!/usr/bin/python
"""
Manage the assignment of bands and 
creates the dict of rates (rate: DSCP)
"""
from mylib import *
"""
example of rate dict (bn_cap = 4000, num_bands = 3)
-------------- <---4000
|			 |
|	DSCP = 3 |
-------------- <---2000   ===> rates = {1000 : 1,
|	DSCP = 2 |							2000 : 2, 
-------------- <---1000 				4000 : 3 }
|	DSCP = 1 |
--------------
So the key is the threshold and the value is the DSCP
"""

"""
Return the dict of rates
"""
def get_rates(g_rate, bn_cap, m_m_rate, num_bands, do_symm, e_f_rate):

	rates = {}

	if do_symm:

		if num_bands == 2:
			rates[e_f_rate] = 1			
			rates[bn_cap] = 2 
		else:
			num_symm_bands = num_bands - 2 # number of equispaced bands
			semi_symm_width = m_m_rate - e_f_rate
			delta = semi_symm_width / (num_symm_bands / 2.0) # width of each symmetric band

			"""
			Find the first threshold (thr) for symmetric bands.
			If the first threshold is too small,
			aggregate it to the next one
			"""
			thr = e_f_rate - semi_symm_width

			if thr >= MIN_BAND_WIDTH:
				dscp = 1
				rates[thr] = 1 
			else: # case 2
				dscp = 0
				thr = max(thr, 0)

			for i in range(num_symm_bands):
				thr += delta
				dscp += 1
				rates[thr] = dscp

			rates[bn_cap] = dscp + 1 

	else:
		delta = float(m_m_rate) / (num_bands - 1)
		rates[g_rate]=1
		for i in range(1, num_bands):
			dscp = i + 1
			new_rate = g_rate + (i * delta)
			if (new_rate >= bn_cap) or (dscp==num_bands):
				new_rate = bn_cap

			rates[new_rate] = dscp
			if new_rate>=bn_cap:
				break
	return rates


"""
NOTE ON PARAMS: 
- g_rates: list of rates (strings)
- free_b: 0 < X < 1
- C : bn_cap as integer 
- if guard_bands == -1, do not use MMR 
	==> mmr = (num_bands-1)*(C/float(num_bands))
	==> Divide C in num_bands and return the rate of the penultimate


Example (num_bands = 8, guard bands = 2, do_symm = False)
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
--------- <--mfr MAXIMUM FAIR RATE (maximum rate at wich an user should converge)
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

Example (num_bands = 8, do_symm = True, symm_width)
--------- <--- bn_cap or C
|		|
|	8	|
|		|
--------- <--- b = EFR + symm_width/2 = MMR 	|
|	7	|										|
---------										|
|	6	|										|
---------										|
|	5	|										|
--------- <---- EFR 							| = symmetric width
|	4	|						 				|	
---------						 				|
|	3	|						 				|
---------						 				|
|	2	|						 				|
--------- <--- a = EFR - symm_width/2 			|
|		|
|	1	|
|		|
---------
[a,b] is divided into num_bands-2 bands.
The band #1 is assigned to rates lower than a
The band #num_bands is assigned to rates bigger than b
Since the EFR must be between two bands, 
only even num_bands are expected.

If the symmetric interval cannot be applied
(because the width is greater than 2*EFR)
In this case:
- the symmetric width is truncated to 2*EFR 
- band#1 is the first band used anyway
- band#num_bands will not be used (the last will be num_bands-1)
Example (num_bands = 8, do_symm = True, symm_width/2 >= EFR)
--------- <--- bn_cap or C
|		|
|		|
|		|
|	7	|
|		|
|		|
|		|
--------- <--- b = 2*EFR = MMR 	|
|	6	|						|
---------						|
|	5	|						|
---------						|
|	4	|						|
--------- <---- EFR 			| = 2 * EFR
|	3	|						|						 	
---------						|
|	2	|						| 
---------						|
|	1	|						| 
--------- <--- a = 0			|
"""
def get_marker_max_rate(C, n_users, g_rates, e_f_rates, 
	num_bands, guard_bands, do_symm, symm_width): 

	if do_symm:
		efr = min(map(rate_to_int, e_f_rates))

		if num_bands == 2:
			return efr

		semi_amp = (rate_to_int(symm_width)) / 2.0

		if semi_amp < efr: # The symmetric width is contained
			return efr + semi_amp
		else: # The symmetric width must be reduced
			return 2 * efr 

	"""
	Maximum fair rate at which an user will converge.
	When users have the same g_u, this is the EFR
	"""  
	mfr = max(map(rate_to_int, e_f_rates))

	# If the mmr is not used, c must be divided simply in num_bands bands
	if guard_bands == -1 or guard_bands >= num_bands:
		return (num_bands - 1) * (C / float(num_bands))

	if guard_bands == 0:
		return mfr

	# normal mmr case
	if (num_bands - guard_bands - 1) > 0:
		delta = mfr / float(num_bands - guard_bands - 1)
	else:
		delta = mfr

	mmr = (mfr + (guard_bands * delta)) # maximum marking rate
	return min(mmr, C)

"""
Return the multipliers that will compensate the effect of rtt
This works only if everyone must obtain the same EFR
old law: return (0.3*np.log(x)) #LAW3
"""
def get_rtt_coefficients(rtts, C, n_users, strenght=0.15):
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
		r.append(float(rtt_min) / rtt)

	c = np.sum(r)

	# see luca's thesis aproach/rtt compensation
	m = float(c) / (n_users * rtt_min)
	q = 0

	# If requested, multiply the angular coefficient time strenght
	# and center the line on the middle value
	if strenght != 1:
		x_mean = np.mean(rtts)
		y_mean = m * x_mean
		m = m * strenght
		q = y_mean - (m * x_mean)

	for i in range(n_users):
		mult = (m * rtts[i]) + q
		coeffs.append(max(mult, 0))
	# print m,q
	# print sorted(coeffs)

	"""
	If possible, normalize coefficients so that the middle rtt gets m_u=1
	by subtracting a fixed value.
	it is possible only if the min coeff does not become negative
	"""
	middle_rtt = np.mean([max(rtts), min(rtts)])
	val_middle = (m * middle_rtt) + q 
	norm_delta = val_middle - 1
	# print min(rtts), middle_rtt, max(rtts), val_middle, norm_delta
	if(min(coeffs) - norm_delta)>0.0:
		coeffs = map(lambda x: x - norm_delta, coeffs)
	# print sorted(coeffs)
	return coeffs

"""
find the maximum DSCP assigned in the dict
"""
def max_dscp(rates):
	maxd = 0
	for rate in rates:
		if rates[rate] > maxd:
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
Verify:
import marking_lib as ml; C = 94100000; nb=2; nu = 6; efr= C/float(nu); 
mmr=ml.get_marker_max_rate(C, nu, [], [efr]*nu, nb, 2 ,True); 
rates = ml.get_rates(0,C,mmr,nb,True,efr); ml.print_rates(rates,C)

import marking_lib as ml; C = 94100000; 
nb=2; nu = 6; sw = "20.0m" 
efr= C/float(nu); mmr=ml.get_marker_max_rate(C, nu, [], [efr]*nu, nb, 2 ,True, sw); rates = ml.get_rates(0,C,mmr,nb,True,efr); ml.print_rates(rates,C)
"""
