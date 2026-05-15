from ..api.endpoints.files import get_user_storage_dir, get_safe_path
from pathlib import Path
from fastapi import UploadFile, HTTPException, status
import os

async def batch_upload(files: list[UploadFile], username) -> list[dict]:
    user_dir = get_user_storage_dir(username)
    uploaded = []

    for file in files:
        filename = file.filename or ""
        if not filename.strip():
            continue

        safe_name = Path(filename).name
        destination = get_safe_path(user_dir, safe_name)

        with destination.open("wb") as buffer:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                buffer.write(chunk)

        await file.close()

        uploaded.append({
            "name": destination.name,
            "path": str(destination),
            "relative_path": destination.relative_to(user_dir).as_posix()
        })

    return uploaded

def _check_path(path: str | None) -> str:
    """Validate a file path exists and is readable. Returns the path or raises."""
    if not path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No file path recorded for this job")
    if not os.path.exists(path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"File not found: {path}")
    if not os.access(path, os.R_OK):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="File is not readable")
    return path
 
def _tail(path: str, lines: int) -> str:
    """Read the last N lines of a file"""
    with open(path, "r", errors="replace") as f:
        return "".join(f.readlines()[-lines:])
 