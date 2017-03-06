import sys
import time
from StringIO import StringIO

from experiment import Experiment
from misc import pdict_to_str
from sim_params import generate_param_dicts


class Capturing(list):
    def __enter__(self):
        self._stdout = sys.stdout
        self._stderr = sys.stderr
        self._stringio = StringIO()
        sys.stdout = self._stringio
        sys.stderr = self._stringio
        return self

    def __exit__(self, *args):
        self.extend(self._stringio.getvalue().splitlines())
        del self._stringio  # free up some memory
        sys.stdout = self._stdout
        sys.stderr = self._stderr


def eta(seconds):
    eta_minutes = seconds / 60.0
    if eta_minutes < 60:
        return "%.0f minutes" % eta_minutes
    else:
        eta_hours = eta_minutes / 60
        if eta_hours < 24:
            return "%.1f hours" % eta_hours
        else:
            return "%.1f days" % (eta_hours / 24.0)


def main():
    sim_list = generate_param_dicts()
    delta_tss = []

    print "Will perform %s experiments" % len(sim_list)

    for i in range(1, len(sim_list)+1):
        params = sim_list[i-1]
        start_ts = time.time()
        exp = Experiment(**params)
        results_fname = exp.results_fname
        if not exp.need_to_run():
            print "# Skipping experiment %s/%s, no need to run: %s..." % (i, len(sim_list), results_fname)
            continue
        log_fname = results_fname + '.log'
        print "# Starting experiment %s/%s: %s..." % (i, len(sim_list), results_fname)
        print "Params: %s" % pdict_to_str(params)
        with Capturing() as out:
            result = exp.run()
        with open(log_fname, 'w') as f:
            f.write('\n'.join(out))
        if not result:
            print "FAIL! See log at %s" % log_fname
        end_ts = time.time()
        delta_tss.append(end_ts - start_ts)
        avg_dur = sum(delta_tss) / float(len(delta_tss))
        eta_seconds = avg_dur * (len(sim_list) - i)
        print "[ETA %s]" % eta(eta_seconds)


if __name__ == '__main__':
    main()
