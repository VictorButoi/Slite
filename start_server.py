# start_server.py

# misc imports
import os
import sys
import time
import requests
import subprocess
from datetime import datetime
# local imports
from slite.registry import LOCAL_VARS

def is_server_running():
    try:
        response = requests.get(f"{LOCAL_VARS['SERVER_URL']}/jobs")
        return response.status_code == 200
    except requests.exceptions.ConnectionError:
        return False

def start_server():
    if is_server_running():
        print("Scheduler server is already running.")
    else:
        print("Starting server...")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # If the scratch dir doesn't exist, create it
        if not os.path.exists(LOCAL_VARS["SCRATCH_DIR"]):
            os.makedirs(LOCAL_VARS["SCRATCH_DIR"])
        with open(f'{LOCAL_VARS["SCRATCH_DIR"]}/scheduler_{timestamp}.log', 'a') as log:
            subprocess.Popen(
                [sys.executable, 'manager.py'],
                stdout=log,
                stderr=log,
                preexec_fn=os.setsid,  # For Unix
            )
        for _ in range(10):
            if is_server_running():
                print("Scheduler server started.")
                return
            time.sleep(1)
        print("Failed to start scheduler server. Check logs for details.")
    sys.exit(1)

def main():
    start_server()

if __name__ == '__main__':
    main()
