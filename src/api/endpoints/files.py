import os
import re
import shutil
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse

from src.api.endpoints.auth import get_current_user

router = APIRouter()

raw_storage_root = os.getenv("LOCAL_STORAGE_DIR", "storage")
STORAGE_ROOT = Path(os.path.expandvars(os.path.expanduser(raw_storage_root))).resolve()

def sanitize_username(username: str) -> str:
    clean_username = username.strip().lower()

    if not clean_username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username cannot be empty",
        )

    clean_username = re.sub(r"[^a-zA-Z0-9._-]", "_", clean_username)

    if clean_username in {".", ".."}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid username",
        )

    return clean_username


def get_storage_username(current_user: dict) -> str:
    username = current_user.get("username")

    if username:
        return sanitize_username(username)

    email = current_user.get("email", "").strip().lower()

    if email.endswith("@student.monash.edu"):
        return sanitize_username(email.split("@")[0][:8])

    if email.endswith("@monash.edu"):
        return sanitize_username(email.split("@")[0])

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="User does not have a valid Monash username",
    )


def get_user_storage_dir(username: str) -> Path:
    user_dir = STORAGE_ROOT / username
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir.resolve()


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


@router.get("/")
def list_directory(
    path: Optional[str] = Query(default=None, description="Folder path to list"),
    current_user: dict = Depends(get_current_user),
):
    username = get_storage_username(current_user)
    user_dir = get_user_storage_dir(username)
    target_dir = get_safe_path(user_dir, path)

    if not target_dir.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Folder not found",
        )

    if not target_dir.is_dir():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Path is not a folder",
        )

    items = []

    for item in sorted(target_dir.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
        if item.name.startswith("."):
            continue

        stat = item.stat()
        relative_path = item.relative_to(user_dir).as_posix()

        items.append({
            "name": item.name,
            "path": relative_path,
            "type": "folder" if item.is_dir() else "file",
            "sizeBytes": stat.st_size if item.is_file() else None,
            "modifiedAt": stat.st_mtime,
        })

    return {
        "success": True,
        "username": username,
        "currentPath": target_dir.relative_to(user_dir).as_posix()
        if target_dir != user_dir
        else "",
        "items": items,
    }


@router.post("/folders", status_code=status.HTTP_201_CREATED)
def create_folder(
    path: str = Query(..., description="Folder path to create"),
    current_user: dict = Depends(get_current_user),
):
    username = get_storage_username(current_user)
    user_dir = get_user_storage_dir(username)
    folder_path = get_safe_path(user_dir, path)

    if folder_path.exists() and not folder_path.is_dir():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A file already exists with this name",
        )

    folder_path.mkdir(parents=True, exist_ok=True)

    return {
        "success": True,
        "message": "Folder created successfully",
        "folder": {
            "name": folder_path.name,
            "path": folder_path.relative_to(user_dir).as_posix(),
        },
    }


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile = File(...),
    path: Optional[str] = Query(default=None, description="Folder path to upload into"),
    overwrite: bool = Query(default=False),
    current_user: dict = Depends(get_current_user),
):
    username = get_storage_username(current_user)
    user_dir = get_user_storage_dir(username)
    upload_dir = get_safe_path(user_dir, path)

    if upload_dir.exists() and not upload_dir.is_dir():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Upload path is not a folder",
        )

    upload_dir.mkdir(parents=True, exist_ok=True)

    filename = file.filename or ""

    if not filename.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid filename",
        )

    safe_name = Path(filename).name
    upload_relative_path = upload_dir.relative_to(user_dir).as_posix()

    destination_path = f"{upload_relative_path}/{safe_name}" if upload_relative_path != "." else safe_name
    destination = get_safe_path(user_dir, destination_path)

    if destination.exists() and not overwrite:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="File already exists",
        )

    try:
        with destination.open("wb") as buffer:
            while True:
                chunk = await file.read(1024 * 1024)

                if not chunk:
                    break

                buffer.write(chunk)

    finally:
        await file.close()

    return {
        "success": True,
        "message": "File uploaded successfully",
        "file": {
            "name": destination.name,
            "path": destination.relative_to(user_dir).as_posix(),
            "sizeBytes": destination.stat().st_size,
        },
    }


@router.get("/download")
def download_file(
    path: str = Query(..., description="File path to download"),
    current_user: dict = Depends(get_current_user),
):
    username = get_storage_username(current_user)
    user_dir = get_user_storage_dir(username)
    file_path = get_safe_path(user_dir, path)

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
        )

    return FileResponse(
        path=file_path,
        filename=file_path.name,
        media_type="application/octet-stream",
    )


@router.delete("/")
def delete_item(
    path: str = Query(..., description="File or folder path to delete"),
    recursive: bool = Query(default=False, description="Required to delete non-empty folders"),
    current_user: dict = Depends(get_current_user),
):
    username = get_storage_username(current_user)
    user_dir = get_user_storage_dir(username)
    target_path = get_safe_path(user_dir, path)

    if not target_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File or folder not found",
        )

    if target_path == user_dir:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete root user folder",
        )

    item_type = "folder" if target_path.is_dir() else "file"
    relative_path = target_path.relative_to(user_dir).as_posix()

    if target_path.is_file():
        target_path.unlink()

    elif target_path.is_dir():
        if any(target_path.iterdir()) and not recursive:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Folder is not empty. Set recursive=true to delete it.",
            )

        if recursive:
            shutil.rmtree(target_path)
        else:
            target_path.rmdir()

    return {
        "success": True,
        "message": f"{item_type.capitalize()} deleted successfully",
        "deleted": {
            "type": item_type,
            "path": relative_path,
        },
    }