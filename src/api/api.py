from fastapi import APIRouter
from src.api.endpoints import users, auth

router = APIRouter()
router.include_router(users.router, prefix="/users", tags=["users"])
router.include_router(auth.router, prefix="/auth", tags=["auth"])