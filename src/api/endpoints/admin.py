from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from src.api.endpoints.auth import get_current_user


router = APIRouter()


class CreditUpdateRequest(BaseModel):
    operation: Literal["set", "add", "deduct"]
    amount: float = Field(..., ge=0)
    reason: str | None = None


def require_admin(current_user: dict):
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin users can perform this action",
        )

    return current_user


def require_credit_balance(user: dict) -> float:
    if "creditBalance" not in user:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"User {user.get('username', 'unknown')} is missing credit balance",
        )

    return float(user["creditBalance"])


@router.get("/users")
def list_users(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    require_admin(current_user)

    users = []

    for user in request.app.db["users"].find(
        {
            "role": {
                "$in": ["user", "staff"],
            },
        },
        {
            "passwordHash": 0,
        },
    ):
        users.append({
            "id": str(user["_id"]),
            "email": user["email"],
            "username": user["username"],
            "role": user.get("role", "user"),
            "status": user.get("status", "active"),
            "creditBalance": require_credit_balance(user),
        })

    return {
        "success": True,
        "users": users,
    }


@router.patch("/users/{username}/credits")
def update_user_credits(
    username: str,
    payload: CreditUpdateRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    require_admin(current_user)

    clean_username = username.strip().lower()

    target_user = request.app.db["users"].find_one({
        "username": clean_username,
    })

    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    if target_user.get("role") not in ["user", "staff"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only student or staff credit balances can be changed",
        )

    old_balance = require_credit_balance(target_user)

    if payload.operation == "set":
        new_balance = payload.amount

    elif payload.operation == "add":
        new_balance = old_balance + payload.amount

    elif payload.operation == "deduct":
        new_balance = old_balance - payload.amount

        if new_balance < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Credit balance cannot be negative",
            )

    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid credit operation",
        )

    request.app.db["users"].update_one(
        {
            "_id": target_user["_id"],
        },
        {
            "$set": {
                "creditBalance": new_balance,
            }
        },
    )

    request.app.db["credit_transactions"].insert_one({
        "targetUserId": target_user["_id"],
        "targetUsername": target_user["username"],
        "adminUserId": current_user["_id"],
        "adminUsername": current_user.get("username"),
        "operation": payload.operation,
        "amount": payload.amount,
        "oldCreditBalance": old_balance,
        "newCreditBalance": new_balance,
        "reason": payload.reason,
    })

    return {
        "success": True,
        "username": target_user["username"],
        "operation": payload.operation,
        "amount": payload.amount,
        "oldCreditBalance": old_balance,
        "newCreditBalance": new_balance,
    }