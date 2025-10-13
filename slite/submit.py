# misc imports
import sys
import time
import submitit
import requests
from pathlib import Path
from typing import Any, List, Optional
from pydantic import validate_arguments
# local imports
from slite.runner import run_exp
from slite.registry import LOCAL_VARS


@validate_arguments(config=dict(arbitrary_types_allowed=True))
def submit_jobs(
    submit_cfg: dict,
    config_list: List[Any],
    job_func: Optional[Any] = None,
):
    # We might have to convert exp_class and job_func to strings.
    if job_func is not None and not isinstance(job_func, str):
        job_func = f"{job_func.__module__}.{job_func.__name__}"
    
    if submit_cfg['mode'] == "slurm":
        for cfg in config_list:
            try:
                log_root = Path(cfg['log']['root'])
                ae_path = log_root / cfg['log']['uuid'] / "submitit"
                executor = submitit.AutoExecutor(folder=ae_path)
                executor.update_parameters(**submit_cfg['slurm_args'])
                job = executor.submit(run_exp, cfg)
                print(f"--> Submitted job with ID: {job.job_id}.")
                time.sleep(submit_cfg.get('submission_delay', 0.0))
            except Exception as e:
                print(f"Failed to submit job with config: {cfg}. Error: {e}")
    else:
        url = f"{LOCAL_VARS['SERVER_URL']}/submit"
        # If exp_class is defined, then we need to submit an experiment; otherwise, we need to submit a job!
        if job_func is not None:
            submit_cfg['job_func'] = job_func
        # Iteratre over the config list and submit each job.
        for cfg in config_list:
            try:
                payload_dict = {
                    'config': cfg,
                    **submit_cfg
                }
                response = requests.post(url, json=payload_dict)
                time.sleep(submit_cfg.get('submission_delay', 0.0))
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