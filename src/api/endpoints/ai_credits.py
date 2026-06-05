import os
from typing import Annotated
from fastapi import APIRouter, Request, Query, Header, HTTPException, Depends
from pydantic import BaseModel
from ...service.credits import get_balance, charge_credits, refund_credits

MCP_TOKEN = os.getenv("MCP_TOKEN")

router = APIRouter()

class TransactionRequest(BaseModel):
    user_id: str
    amount: float
    job_id: str

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

@router.post("/charge")
async def charge_credits_endpoint(
    request: Request,
    body: TransactionRequest,
    _=Depends(verify_token),
):
    return charge_credits(request.app.db, body.user_id, body.amount, body.job_id)

@router.post("/refund")
async def refund_credits_endpoint(
    request: Request,
    body: TransactionRequest,
    _=Depends(verify_token),
):
    return refund_credits(request.app.db, body.user_id, body.amount, body.job_id)