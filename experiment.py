import glob
import hashlib
import os
import pickle
import socket
import threading
import time
from subprocess import CalledProcessError

import pserver as ps
import validator
from cmdlib import cmd
from misc import filter_callables, pdict_to_str
from scripter import gen_scripts
from source_conf import gen_source_confs, rates_fan, CONF_RANGE
from switch import SW_TYPE_UGUALE
from uconf import SYNC_TIME, BIRTH_TIMEOUT, SERVER, DURATION

this_machine = socket.gethostname()

NUM_INSTANCES = 1


class Experiment:
    def __init__(self, spc, conn_conf, rtt_conf, rate_conf, sw_type, duration, sim_group=None):
        self.spc = spc
        self.conn_conf = conn_conf
        self.rtt_conf = rtt_conf
        self.rate_conf = rate_conf
        self.sw_type = sw_type
        self.duration = duration
        self.sim_group = 'all' if not sim_group else sim_group

        descr_dict = dict(spc=spc, conn_conf=conn_conf, rtt_conf=rtt_conf, rate_conf=rate_conf, sw_type=sw_type,
                          duration=duration)
        descr_str = pdict_to_str(descr_dict)
        self.sim_name = hashlib.sha1(descr_str).hexdigest()[:7]
        self.fname_idx = len(glob.glob('./results/%s/%s-*.p' % (self.sim_group, self.sim_name))) + 1
        self.results_fname = './results/%s/%s-%s.p' % (self.sim_group, self.sim_name, self.fname_idx)

        if not os.path.exists('./results/' + self.sim_group):
            os.makedirs('./results/' + self.sim_group)

    def need_to_run(self):
        return self.fname_idx <= NUM_INSTANCES

    def copy_to(self, addr, fname):
        actual_fname = fname.split('/')[-1]
        if addr != this_machine:
            self._print("Copying %s to %s:/tmp..." % (fname, addr))
            cmd('scp %s %s:/tmp/%s' % (fname, addr, actual_fname))

    def run_script(self, addr, fname, sleep_seconds=None, run_cmd='sh -x'):
        if sleep_seconds:
            time.sleep(sleep_seconds)
        actual_fname = fname.split('/')[-1]
        if addr != this_machine:
            self._print("Running %s on %s..." % (fname, addr))
            output = cmd("ssh %s '%s /tmp/%s'" % (addr, run_cmd, actual_fname))
        else:
            self._print("Running %s here..." % fname)
            output = cmd('%s %s' % (run_cmd, fname))
        print output

    def _print(self, msg):
        tname = threading.current_thread().getName()
        print "[EXP-%s-%s] %s" % (self.sim_name, tname, msg)

    def run(self):
        source_confs, info = gen_source_confs(spc=self.spc, conn_conf=self.conn_conf, rtt_conf=self.rtt_conf,
                                              rate_conf=self.rate_conf)

        self._print("Starting experiment %s-%s..." % (self.sim_name, self.fname_idx))
        self._print("This machine: %s" % this_machine)

        params = dict(spc=self.spc, conn_conf=self.conn_conf, rtt_conf=self.rtt_conf, source_confs=source_confs,
                      rate_conf=self.rate_conf, sw_type=self.sw_type, duration=self.duration, time=time.time(),
                      info=info, sim_group=self.sim_group)
        # Substitute functions with their names
        params = filter_callables(params)

        # Write scripts in ./gen
        # Get a dict like: client_addr -> [script_fname, ..]
        scripts = gen_scripts(source_confs=source_confs, sw_type=self.sw_type, duration=self.duration)

        self._print(
            "Generated scripts\n\t%s" % '\n\t'.join(['%s -> %s' % (k, '; '.join(v)) for k, v in scripts.items()]))

        iperf_scripts = {h: [] for h in scripts}
        ping_scripts = {h: [] for h in scripts}

        try:
            # Copy scripts to machines
            for addr, fnames in scripts.items():
                for fname in fnames:
                    if 'iperf' in fname:
                        iperf_scripts[addr].append(fname)
                    if 'ping' in fname:
                        ping_scripts[addr].append(fname)
                    self.copy_to(addr, fname)

            # Exec them (provisioning only)
            for addr, fnames in scripts.items():
                for fname in fnames:
                    if 'iperf' not in fname and 'ping' not in fname:
                        # Will run iperf later, now just machine provisioning
                        self.run_script(addr, fname)

            # iperf_s_cmd = get_detach_cmd('ip netns exec ns-sink iperf -s -i1', log='/tmp/iper_server.log')
            # run_cmd(this_machine, iperf_s_cmd)

            # Ping scripts
            for addr, fnames in ping_scripts.items():
                for fname in fnames:
                    self.run_script(addr, fname)

            for addr, fnames in iperf_scripts.items():
                for fname in fnames:
                    t = threading.Thread(target=self.run_script, args=(addr, fname, SYNC_TIME), name=fname)
                    t.start()

            # Start server
            self._print("Starting the server...")

            data = ps.run_server(
                interface=SERVER['intf'], tcp_ports=[5001], udp_ports=[],
                interactive=False,
                duration=self.duration + SYNC_TIME + 2,
                do_visualize=False,
                expected_users=len(source_confs),
                check_time=BIRTH_TIMEOUT + SYNC_TIME,
                cprefix='ip netns exec ns-sink')

        except CalledProcessError as e:
            self._print("! Abort as cmd returned %s" % e.returncode)
            self._print("cmd: %s" % e.cmd)
            self._print("output:\n%s" % e.output)
            return

        # ---------------------- SAVING ----------------------#
        test = {"params": params, "data": data}

        if not validator.test_is_valid(test):
            self._print("Test was not valid, results won't be saved to disk")
            return False

        # Save the test in a file
        pickle.dump(test, open(self.results_fname, "wb"))
        return True
        # append results to CSV


def main():
    rate_conf = dict(num_bands=8, func=rates_fan, alpha=0.9)
    conn_conf = dict(type=CONF_RANGE, range=(2, 10))
    rtt_conf = dict(type=CONF_RANGE, range=(40, 40))
    exp = Experiment(spc=10, conn_conf=None, rate_conf=rate_conf, rtt_conf=rtt_conf, sw_type=SW_TYPE_UGUALE,
                     duration=DURATION)
    exp.run()


if __name__ == '__main__':
    main()
