import os
import subprocess
from sys import stderr

import pexpect as pexpect

FNULL = open(os.devnull, "w")


def cmd(command, sudo=False):
    # TODO: check stderr
    if sudo:
        command = 'sudo ' + command
    subprocess.call(command, shell=True)


def iterate_cmd_out(command):
    """
    Executes a programm (command string) and iterate over stdout lines
    """
    child = pexpect.spawn(command, timeout=None)
    for line in child:
        yield line


def launch_bg(command, do_print=False):
    """
    Executes a command in background (no output!)
    """
    if do_print:
        print command
    return subprocess.Popen(command.split(), stdout=FNULL)


def cmd_ssh_xterm(host, command, do_print=False):
    """
    Open an XTERM and send an SSH command
    """
    cmd_str = "(xterm -hold -e \"ssh {} '{}'\") & ".format(host, command)
    cmd(cmd_str)
    if do_print:
        print cmd_str


def cmd_ssh(host, command, do_print=False):
    """
    Send an SSH command and wait for
    the remote task to complete.
    """
    local_cmd = "/usr/bin/ssh", host, command
    if do_print:
        print "*** Executing SSH command: {}".format(local_cmd)
    try:
        result = subprocess.check_output(local_cmd, stderr=subprocess.STDOUT, shell=False)
    except subprocess.CalledProcessError as e:
        result = e.output
        print >> stderr, "*** Error with SSH command {}: {}".format(local_cmd, result)
    return result


def cmd_ssh_bg(host, command, do_print=False):
    """
    Send an SSH command and return immediately.
    """
    local_cmd = "/usr/bin/ssh", host, command
    if do_print:
        print "*** Executing SSH command in background: {}".format(local_cmd)
    subprocess.Popen(local_cmd, stdout=FNULL, stderr=FNULL, shell=False)


def killall_str(process_name, arg=None):
    if arg is not None:
        grep_str = "{}.*{}".format(process_name, arg)
    else:
        grep_str = str(process_name)
    return "for pid in $(ps -ef | grep \"" + grep_str + "\" | awk '{print $2}'); do sudo kill -9 $pid; done"


def killall(process_name, arg=None):
    """
    Effectivelly kill all process with given name
    and optional arguments (used to launch the process)
    """
    cmd(killall_str(process_name, arg))
