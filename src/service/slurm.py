# mm yummy slurm
import subprocess
from datetime import datetime, timedelta
from typing import Optional
import json
from zoneinfo import ZoneInfo
 
TIMEZONE = ZoneInfo("Asia/Kuala_Lumpur")

# All fields we care about from sacct
SACCT_FIELDS = [
    "JobID",
    "JobName",
    "State",
    "Submit",
    "Start",
    "End",
    "Elapsed",       # runtime
    "AllocTRES",     # contains GPU count and memory, e.g. "cpu=8,mem=32G,gres/gpu=1"
    "ReqMem",        # requested memory as a simpler field
    "MaxRSS",    # peak memory actually used (available post-completion)
    "AllocCPUS",
    "ExitCode",
    "User",
    "NodeList",
]
 
FIELD_STR = ",".join(SACCT_FIELDS)
 
# Slurm state → dashboard label
STATE_MAP = {
    "RUNNING":    "Running",
    "PENDING":    "Pending",
    "COMPLETED":  "Completed",
    "FAILED":     "Failed",
    "CANCELLED":  "Cancelled",
    "CANCELLED+": "Cancelled",   # cancelled by a signal
    "TIMEOUT":    "Failed",
    "NODE_FAIL":  "Failed",
    "OUT_OF_MEMORY": "Failed",
}

def _parse_rss(rss_str: str) -> int:
    """Convert sacct memory string (e.g. '3220K', '1.5M') to KB."""
    if not rss_str or rss_str in ("", "--"):
        return 0
    rss_str = rss_str.strip()
    try:
        if rss_str.endswith("K"):
            return int(float(rss_str[:-1]))
        elif rss_str.endswith("M"):
            return int(float(rss_str[:-1]) * 1024)
        elif rss_str.endswith("G"):
            return int(float(rss_str[:-1]) * 1024 * 1024)
        return int(rss_str)
    except ValueError:
        return 0

def _format_rss(kb: int) -> str:
    """Format KB value into human readable string."""
    if kb >= 1024 * 1024:
        return f"{kb / (1024 * 1024):.1f}G"
    elif kb >= 1024:
        return f"{kb / 1024:.1f}M"
    return f"{kb}K"
 
def _run_sacct(extra_args: list[str]) -> list[dict]:
    """
    Run sacct with our standard flags + any extra args.
    Returns a list of dicts keyed by SACCT_FIELDS, with batch/extern
    steps already stripped out.
    """
    cmd = [
        "sacct",
        "--format",    FIELD_STR,
        "--parsable2",          # pipe-delimited, no trailing |
        "--noheader",
        "--units",     "G",
    ] + extra_args
 
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )
 
    if result.returncode != 0:
        raise RuntimeError(
            f"sacct failed (exit {result.returncode}): {result.stderr.strip()}"
        )
 
    rows = []
    step_rss: dict[str, int] = {}  # job_id → max MaxRSS across steps

    for line in result.stdout.strip().splitlines():
        if not line:
            continue
        parts = line.split("|")
        row = dict(zip(SACCT_FIELDS, parts))
        job_id = row.get("JobID", "")

        if "." in job_id:
            # it's a step — extract MaxRSS and track the max
            parent_id = job_id.split(".")[0]
            rss_str = row.get("MaxRSS", "")
            rss_kb = _parse_rss(rss_str)
            if rss_kb > step_rss.get(parent_id, 0):
                step_rss[parent_id] = rss_kb
            continue

        rows.append(row)

    # merge MaxRSS back into parent rows
    for row in rows:
        job_id = row["JobID"]
        kb = step_rss.get(job_id, 0)
        row["MaxRSS"] = _format_rss(kb) if kb > 0 else ""
 
    return rows
 
 
def _normalize_row(row: dict, db) -> dict:
    raw_state = row.get("State", "").upper().split(" ")[0]
    state = STATE_MAP.get(raw_state, raw_state.capitalize())
    tres = _parse_tres(row.get("AllocTRES", ""))

    job_id = row["JobID"]
    slurm_job = db["slurm_jobs"].find_one({"jobId": job_id}, {"amount": 1})
    credits = slurm_job["amount"] if slurm_job else None

    return {
        "job_id":           job_id,
        "job_name":         row["JobName"],
        "status":           state,
        "submitted":        _format_dt(row.get("Submit")),
        "start":            _format_dt(row.get("Start")),
        "end":              _format_dt(row.get("End")),
        "runtime":          row.get("Elapsed", ""),
        "credits":          credits,
        "exit_code":        row.get("ExitCode", ""),
        "user":             row.get("User", ""),
        "nodes":            row.get("NodeList", ""),
        "cpus":             int(row.get("AllocCPUS") or 0),
        "gpus":             tres["gpus"],
        "memory_requested": row.get("ReqMem") or "—",
        "memory_used":      row.get("MaxRSS") or "—",
    }
 
