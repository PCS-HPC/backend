from fastapi import APIRouter
from src.api.endpoints import users

router = APIRouter()
router.include_router(users.router, prefix="/users", tags=["users"])