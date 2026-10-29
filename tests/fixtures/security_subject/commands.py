"""A constant-command hardening fixture, not an exploitable-user-input claim."""
import subprocess


def constant_output():
    return subprocess.check_output('/usr/bin/printf fixture', shell=True).decode('ascii')


def add_one(value):
    return value + 1
