# submit.py

# misc imports
import sys
import time
import submitit
import requests
from typing import Any, List, Optional, Literal
from pydantic import validate_arguments
# local imports
from slite.registry import LOCAL_VARS


@validate_arguments(config=dict(arbitrary_types_allowed=True))
def submit_jobs(
    submit_params: dict,
    config_list: List[Any],
    mode: Literal['local', 'slurm'],
    submission_delay: int = 0.0,
    exp_class: Optional[Any] = None,
    job_func: Optional[Any] = None,
    available_gpus: Optional[List[str]] = None,
):
    # Precisely one of exp_class or job_func must be defined.
    assert (exp_class is not None) ^ (job_func is not None), \
        "Exactly one of exp_class or job_func must be defined."
    # We might have to convert exp_class and job_func to strings.
    if exp_class is not None and not isinstance(exp_class, str):
        exp_class = f"{exp_class.__module__}.{exp_class.__name__}"
    if job_func is not None and not isinstance(job_func, str):
        job_func = f"{job_func.__module__}.{job_func.__name__}"
    
    if mode == "slurm":
        for cfg in config_list:
            try:
                executor = submitit.AutoExecutor(folder=cfg['submitit_root'])
                executor.update_parameters(**submit_params)

                job = executor.submit(eval(job_func), cfg, available_gpus=available_gpus)
                print(f"--> Submitted job with ID: {job.job_id} and config: {cfg}")
                time.sleep(submission_delay)
            except Exception as e:
                print(f"Failed to submit job with config: {cfg}. Error: {e}")
    else:
        url = f"{LOCAL_VARS['SERVER_URL']}/submit"
        payload_defaults = {
            'job_func': job_func,
            'exp_class': exp_class,
            'submit_params': submit_params,
            'available_gpus': available_gpus,
        }
        for cfg in config_list:
            try:
                payload_dict = {
                    'config': cfg,
                    **payload_defaults
                }
                response = requests.post(url, json=payload_dict)
                time.sleep(submission_delay)
                if response.status_code == 200:
                    successful_job = response.json()
                    succ_job_status = successful_job.get('status')
                    if succ_job_status == 'running':
                        print(f"--> Launched job-id: {successful_job.get('job_id')} on gpu: {successful_job.get('job_gpu')}.")
                    elif succ_job_status == 'queued':
                        print(f"--> Queued job-id: {successful_job.get('job_id')}.")
                    else:
                        raise ValueError()
                else:
                    print(f"Failed to submit job: {response.json().get('error')}")
            except requests.exceptions.ConnectionError:
                print("Failed to connect to the scheduler server. Is it running?")
                sys.exit(1)