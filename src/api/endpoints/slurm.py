from fastapi import APIRouter, Query, Depends, HTTPException
from fastapi.responses import FileResponse
from ...service import slurm, file
from src.api.endpoints.auth import get_current_user
import os

router = APIRouter()

PREVIEW_LINES = 200
@router.get("/jobs")
def list_jobs(
    request: Request,
    status: str | None = Query(None),
    current_user: dict = Depends(get_current_user),
    days:   int        = Query(7),
):
    user = current_user["username"]
    db = request.app.db
    if status:
        return slurm.get_jobs_by_status(status, user=user, days_back=days, db=db)
    return slurm.get_all_jobs(user=user, days_back=days, db=db)
 
@router.get("/jobs/{job_id}")
def job_detail(
    job_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    db = request.app.db
    job = slurm.get_job_by_id(job_id, db=db)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@router.get("/stats")
def stats(
    current_user: dict = Depends(get_current_user)
):
    user = current_user["username"]
    return slurm.get_job_stats(user=user)

@router.get("/jobs/{job_id}/output")
async def get_job_output(
    job_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Preview the last 200 lines of stdout."""
    job = slurm.get_job_output_paths(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
 
    path = file._check_path(job.get("stdout"))
    return {
        "job_id":    job_id,
        "path":      path,
        "content":   file._tail(path, PREVIEW_LINES),
        "truncated": True,
    }
 
@router.get("/jobs/{job_id}/error")
async def get_job_error(
    job_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Preview the last 200 lines of stderr."""
    job = slurm.get_job_output_paths(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
 
    path = file._check_path(job.get("stderr"))
    return {
        "job_id":    job_id,
        "path":      path,
        "content":   file._tail(path, PREVIEW_LINES),
        "truncated": True,
    }

@router.get("/jobs/{job_id}/output/download")
async def download_job_output(
    job_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Download the full stdout file."""
    job = slurm.get_job_output_paths(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
 
    path = file._check_path(job.get("stdout"))
    return FileResponse(
        path=path,
        filename=os.path.basename(path),
        media_type="application/octet-stream",
    )
 
@router.get("/jobs/{job_id}/error/download")
async def download_job_error(
    job_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Download the full stderr file."""
    job = slurm.get_job_output_paths(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
 
    path = file._check_path(job.get("stderr"))
    return FileResponse(
        path=path,
        filename=os.path.basename(path),
        media_type="application/octet-stream",
    )