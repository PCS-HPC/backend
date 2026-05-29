from fastapi import APIRouter, Query, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from ...service import slurm, file
from src.api.endpoints.auth import get_current_user
import os
from datetime import datetime, timedelta

router = APIRouter()

PREVIEW_LINES = 200
@router.get("/jobs")
def list_jobs(
    request: Request,
    status: str | None = Query(None),
    current_user: dict = Depends(get_current_user),
    days:   int        = Query(7),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None)
):
    user = current_user["username"]
    user_role = current_user["role"]

    if (user_role == "admin"):
        user = None

    # --- Slurm Inclusive End-Date Offset Handler ---
    adjusted_end_date = end_date
    if end_date:
        try:
            # Parse 'YYYY-MM-DD' text into datetime object
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
            # Increment by 1 day so jobs finishing *during* the day are caught
            inclusive_dt = end_dt + timedelta(days=1)
            # Re-serialize back to a string for the sacct query command layer
            adjusted_end_date = inclusive_dt.strftime("%Y-%m-%d")
        except ValueError:
            # Fallback to the original user input if the string format is unexpected
            pass

    db = request.app.db
    if status:
        return slurm.get_jobs_by_status(
            status, 
            user=user, 
            days_back=days, 
            db=db,
            start_date=start_date,
            end_date=adjusted_end_date # Shoved clean parameter value here
        )
        
    return slurm.get_all_jobs(
        user=user,
        days_back=days,
        db=db,
        start_date=start_date,
        end_date=adjusted_end_date # Shoved clean parameter value here
    )

@router.get("/jobs/{job_id}")
def job_detail(
    job_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    user = current_user["username"]
    user_role = current_user["role"]

    db = request.app.db
    job = slurm.get_job_by_id(job_id, db=db)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if user_role != "admin":
        if job.get("user") != user:
            raise HTTPException(status_code=404, detail="Job not found")
    return job

# dont think this is used
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