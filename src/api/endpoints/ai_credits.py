from fastapi import APIRouter, Request, Query, Header, HTTPException, Depends
from typing import Annotated
from ...service.credits import get_balance, charge_credits, refund_credits
import os

MCP_TOKEN = os.getenv("MCP_TOKEN")

router = APIRouter()

def verify_token(authorization: Annotated[str | None, Header()] = None):
    if not authorization or authorization != f"Bearer {MCP_TOKEN}":
        raise HTTPException(status_code=401, detail="Unauthorized")

@router.get("/balance")
async def get_balance_endpoint(
    request: Request,
    user_id: str = Query(...),
    _=Depends(verify_token),
):
    return get_balance(request.app.db, user_id)

@router.get("/charge")
async def charge_credits_endpoint(
    request: Request,
    user_id: str = Query(...),
    amount: float = Query(...),
    job_id: str = Query(...),
    _=Depends(verify_token),
):
    return charge_credits(request.app.db, user_id, amount, job_id)

@router.get("/refund")
async def refund_credits_endpoint(
    request: Request,
    user_id: str = Query(...),
    amount: float = Query(...),
    job_id: str = Query(...),
    _=Depends(verify_token),
):
    return refund_credits(request.app.db, user_id, amount, job_id)
