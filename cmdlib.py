import subprocess


def cmd(command, exit_on_error=True, sudo=False):
    # TODO: check stderr
    if sudo:
        command = 'sudo ' + command
    subprocess.call(command, shell=True)
