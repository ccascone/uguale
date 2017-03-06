import math
import numpy as np

from uconf import RECORD_BEGIN, RECORD_END, IPERF_REPORT_INTERVAL, BIRTH_TIMEOUT


def test_is_valid(test):
    # all users must arise within a timeout
    data = test["data"]
    params = test["params"]
    duration = params["duration"]
    n_users = len(params['source_confs'])

    max_noshow_seconds = 5
    min_val = 100  # bit/s
    max_small_samples = 0.10

    expected_reports = float(duration - RECORD_BEGIN - RECORD_END) / IPERF_REPORT_INTERVAL
    max_noshow_reports = float(max_noshow_seconds) / IPERF_REPORT_INTERVAL

    flag = True

    if not data:
        print "Data is None"
        return False

    # Check if the SUM process (bwm-ng) has worked
    if len(data["SUM"]["total"]["t"]) < (expected_reports / 2.0):
        print "Warn: no SUM process"
        #return False

    # Check if there are all iperf users
    if (len(data) - 1) < n_users:
        print "ERROR: Expected {} active users, found {}".format(n_users, len(data) - 1)
        flag = False

    for src in data:
        if src != "SUM":
            if data[src]["tcp"]["t"][0] > BIRTH_TIMEOUT:
                print "ERROR: {} born after birth timeout ({}s)".format(src, data[src]["tcp"]["t"][0])
                flag = False

            if data[src]["tcp"]["t"][-1] < duration - RECORD_END:
                print "ERROR: {} died prematurely ({}s)".format(src, data[src]["tcp"]["t"][-1])
                flag = False

            sampleslen = len((trim_samples(data[src]["tcp"], duration))[1])
            if math.fabs(sampleslen - expected_reports) > max_noshow_seconds:
                print "ERROR: expected {} samples (+\-{}), but {} has {}".format(expected_reports, max_noshow_reports,
                                                                                 src, sampleslen)
                flag = False

            np_val_array = np.array(data[src]["tcp"]["val"])
            # check the number of small samples (if too many samples are too small, then somthing went wrong...)
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
        if ts > RECORD_BEGIN:
            break
    first = i + 1

    last_valid_instant = duration - RECORD_END

    last = 0
    for i in range(len(samples["t"])):
        ts = samples["t"][i]
        if ts > last_valid_instant:
            break
    last = i - 1

    return [samples["t"][first:last], samples["val"][first:last]]
