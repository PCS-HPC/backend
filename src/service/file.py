from ..api.endpoints.files import get_user_storage_dir, get_safe_path
from pathlib import Path
from fastapi import UploadFile

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
            "path": destination.relative_to(user_dir).as_posix(),
        })

    return uploaded