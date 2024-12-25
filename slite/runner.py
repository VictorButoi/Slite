# run_jobs.py

# misc imports
import os
import sys
import importlib
from typing import Any, Optional
from pydantic import validate_arguments


def absolute_import(reference):
    module, _, attr = reference.rpartition(".")
    if importlib.util.find_spec(module) is not None:
        module = importlib.import_module(module)
        if hasattr(module, attr):
            return getattr(module, attr)

    raise ImportError(f"Could not import {reference}")


@validate_arguments(config=dict(arbitrary_types_allowed=True))
def run_exp(
    exp_class: Any,
    config: Any,
    available_gpus: Optional[int] = None,
):
    # Important imports, otherwise the processes will not be able to import the necessary modules
    for sys_path in config['experiment'].get('sys_paths', []):
        sys.path.append(sys_path)
    # Regular schema dictates that we put DATAPATH
    os.environ['DATAPATH'] = ':'.join(config['experiment'].get('data_paths', []))
    # Set the visible gpu.
    if available_gpus is not None:
        os.environ["CUDA_VISIBLE_DEVICES"] = str(available_gpus)
    # If exp_class is a string, them we need to import it
    if isinstance(exp_class, str):
        exp_class = absolute_import(exp_class)
    # NOTE: config must be a pylot 'Config' object.
    exp = exp_class.from_config(config, uuid=config['log']['uuid'])
    # Run the experiment.
    exp.run()


@validate_arguments(config=dict(arbitrary_types_allowed=True))
def run_job(
    job_func: Any,
    config: Any,
    available_gpus: Optional[int] = None 
):
    # Important imports, otherwise the processes will not be able to import the necessary modules
    for sys_path in config['experiment'].get('sys_paths', []):
        sys.path.append(sys_path)
    # Regular schema dictates that we put DATAPATH
    os.environ['DATAPATH'] = ':'.join(config['experiment'].get('data_paths', []))
    # Set the visible gpu.
    if available_gpus is not None:
        os.environ["CUDA_VISIBLE_DEVICES"] = str(available_gpus)
    # If exp_class is a string, them we need to import it
    if isinstance(job_func, str):
        job_func = absolute_import(job_func)
    # NOTE: config must be a pylot 'Config' object.
    job_func(config)
