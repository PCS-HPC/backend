from pathlib import Path
from fastapi import UploadFile, HTTPException, status
import os
import pwd
import stat

EXECUTABLE_EXTENSIONS = {".out", ".x", ".bin", ""}  # "" = no extension, like your pi_reduce

raw_storage_root = os.getenv("LOCAL_STORAGE_DIR", "storage")
STORAGE_ROOT = Path(os.path.expandvars(os.path.expanduser(raw_storage_root))).resolve()

def clean_relative_path(raw_path: Optional[str]) -> Path:
    """
    Allows nested paths like:
    - assignment
    - assignment/notes.txt
    - assignment/images/diagram.png

    Blocks dangerous paths like:
    - ../secret.txt
    - C:/Windows/system32
    - /absolute/path
    """
    if not raw_path:
        return Path()

    normalized = raw_path.strip().replace("\\", "/")

    if normalized in {"", "."}:
        return Path()

    path = Path(normalized)

    if path.is_absolute():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Absolute paths are not allowed",
        )

    parts = []

    for part in normalized.split("/"):
        part = part.strip()

        if part in {"", "."}:
            continue

        if part == "..":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Path traversal is not allowed",
            )

        if any(char in part for char in '<>:"|?*'):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid path segment: {part}",
            )

        parts.append(part)

    return Path(*parts)

def get_safe_path(user_dir: Path, raw_path: Optional[str]) -> Path:
    relative_path = clean_relative_path(raw_path)
    target_path = (user_dir / relative_path).resolve()

    if user_dir != target_path and user_dir not in target_path.parents:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid path",
        )

    return target_path

def get_user_storage_dir(username: str) -> Path:
    user_dir = STORAGE_ROOT / username
    user_dir.mkdir(parents=True, exist_ok=True) # this shouldnt get called, like at all, openLDAP handles this
    return user_dir.resolve()

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
        set_ownership(destination, username)

        # Set executable bit for binary files
        # temp fix: proper fix later
        if destination.suffix in EXECUTABLE_EXTENSIONS:
            current = destination.stat().st_mode
            destination.chmod(current | stat.S_IXUSR | stat.S_IXGRP)

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
 
def set_ownership(target_path: Path, username: str):
    """Changes ownership of a single file or folder to the given OS username."""
    try:
        user_info = pwd.getpwnam(username)
        os.chown(target_path, user_info.pw_uid, user_info.pw_gid)
    except KeyError:
        print(f"Well that shouldnt happen, {username} doesn't exist, check with LDAP")
    except OSError as e:
        print(f"Failed to change ownership for {target_path}: {e}")