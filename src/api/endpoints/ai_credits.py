from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

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
async def get_balance(body: BalanceRequest):
    # TODO: replace with MongoDB lookup
    return { "balance": 100000 }


@router.post("/charge")
async def charge_credits(body: ChargeRequest):
    # TODO: deduct from MongoDB balance
    return {
        "user_id": body.user_id,
        "job_id":  body.job_id,
        "amount":  body.amount,
        "balance": 100000,
    }


@router.post("/refund")
async def refund_credits(body: RefundRequest):
    # TODO: add back to MongoDB balance
    return {
        "user_id": body.user_id,
        "job_id":  body.job_id,
        "amount":  body.amount,
        "balance": 100000,
    }