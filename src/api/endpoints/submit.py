from __future__ import annotations

import json
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field, ValidationError, field_validator

from ...service.slurm_submit import submit_job, generate_slurm_script
from ...service.file import batch_upload
from .auth import get_current_user

router = APIRouter()

class SubmitResponse(BaseModel):
    job_id: int
    message: str
    staged_files: list[str]

class SlurmJobParams(BaseModel):
    jobName: str = Field(..., description="Name of the job")
    nodes: int = Field(default=1, ge=1, description="Number of nodes")
    cpus: int = Field(default=1, ge=1, description="CPUs per task")
    gpus: int = Field(default=0, ge=0, description="GPUs per node")
    memory: str = Field(default="1G", pattern=r"^\d+[KMGT]$", description="e.g., 8G, 500M")
    walltime: str = Field(default="01:00:00", pattern=r"^\d{2}:\d{2}:\d{2}$", description="HH:MM:SS format")
    output: str | None = None
    error: str | None = None
    body: str = Field(..., min_length=1, description="The actual bash commands to run")

    @field_validator("memory", mode="before")
    @classmethod
    def sanitize_memory(cls, v: str) -> str:
        if not isinstance(v, str):
            v = str(v)
        v = v.strip().upper()
        if v.isdigit():
            return f"{v}G"
        return v

@router.post("/submit", response_model=SubmitResponse, status_code=201)
async def submit(
    request: Request,
    job_params: str = Form(..., description="JSON string of SlurmJobParams"),
    files: list[UploadFile] = File(default=[]),
    current_user: dict = Depends(get_current_user),
):
    """
    Accept job parameters and optional supporting files, build the script,
    submit via sbatch, and record the job in the database.
    """
    username = current_user["username"]
    db = request.app.db

    try:
        params = SlurmJobParams.model_validate_json(job_params)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=f"Invalid job parameters: {e.errors()}")

    # _validate_files(files)

    staged: list[dict] = []
    if files:
        staged = await batch_upload(files, username)

    # Safely generate the script now that inputs are validated
    script = generate_slurm_script(params)

    # Submit the generated script
    job_id = submit_job(script=script, username=username)

    _record_submission(db, job_id=job_id, username=username, script=script)

    return SubmitResponse(
        job_id=job_id,
        message=f"Submitted batch job {job_id}",
        staged_files=[f["relative_path"] for f in staged],
    )

def _record_submission(db, *, job_id: int, username: str, script: str) -> None:
    # TODO: mongodb
    pass