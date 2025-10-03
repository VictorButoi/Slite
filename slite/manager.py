# scheduler_server.py

# misc imports
import sys
import os
import queue
import GPUtil
import logging
import submitit
import threading
import traceback
logging.basicConfig(level=logging.DEBUG)
from typing import Optional, Any
from flask import Flask, request, jsonify
from pynvml import nvmlInit, nvmlDeviceGetCount, nvmlShutdown, nvmlDeviceGetHandleByIndex
# local imports
import slite.runner as slunner
from slite.registry import LOCAL_VARS


app = Flask(__name__)


class SliteGPUManager:

    def __init__(self, idle_gpu_memory=10):
        nvmlInit()
        self.num_gpus = nvmlDeviceGetCount()
        self.gpu_handles = [nvmlDeviceGetHandleByIndex(i) for i in range(self.num_gpus)]
        self.gpu_status = [True] * self.num_gpus  # True means free
        self.idle_gpu_memory = idle_gpu_memory

    def get_free_gpu(self):
        # TODO: Replace with a mechanism that checks without the hacks.
        gpu_objects = GPUtil.getGPUs()
        gpu_memory_free = []
        for gpu in gpu_objects:
            gpu_is_free = (gpu.memoryUsed <= self.idle_gpu_memory)
            gpu_memory_free.append(gpu_is_free)
        
        # The current gpu status will be a combination of the gpu_status and the gpu_memory_free
        current_gpu_status = [a and b for a, b in zip(self.gpu_status, gpu_memory_free)]

        for i, status in enumerate(current_gpu_status):
            if status:
                self.gpu_status[i] = False
                return i
        return None

    def release_gpu(self, job_gpu):
        if (job_gpu is not None) and (0 <= job_gpu < self.num_gpus):
            self.gpu_status[job_gpu] = True

    def shutdown(self):
        nvmlShutdown()


