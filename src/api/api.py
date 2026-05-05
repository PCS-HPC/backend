from fastapi import APIRouter
from api.endpoints import users

router = APIRouter()
router.include_router(users.router, prefix="/users")