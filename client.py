# client.py

# misc imports
import os
import sys
import argparse
import requests
import subprocess
from pprint import pprint   
# local imports
from slite.registry import LOCAL_VARS


def start_server():
    # Run the scheduler_server.py file in the slite directory.
    subprocess.run(["python", f"{LOCAL_VARS['SLITE_DIR']}/start_server.py"], cwd=LOCAL_VARS['SLITE_DIR'])


def relaunch_job(job_id):
    url = f"{LOCAL_VARS['SERVER_URL']}/relaunch"
    data = {'job_id': job_id}
    try:
        response = requests.post(url, json=data)
        if response.status_code == 200:
            result = response.json()
            status = result.get('status', 'Status Unknown.')
            print(status)
        else:
            error_message = response.json().get('error', 'No error message provided.')
            print(f"Failed to relaunch job {job_id}. Server responded with status code {response.status_code}: {error_message}")
    except requests.exceptions.ConnectionError:
        print("Failed to connect to the scheduler server. Is it running?")
        sys.exit(1)


def kill_job(job_id):
    url = f"{LOCAL_VARS['SERVER_URL']}/kill"
    data = {'job_id': job_id}
    try:
        response = requests.post(url, json=data)
        if response.status_code == 200:
            result = response.json()
            status = result.get('status', 'Status Unknown.')
            print(status)
        else:
            error_message = response.json().get('error', 'No error message provided.')
            print(f"Failed to kill job {job_id}. Server responded with status code {response.status_code}: {error_message}")
    except requests.exceptions.ConnectionError:
        print("Failed to connect to the scheduler server. Is it running?")
        sys.exit(1)


def inspect_job(job_id):
    url = f"{LOCAL_VARS['SERVER_URL']}/get_job"
    try:
        response = requests.get(url, json={'job_id': job_id})
        if response.status_code == 200:
            job_info = response.json()
            if not job_info:
                print(f"Job with id {job_id} not found.")
                return
            # Print the job information
            pprint(job_info)
        else:
            print(f"Failed to retrieve job with id {job_id}.")
    except requests.exceptions.ConnectionError:
        print("Failed to connect to the scheduler server. Is it running?")
        sys.exit(1)


def flush_jobs(status):
    url = f"{LOCAL_VARS['SERVER_URL']}/flush"
    data = {'status': status}
    try:
        response = requests.post(url, json=data)
        if response.status_code == 200:
            result = response.json()
            status = result.get('status', 'Status Unknown.')
            print(status)
        else:
            error_message = response.json().get('error', 'No error message provided.')
            print(f"Failed to flush jobs with status {status}. Server responded with status code {response.status_code}: {error_message}")
    except requests.exceptions.ConnectionError:
        print("Failed to connect to the scheduler server. Is it running?")
        sys.exit(1)


def list_jobs(status):
    url = f"{LOCAL_VARS['SERVER_URL']}/jobs"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            jobs = response.json()
            # Group jobs by status
            grouped_jobs = {}
            for job_id, job in jobs.items():
                job_status = job.get('status', 'unknown')
                grouped_jobs.setdefault(job_status, []).append({
                    'job_id': job_id,
                    'job_gpu': job.get('job_gpu')
                })

            # Print jobs based on chosen status or all
            statuses_to_display = ['queued', 'running', 'completed', 'failed', 'cancelled'] if status == 'all' else [status]
            for status in statuses_to_display:
                print(f"\n{status.capitalize()} Jobs:")
                for job in grouped_jobs.get(status, []):
                    print(f"  ID: {job['job_id']}, GPU: {job['job_gpu']}")
            print()
        else:
            print("Failed to retrieve jobs.")
    except requests.exceptions.ConnectionError:
        print("Failed to connect to the scheduler server. Is it running?")
        sys.exit(1)


# TODO: Fix, shutdown doesn't currently work.
def shutdown_scheduler():
    url = f"{LOCAL_VARS['SERVER_URL']}/shutdown"
    try:
        response = requests.post(url)
        if response.status_code == 200:
            print("Scheduler is shutting down.")
        else:
            print("Failed to shutdown scheduler.")
    except requests.exceptions.ConnectionError:
        print("Failed to connect to the scheduler server. Is it running?")
        sys.exit(1)


def main():
    # Create the parser
    parser = argparse.ArgumentParser(
        description="Local GPU Job Queue Client with Submitit"
    )
    parser.add_argument(
        '-flush', 
        metavar='STATUS', 
        choices=['queued', 'running', 'completed', 'failed', 'cancelled', 'all'], 
        help='Flush jobs based on their status'
    )
    parser.add_argument(
        '-kill', 
        metavar='JOB_ID', 
        type=str, 
        help='Kill a job with the given ID'
    )
    parser.add_argument(
        '-inspect', 
        metavar='JOB_ID', 
        type=str, 
        help='Inspect a job with the given ID'
    )
    parser.add_argument(
        '-list', 
        metavar='STATUS', 
        nargs='?', 
        const='all',
        choices=['queued', 'running', 'completed', 'failed', 'cancelled', 'all'], 
        help='List jobs based on their status (default is all)'
    )
    parser.add_argument(
        '-relaunch', 
        metavar='JOB_ID', 
        type=str, 
        help='Relaunch a finished-job with the given ID'
    )
    parser.add_argument(
        '-shutdown', 
        action='store_true', 
        help='Shutdown the scheduler server'
    )
    parser.add_argument(
        '-startup', 
        action='store_true', 
        help='Launch the slite job manager'
    )

    # Parse arguments
    args = parser.parse_args()

    if args.startup:
        start_server()
    elif args.list:
        list_jobs(args.list)
    elif args.shutdown:
        shutdown_scheduler()
    elif args.kill:
        if not args.kill:
            parser.error("-kill requires a job ID")
        kill_job(args.kill)
    elif args.relaunch:
        if not args.relaunch:
            parser.error("-relaunch requires a job ID")
        relaunch_job(args.relaunch)
    elif args.inspect:
        if not args.inspect:
            parser.error("-inspect requires a job ID")
        inspect_job(args.inspect)
    elif args.flush:
        if not args.flush:
            parser.error("-flush requires a status")
        flush_jobs(args.flush)
    else:
        parser.print_help()

if __name__ == '__main__':
    main()