class SliteJobScheduler:
    def __init__(self):
        self.gpu_manager = SliteGPUManager()
        self.default_executer_params = {
            "timeout_min": 60*24*7,  # 7 days
            "slurm_additional_parameters": {
                "gres": "gpu:1"  # Placeholder, not used in local executor
            }
        }
        self.lock = threading.Lock()
        self.job_queue = queue.Queue()
        self.job_counter = 0
        self.all_jobs = {}  # Mapping from job_id to job info
        self.running_jobs = {}
        self.completed_jobs = {}

    def clear_job(
        self, 
        job_id,
    ):
        with self.lock:
            # Remove the job from the all_jobs dict
            self.all_jobs.pop(job_id, None)
            self.running_jobs.pop(job_id, None)
            self.completed_jobs.pop(job_id, None)

    def submit_job(self, data_obj: dict):
        cfg = data_obj['config']
        with self.lock:
            job_id = str(self.job_counter)
            self.job_counter += 1
            job_info = {
                "job_id": job_id,
                "cfg": cfg,
                "job_func": data_obj.get('job_func', None),
                "exp_class": data_obj.get('exp_class', None),
                "status": None,  # To be set below
                "job_gpu": None,
                "submitit_root": f'{cfg["log"]["root"]}/{cfg["log"]["uuid"]}/submitit'
            }
            self.all_jobs[job_id] = job_info

            job_gpu = self.gpu_manager.get_free_gpu()
            if job_gpu is None:
                # No GPU available, queue the job
                job_info["status"] = "queued"
                self.job_queue.put(job_id)
                return job_id  # Return the job_id to the user
            else:
                # GPU available, submit the job
                job_info["job_gpu"] = job_gpu
                return self._submit_to_executor(job_id, job_info)

    def relaunch_job(self, job_id):
        with self.lock:
            # Check if the job exists
            if job_id not in self.all_jobs:
                logging.error(f"Job {job_id} not found.")
                return False
            # Check if the job is currently running
            if job_id in self.running_jobs:
                logging.error(f"Job {job_id} is currently running and cannot be relaunched.")
                return False
            job_info = self.all_jobs[job_id]
            # Remove any previous job object and error messages
            job_info.pop('job_object', None)
            job_info.pop('error', None)
            # Reset job status and GPU assignment
            job_info["status"] = None
            job_info["job_gpu"] = None

            # Relaunch the job using the submit_job method
            job_gpu = self.gpu_manager.get_free_gpu()
            if job_gpu is None:
                # No GPU available, queue the job
                job_info["status"] = "queued"
                self.job_queue.put(job_id)
                return job_id  # Return the job_id to the user
            else:
                # GPU available, submit the job
                job_info["job_gpu"] = job_gpu
                return self._submit_to_executor(job_id, job_info)

    def kill_job(self, job_id):
        with self.lock:
            # Check if the job is running
            if job_id in self.running_jobs:
                job_info = self.running_jobs[job_id]
                job = job_info.get("job_object")
                if job is not None:
                    # Attempt to cancel the job
                    try:
                        job.cancel()
                        job_info["status"] = "cancelled"
                    except Exception as e:
                        logging.error(f"Failed to cancel job {job_id}: {e}")
                else:
                    logging.error(f"No job object found for job {job_id}")

                # Remove from running_jobs, add to completed_jobs
                self.running_jobs.pop(job_id)
                self.completed_jobs[job_id] = job_info
                # Release the GPU
                self.gpu_manager.release_gpu(job_info["job_gpu"])

                # Check if there are queued jobs
                if not self.job_queue.empty():
                    next_job_id = self.job_queue.get()
                    next_job_info = self.all_jobs[next_job_id]
                    # Try to get a GPU (should be available now)
                    job_gpu = self.gpu_manager.get_free_gpu()
                    if job_gpu is not None:
                        next_job_info["job_gpu"] = job_gpu
                        self._submit_to_executor(next_job_id, next_job_info)
                    else:
                        # This shouldn't happen, but just in case
                        next_job_info["status"] = "queued"
                        self.job_queue.put(next_job_id)
                return True
            elif job_id in self.all_jobs and self.all_jobs[job_id]["status"] == "queued":
                # Job is in queue, remove it
                # Since Queue doesn't support removal of arbitrary items, rebuild the queue
                new_queue = queue.Queue()
                while not self.job_queue.empty():
                    queued_job_id = self.job_queue.get()
                    if queued_job_id != job_id:
                        new_queue.put(queued_job_id)
                    else:
                        self.all_jobs[job_id]["status"] = "cancelled"
                        self.completed_jobs[job_id] = self.all_jobs[job_id]
                self.job_queue = new_queue
                return True
            else:
                logging.error(f"Job {job_id} is not running.")
                return False

    def _submit_to_executor(self, job_id, job_info):
        cfg = job_info["cfg"]
        job_func = job_info["job_func"]
        exp_class = job_info["exp_class"]
        job_gpu = job_info["job_gpu"]

        executor = submitit.LocalExecutor(job_info['submitit_root'])
        executor.update_parameters(**self.default_executer_params)
        
        # Ensure subprocess uses the same Python environment as the parent
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join(sys.path)
        # Preserve the current Python executable path
        if hasattr(sys, 'executable'):
            env["PYTHON_EXECUTABLE"] = sys.executable
        executor.update_parameters(env=env)

        submit_kwargs = {
            "config": cfg,
            "available_gpus": job_gpu
        }

        if exp_class is not None:
            job = executor.submit(
                slunner.run_exp, 
                exp_class=exp_class,
                **submit_kwargs
            )
        else:
            job = executor.submit(
                slunner.run_job, 
                job_func=job_func,
                **submit_kwargs
            )

        job_info["status"] = "running"
        job_info["job_object"] = job  # Store the job object

        # Place the job in the running_jobs dict.
        self.running_jobs[job_id] = job_info

        threading.Thread(target=self.monitor_job, args=(job_id, job), daemon=True).start()

        return job_id

    def monitor_job(self, job_id, job):
        try:
            job.result()  # This will block until the job finishes
            status = "completed"
        except Exception as e:
            status = "failed"
            with self.lock:
                self.running_jobs[job_id]["error"] = str(e)

        with self.lock:
            job_info = self.running_jobs.pop(job_id, None)
            job_info["status"] = status
            self.completed_jobs[job_id] = job_info

            # Release the GPU while holding self.lock
            self.gpu_manager.release_gpu(job_info["job_gpu"])

            # Check if there are queued jobs
            if not self.job_queue.empty():
                next_job_id = self.job_queue.get()
                next_job_info = self.all_jobs[next_job_id]
                # Try to get a GPU (should be available now)
                job_gpu = self.gpu_manager.get_free_gpu()
                if job_gpu is not None:
                    next_job_info["job_gpu"] = job_gpu
                    self._submit_to_executor(next_job_id, next_job_info)
                else:
                    # This shouldn't happen, but just in case
                    next_job_info["status"] = "queued"
                    self.job_queue.put(next_job_id)

    def list_jobs(self):
        with self.lock:
            jobs = {}
            # Include all jobs with their statuses
            for job_id, job_info in self.all_jobs.items():
                jobs[job_id] = {
                    "status": job_info["status"],
                    "job_gpu": job_info["job_gpu"],
                }
        return jobs

    def shutdown(self):
        self.gpu_manager.shutdown()
        # Optionally, cancel all running jobs and clear the queue
        with self.lock:
            for job_id, info in self.running_jobs.items():
                info["status"] = "cancelled"
            self.running_jobs.clear()
            # Clear queued jobs
            while not self.job_queue.empty():
                job_id = self.job_queue.get()
                self.all_jobs[job_id]["status"] = "cancelled"

# Initialize the scheduler
scheduler = SliteJobScheduler()