def _format_dt(raw: Optional[str]) -> Optional[str]:
    """Parse and reformat a Slurm datetime string. Returns None if unknown."""
    if not raw or raw in ("Unknown", "None", "N/A", ""):
        return None
    try:
        dt = datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S")
        dt = dt.replace(tzinfo=ZoneInfo("UTC")).astimezone(TIMEZONE)
        return dt.strftime("%-d %b, %I:%M %p")   # e.g. "15 May, 12:13 pm"
    except ValueError:
        return raw
 
def _parse_tres(alloc_tres: str) -> dict:
    """Parse AllocTRES string into individual fields."""
    result = {"gpus": 0, "memory": "—"}
    for item in alloc_tres.split(","):
        if item.startswith("gres/gpu="):
            result["gpus"] = int(item.split("=")[1] or 0)
        elif item.startswith("mem="):
            result["memory"] = item.split("=")[1]   # e.g. "32G"
    return result

def get_all_jobs(
    user=None, 
    days_back=7, 
    db=None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> list[dict]:
    if start_date:
        start = start_date
    else:
        start = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")

    args = ["--starttime", start, "--allusers"]
    
    if end_date:
        args += ["--endtime", end_date]
    if user:
        args = ["--starttime", start, "--user", user]
        if end_date:
            args += ["--endtime", end_date]

    rows = _run_sacct(args)
    return [_normalize_row(r, db) for r in rows]

 
def get_jobs_by_status(
    status: str,
    user: Optional[str] = None,
    days_back: int = 7,
    db=None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> list[dict]:
    """
    Return jobs filtered by dashboard status label:
    'Running' | 'Pending' | 'Completed' | 'Failed' | 'Cancelled'
 
    Filtering is done natively via sacct --state, not in Python.
    'Failed' expands to FAILED,TIMEOUT,NODE_FAIL,OUT_OF_MEMORY.
    'Cancelled' expands to CANCELLED (sacct matches partial strings like CANCELLED+).
    """
    # Dashboard label → sacct --state value(s)
    STATUS_TO_SLURM = {
        "running":   "RUNNING",
        "pending":   "PENDING",
        "completed": "COMPLETED",
        "failed":    "FAILED,TIMEOUT,NODE_FAIL,OUT_OF_MEMORY",
        "cancelled": "CANCELLED",
    }
 
    slurm_state = STATUS_TO_SLURM.get(status.lower())
    if not slurm_state:
        raise ValueError(
            f"Unknown status '{status}'. "
            f"Valid values: {list(STATUS_TO_SLURM.keys())}"
        )
 
    if start_date:
        start = start_date
    else:
        start = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
        
    if end_date:
        end = end_date
    else:
        end = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
 
    start = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    end = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    args = ["--state", slurm_state]

    if status.lower() not in ['running', 'pending'] or start_date:
        args += ["--starttime", start]
    if (status in ["completed", "failed", "cancelled"]) or end_date:
        args += ["--endtime", end]

    args += ["--user", user] if user else ["--allusers"]
 
    rows = _run_sacct(args)
    return [_normalize_row(r, db) for r in rows]
 
 
def get_job_by_id(job_id: str, db=None) -> Optional[dict]:
    """
    Return a single job by its Slurm JobID (e.g. 'JOB-1042' or '1042').
    Returns None if not found.
    """
    # Strip any 'JOB-' prefix your frontend adds
    numeric_id = job_id.replace("JOB-", "").replace("job-", "")
    rows = _run_sacct(["--jobs", numeric_id])
    if not rows:
        return None
    return _normalize_row(rows[0], db)
 
def get_job_stats(user: Optional[str] = None, days_back: int = 7) -> dict:
    """
    Return aggregate statistics for the dashboard summary panel.
    """
    jobs = get_all_jobs(user=user, days_back=days_back)
 
    by_status: dict[str, int] = {}
 
    for j in jobs:
        by_status[j["status"]] = by_status.get(j["status"], 0) + 1
 
    return {
        "total_jobs":    len(jobs),
        # total_credits: TODO: fetch from MongoDB and merge here
        "by_status":     by_status,
    }
 
def get_job_output_paths(job_id: str) -> dict:
    """
    Use --json specifically to get expanded stdout/stderr paths.
    
    See, if we use --parseable2 for output, we get this:
    sacct -j 182 --format=JobID,StdOut,StdErr,WorkDir --parsable2 --noheader
    182|/mnt/beegfs/test/hostname_%j.out||/mnt/beegfs/test
    182.batch|||
    182.0|||
    And we need to figure out and replace %j by ourself
    
    Now if we do 
    sacct --jobs=182 --json > 182.json
    jq --raw-output '.jobs[].stdout_expanded' < 182.json
    
    We get:
    /mnt/beegfs/test/hostname_182.out
    
    Which is SO much more better than whatever the fuck the above one is
    but --json returns EVERYTHING, even stuff that we dont really give a shit about
    """
    result = subprocess.run(
        ["sacct", f"--jobs={job_id}", "--json"],
        capture_output=True, text=True
    )
    data = json.loads(result.stdout)
    job = data["jobs"][0] if data.get("jobs") else None
    if not job:
        return {}
    return {
        "stdout": job.get("stdout_expanded"),
        "stderr": job.get("stderr_expanded"),
        "work_dir": job.get("working_directory"),
    }
