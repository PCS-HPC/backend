from fastapi import APIRouter
from src.api.endpoints import users, auth, files, ai

router = APIRouter()
router.include_router(users.router, prefix="/users", tags=["users"])
router.include_router(auth.router, prefix="/auth", tags=["auth"])
router.include_router(ai.router, prefix="/ai", tags=["ai"])
router.include_router(files.router, prefix="/files", tags=["files"])