@app.route('/submit', methods=['POST'])
def submit_job_endpoint():
    try: 
        data = request.get_json()
        if not data or 'config' not in data:
            return jsonify({'error': 'No config provided.'}), 400
        # Submit the job
        job_id = scheduler.submit_job(data_obj=data)
        job_info = scheduler.all_jobs[job_id]
    except Exception as e:
        logging.error(f"Failed to submit job {job_id}: {e}")
        logging.error(traceback.format_exc())
        job_info = {
            "job_id": None,
            "status": "failed",
        }     
    return jsonify({'job_id': job_id, 'status': job_info["status"], 'job_gpu': job_info.get('job_gpu')}), 200

@app.route('/relaunch', methods=['POST'])
def relaunch_job_endpoint():
    try: 
        data = request.get_json()
        if not data or 'job_id' not in data:
            return jsonify({'error': 'No job-id provided.'}), 400
        jid = data['job_id']
        # Attempt to relaunch the job
        success = scheduler.relaunch_job(jid)
        if success:
            status = f"Job {jid} relaunched."
            return jsonify({"status": status}), 200
        else:
            status = f"Failed to relaunch job {jid}."
            return jsonify({"status": status}), 400
    except Exception as e:
        logging.error(f"Failed to relaunch job with {data.get('job_id', 'unknown')}: {e}")
        logging.error(traceback.format_exc())
        status = "Failed to relaunch job due to server error."
        return jsonify({"status": status}), 500

@app.route('/kill', methods=['POST'])
def kill_job_endpoint():
    try: 
        data = request.get_json()
        if not data or 'job_id' not in data:
            return jsonify({'error': 'No job-id provided.'}), 400
        jid = data['job_id']
        # Attempt to kill the job
        success = scheduler.kill_job(jid)
        if success:
            status = f"Job {jid} killed."
            return jsonify({"status": status}), 200
        else:
            status = f"Failed to kill job {jid}."
            return jsonify({"status": status}), 400
    except Exception as e:
        logging.error(f"Failed to kill job with {data.get('job_id', 'unknown')}: {e}")
        logging.error(traceback.format_exc())
        status = "Failed to kill job due to server error."
        return jsonify({"status": status}), 500

@app.route('/flush', methods=['POST'])
def flush_jobs_endpoint():
    try: 
        data = request.get_json()
        if not data or 'status' not in data:
            return jsonify({'error': 'No job type provided.'}), 400
        j_status = data['status']
        # If j_status is 'all' we flush all jobs
        if j_status == 'all':
            j_categories = ['queued', 'running', 'completed', 'failed', 'cancelled']
        else:
            j_categories = [j_status]
        # Loop through the job categories.
        try:
            # Go through all the different categories to flush them.
            for j_cat in j_categories:
                # We need to gather the job ids first to avoid changing the dict while iterating.
                j_cat_id_list = []
                for jid in list(scheduler.all_jobs.keys()):
                    if scheduler.all_jobs[jid]["status"] == j_cat:
                        j_cat_id_list.append(jid)
                # Now we can iterate over the job ids and flush them.
                for cat_jid in j_cat_id_list:
                    # If the category is 'running' or 'queued', we need to kill the jobs.
                    if j_cat in ['running', 'queued']:
                        scheduler.kill_job(cat_jid)
                    else:
                        scheduler.clear_job(cat_jid)
            # Capitalize j_status for the response
            status = f"{j_status.capitalize()} jobs flushed."
            return jsonify({"status": status}), 200
        except Exception as e:
            status = f"Failed to flush {j_status} jobs."
            return jsonify({"status": status}), 400
    except Exception as e:
        logging.error(f"Failed to flush jobs with {data.get('status', 'unknown')}: {e}")
        logging.error(traceback.format_exc())
        status = "Failed to flush jobs due to server error."
        return jsonify({"status": status}), 500

@app.route('/shutdown', methods=['POST'])
def shutdown_server():
    # Directly call scheduler shutdown and server shutdown within the request context
    scheduler.shutdown()  # Ensure that this line only runs if scheduler is defined
    func = request.environ.get('werkzeug.server.shutdown')
    if func is None:
        raise RuntimeError('Not running with the Werkzeug Server')
    # Run the shutdown function in a separate thread if needed
    threading.Thread(target=func).start()
    
    return jsonify({"message": "Server is shutting down..."}), 200

@app.route('/get_job', methods=['GET'])
def get_job():
    try: 
        data = request.get_json()
        if not data or 'job_id' not in data:
            return jsonify({'error': 'No job-id provided.'}), 400
        # Submit the job
        job_info = scheduler.all_jobs[data['job_id']].copy()
        # Pop the job object to avoid serialization errors
        job_info.pop("job_object", None)
    except Exception as e:
        logging.error(f"Failed to gather job {data['job_id']}: {e}")
        logging.error(traceback.format_exc())
        job_info = {
            "job_id": None,
            "status": "failed",
        }     
    return jsonify(job_info), 200

@app.route('/jobs', methods=['GET'])
def get_jobs():
    jobs = scheduler.list_jobs()
    return jsonify(jobs), 200

if __name__ == '__main__':
    # Run the Flask app
    port = LOCAL_VARS['SERVER_URL'].split(':')[-1]
    app.run(host='0.0.0.0', port=port, threaded=True)
