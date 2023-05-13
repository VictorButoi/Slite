import os
import time


def task(c_idx, cfg_group, exp_type, available_gpus):
    gpu_idx = c_idx % len(available_gpus)
    os.environ["CUDA_VISIBLE_DEVICES"] = str(available_gpus[gpu_idx])
    for cfg in cfg_group:
        try:
            exp = exp_type.from_config(cfg)
            exp.run()
        except Exception as e:
            print(e)
            time.sleep(10)
            continue


def chunk_cfs(cfg_list, num_gpus):
    chunk_size = len(cfg_list) // num_gpus
    overflow_jobs = len(cfg_list) % num_gpus
    job_counts = [cfg_list[chunk_size*i:(chunk_size*i+ + chunk_size)] for i in range(num_gpus)]
    if overflow_jobs > 0:
        for i in range(overflow_jobs):
            job_counts[i].append(cfg_list[-(i+1)])
    return job_counts