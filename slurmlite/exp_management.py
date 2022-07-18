import pandas as pd
import os
import yaml
import pprint
import glob
import shutil
import torch
from notebook_utils.misc_utils import *
from notebook_utils.run_funcs import *
from os import system
from tqdm import tqdm
import time


def tmux(command):
    system('tmux %s' % command)


def tmux_shell(command):
    tmux('send-keys "%s" "C-m"' % command)


def create_gridsearch(params):
    new_dicts = []
    first_dicts = True

    #go through all options you want to set
    for key in params.keys():
        prepared_new_dicts = []
        for option in params[key]:
            nd = {
                key: option
            }
            prepared_new_dicts.append(nd)
        if first_dicts:
            for nd in prepared_new_dicts:
                new_dicts.append(nd)
        else:
            old_dicts = new_dicts
            merged_dicts = []
            for od in old_dicts:
                for nd in prepared_new_dicts:
                    merged_dicts.append(merge_dicts(od, nd))
            new_dicts = merged_dicts
        first_dicts = False

    pprint.pprint(new_dicts)

    return new_dicts

def run_exps(exp_manager, names, grid_params):
    assert len(names) == len(grid_params), "Each thing in gridsearch must have a name"

    PROJECT_PATH = "/persist/S4ndwich"
    ACTIVATE_VENV = "conda activate S4-env"

    job_objects = []

    for pi, param in enumerate(grid_params):
        print("Created tmux window:", names[pi])
        #Make a new tmux window
        tmux(f'new-window -n {names[pi]}')
        #CD and Change env
        tmux_shell('cd %s' % PROJECT_PATH)
        tmux_shell(ACTIVATE_VENV)
        #Get the shell command
        hash = str(random.getrandbits(128))
        run_string, debug_string = exp_manager.get_run_string(names[pi], param, hash)
        #Run command
        print("Running command:", debug_string)
        tmux_shell(run_string)
        #Go back to original window
        tmux_shell('tmux select-window -t 0')
        job_gathered = False
        # create job objects
        while(not job_gathered):
            f = open("/persist/S4ndwich/overhead/work_dirs.txt", 'r')
            jobs = f.read().split("\n")
            f.close()
            #Not the best way to do this, but nothing about my code is the "best way to do this"
            for job in jobs:
                if hash in job:
                    job_gathered = True
                    job_name = job.split("$")
                    print("Gathered Jobs:", job_name[1])
                    job_objects.append(Job(job_name[1]))
                    break
        #Buffer running so the automatic gpu distribution
        time.sleep(5)

    return job_objects


def kill_jobs(keep_id_list=None):
    # Subtract 1 to account for the jupyter window
    windows = sp.getoutput('tmux list-windows -F "#I"').split("\n")
    if keep_id_list:
        for id in keep_id_list:
            windows.remove(str(id))
    windows.remove('0')
    num_windows = len(windows)
    close_command = input(f"Are you sure you want to close {num_windows} windows (Y/y)?: ")
    if close_command in ["Y", "y"]:
        for session_id in windows:
            print("Killed tmux session:", session_id)
            tmux(f'kill-window -t {session_id}')


class Job:

    def __init__(self, root):
        self.run_dir = root

    @property
    def error(self):
        error_file = os.path.join(self.run_dir, "error.log")
        try:
            f = open(error_file)
            text = f.read()
            f.close()
            pprint.pprint(text)
        except:
            print("")
