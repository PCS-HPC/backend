from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from fastapi import HTTPException
from .file import get_user_storage_dir

SBATCH_ID_RE = re.compile(r"Submitted batch job (\d+)")
SBATCH_TIMEOUT_SECONDS = 60

def submit_job(*, script: str, username: str) -> int:
    # No more temp files, just pass the raw string and username
    work_dir = get_user_storage_dir(username)
    return _run_sbatch(script=script, username=username, work_dir=work_dir)

def _run_sbatch(script: str, username: str, work_dir: str) -> int:
    # Build the command to execute sbatch as the specified user
    command = ['sudo', '-u', username, 'sbatch']

    try:
        result = subprocess.run(
            command,
            input=script,
            cwd=work_dir,
            capture_output=True,
            text=True,
            timeout=SBATCH_TIMEOUT_SECONDS,
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=502,
            detail="Required binary ('sudo' or 'sbatch') not found.",
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=502, detail="sbatch timed out")

    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "sbatch failed"
        raise HTTPException(status_code=400, detail=detail)

    match = SBATCH_ID_RE.search(result.stdout)
    if not match:
        raise HTTPException(
            status_code=502,
            detail=f"Could not parse job ID from sbatch output: {result.stdout!r}",
        )

    return int(match.group(1))

def generate_slurm_script(params: SlurmJobParams) -> str:
    lines = ["#!/bin/bash"]
    lines.append(f"#SBATCH --get-user-env")
    lines.append(f"#SBATCH --job-name={params.jobName}")
    lines.append(f"#SBATCH --nodes={params.nodes}")
    lines.append(f"#SBATCH --ntasks={params.ntasks}")
    if params.ntasksPerNode:
        lines.append(f"#SBATCH --ntasks-per-node={params.ntasksPerNode}") 
    lines.append(f"#SBATCH --cpus-per-task={params.cpus}")

    if params.gpus > 0:
        lines.append(f"#SBATCH --gpus-per-node={params.gpus}")
        
    lines.append(f"#SBATCH --mem={params.memory}")
    lines.append(f"#SBATCH --time={params.walltime}")
    
    if params.output:
        lines.append(f"#SBATCH --output={params.output}")
    if params.error:
        lines.append(f"#SBATCH --error={params.error}")
        
    lines.append("") # Empty line before the main script body
    lines.append(params.body)
    
    return "\n".join(lines)

# credit calc
def parse_memory_to_gb(mem_str: str) -> float:
    """Convert Slurm memory strings (e.g., 500M, 16G, 1T) to gigabytes (GB)."""
    unit = mem_str[-1]
    value = float(mem_str[:-1])
    
    if unit == "K":
        return value / (1024 * 1024)
    elif unit == "M":
        return value / 1024
    elif unit == "G":
        return value
    elif unit == "T":
        return value * 1024
    return value

def parse_walltime_to_hours(walltime_str: str) -> float:
    """Convert HH:MM:SS walltime format to total hours as a float."""
    parts = walltime_str.split(":")
    hours = int(parts[0])
    minutes = int(parts[1])
    seconds = int(parts[2])
    return hours + (minutes / 60.0) + (seconds / 3600.0)

def calculate_job_cost(params: SlurmJobParams) -> float:
    """
    Calculate total credit cost based on requested resources and walltime.
    Rates: 1 GPU = 10 cr/hr, 1 CPU = 1 cr/hr, 1 GB RAM = 0.1 cr/hr
    """
    hours = parse_walltime_to_hours(params.walltime)

    # Slurm allocations logic
    total_gpus = params.nodes * params.gpus

    # Determine total tasks assigned across nodes
    if params.ntasksPerNode:
        total_tasks = params.nodes * params.ntasksPerNode
    else:
        total_tasks = params.ntasks
    total_cpus = total_tasks * params.cpus

    # Slurm memory (--mem) is typically allocated per node
    total_ram_gb = params.nodes * parse_memory_to_gb(params.memory)
    
    # Compute hourly rate and multiply by duration
    hourly_rate = (total_gpus * 10.0) + (total_cpus * 1.0) + (total_ram_gb * 0.1)
    total_cost = hourly_rate * hours
    
    return round(total_cost, 4)
