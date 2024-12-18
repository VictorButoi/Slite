# SLITE = Slurm + Lite

`slite` is a lightweight Slurm alternative for GPU job-management on individual servers. It provides a simple interface for scheduling and managing GPU jobs on a single machine.

## Installation

```bash
git clone https://github.com/VictorButoi/Slite.git
cd Slite
pip install -e .
```

## Configuration

Configure your server settings in `registry.py`:

```python
LOCAL_VARS = {
    "SERVER_URL": 'http://localhost:5000',  # Server URL and port
    "SLITE_DIR": '/path/to/slite',         # Slite installation directory 
    "SCRATCH_DIR": '/path/to/scratch/slite' # Directory for logs and temp files
}
```

## Usage

Start the server:
```bash
slite -startup
```

Common commands:
```bash
slite -list all              # List all jobs
slite -list running          # List running jobs
slite -inspect <job_id>      # Get job details
slite -kill <job_id>        # Kill a job
slite -relaunch <job_id>    # Relaunch a finished job 
slite -flush all            # Clear all jobs
slite -shutdown             # Stop the server
```

Python API for job submission:
```python
from slite import submit_jobs

# Submit experiment jobs
submit_jobs(
    config_list=[config1, config2],  # List of configs
    exp_class=ExperimentClass,       # Your experiment class
)

# Submit function jobs
submit_jobs(
    config_list=[config1, config2],  # List of configs  
    job_func=my_function,           # Function to run
)
```
