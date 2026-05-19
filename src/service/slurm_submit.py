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