from fastapi import APIRouter
from src.api.endpoints import users, auth, files, ai, admin, ai_credits, slurm, submit, nodes

router = APIRouter()
router.include_router(users.router, prefix="/users", tags=["users"])
router.include_router(auth.router, prefix="/auth", tags=["auth"])
router.include_router(ai.router, prefix="/ai", tags=["ai"])
router.include_router(files.router, prefix="/files", tags=["files"])
router.include_router(admin.router, prefix="/admin", tags=["admin"])
router.include_router(ai_credits.router, prefix="/credits", tags=["credits"])
router.include_router(slurm.router, prefix="/slurm", tags=["slurm"])
router.include_router(submit.router, prefix="/jobs", tags=["submit"])
router.include_router(nodes.router, prefix="/nodes", tags=["nodes"])
