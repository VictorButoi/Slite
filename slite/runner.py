from .utils import chunk_cfs, task

# misc imports
import submitit
import time
from typing import List

class SliteRunner:

    def __init__(
            self, 
            task_type,
            exp_name: str, 
            available_gpus: List[str], 
            log_root_dir: str='/storage/vbutoi/scratch'
            ):
        # Configure Submitit object
        submitit_root = f"{log_root_dir}/submitit/{exp_name}"
        self.executor = submitit.LocalExecutor(folder=submitit_root)
        self.executor.parameters['visible_gpus'] = available_gpus
        self.executor.parameters['timeout_min'] = int(24 * 60 * 7)
        # Keep track of important properties
        self.available_gpus = available_gpus
        self.task_type = task_type
        # Keep cache of jobs
        self.jobs = []
    
    def run_exps(self, cfg_list):

        cfg_chunks = chunk_cfs(cfg_list, num_gpus=len(self.available_gpus))
        for c_idx, cfg_chunk in enumerate(cfg_chunks):
            job = self.executor.submit(task, c_idx, self.task_type, cfg_chunk)
            print(f"Submitted job {job.job_id} with {len(cfg_chunk)} configs.")
            time.sleep(2) # Sleep for 2 seconds to avoid submitting too many jobs at once
            self.jobs.append(job)

    def kill_jobs(self):
        return None