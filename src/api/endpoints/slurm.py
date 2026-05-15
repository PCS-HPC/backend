from fastapi import FastAPI, Query, Depends
from ...service import slurm

app = FastAPI()
 
@app.get("/jobs")
def list_jobs(
    status: str | None = Query(None),
    current_user: dict = Depends(get_current_user),
    days:   int        = Query(7),
):
    user = current_user["username"]
    if status:
        return slurm.get_jobs_by_status(status, user=user, days_back=days)
    return slurm.get_all_jobs(user=user, days_back=days)
 
@app.get("/jobs/{job_id}")
def job_detail(
    job_id: str,
    current_user: dict = Depends(get_current_user)
):
    user = current_user["username"]
    job = slurm.get_job_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@app.get("/stats")
def stats(
    current_user: dict = Depends(get_current_user)
):
    user = current_user["username"]
    return slurm.get_job_stats(user=user)