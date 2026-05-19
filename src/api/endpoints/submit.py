from __future__ import annotations

import json
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field, ValidationError, field_validator

from ...service.slurm_submit import submit_job, generate_slurm_script, calculate_job_cost
from ...service.file import batch_upload
from ...service.credits import _record_transaction
from .auth import get_current_user

router = APIRouter()

class SubmitResponse(BaseModel):
    job_id: int
    message: str
    staged_files: list[str]

class SlurmJobParams(BaseModel):
    jobName: str = Field(..., description="Name of the job")
    nodes: int = Field(default=1, ge=1, description="Number of nodes")
    ntasks: int = Field(default=1, ge=1)
    ntasksPerNode: int | None = Field(default=None, ge=1)
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

    # 2. Calculate job credit cost
    job_cost = calculate_job_cost(params)
    old_balance = current_user.get("creditBalance", 0)

    # 3. Guard clause for insufficient balance
    if old_balance < job_cost:
        raise HTTPException(
            status_code=400, 
            detail=f"Insufficient credits. Required: {job_cost:.2f}, Available: {old_balance:.2f}"
        )

    # 4. Deduct the credits from user account
    new_balance = old_balance - job_cost
    db["users"].update_one(
        {"_id": current_user["_id"]},
        {"$set": {"creditBalance": new_balance}}
    )

    staged: list[dict] = []
    if files:
        staged = await batch_upload(files, username)

    # Safely generate the script now that inputs are validated
    script = generate_slurm_script(params)

    # Submit the generated script
    job_id = submit_job(script=script, username=username)

    _record_transaction(
        db=db,
        adminUserId=None,
        adminName="SYSTEM",
        user=current_user,
        operation="deduct",
        amount=job_cost,
        old_balance=old_balance,
        new_balance=new_balance,
        job_id=str(job_id)
    )

    return SubmitResponse(
        job_id=job_id,
        message=f"Submitted batch job {job_id}",
        staged_files=[f["relative_path"] for f in staged],
    )
