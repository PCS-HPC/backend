from fastapi import APIRouter, Request
from pydantic import BaseModel
from ...services.credit_service import get_balance, charge_credits, refund_credits

router = APIRouter()

class BalanceRequest(BaseModel):
    user_id: str

class ChargeRequest(BaseModel):
    user_id: str
    amount: float
    job_id: str

class RefundRequest(BaseModel):
    user_id: str
    amount: float
    job_id: str

@router.post("/balance")
async def get_balance_endpoint(body: BalanceRequest, request: Request):
    return get_balance(request.app.db, body.user_id)


@router.post("/charge")
async def charge_credits_endpoint(body: ChargeRequest, request: Request):
    return charge_credits(request.app.db, body.user_id, body.amount, body.job_id)


@router.post("/refund")
async def refund_credits_endpoint(body: RefundRequest, request: Request):
    return refund_credits(request.app.db, body.user_id, body.amount, body.job_id)