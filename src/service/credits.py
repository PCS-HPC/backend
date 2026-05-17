from bson import ObjectId
from pymongo.database import Database
from pymongo.errors import PyMongoError
from fastapi import HTTPException, status


def _get_user_by_id(db: Database, user_id: str) -> dict:
    """Fetch a user document by their string ID, raising 404 if not found."""
    try:
        oid = ObjectId(user_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid user_id format",
        )

    user = db["users"].find_one({"_id": oid})

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    return user


def _require_credit_balance(user: dict) -> int:
    """Return the user's credit balance, raising 500 if the field is missing."""
    if "creditBalance" not in user:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"User {user.get('username', 'unknown')} is missing credit balance",
        )

    return int(user["creditBalance"])


def _record_transaction(
    db: Database,
    *,
    user: dict,
    operation: str,
    amount: float,
    old_balance: int,
    new_balance: int,
    job_id: str,
) -> None:
    """Insert an audit record into credit_transactions and slurm_jobs."""
    db["credit_transactions"].insert_one({
        "targetUserId":      user["_id"],
        "targetUsername":    user.get("username"),
        "operation":         operation,
        "amount":            amount,
        "oldCreditBalance":  old_balance,
        "newCreditBalance":  new_balance,
        "jobId":             job_id,
    })

    db["slurm_jobs"].insert_one({
        "jobId":     job_id,
        "userId":    user["_id"],
        "operation": operation,
        "amount":    amount,
    })


# ── Public service functions ──────────────────────────────────────────────────

def get_balance(db: Database, user_id: str) -> dict:
    """Return the current credit balance for a user."""
    user = _get_user_by_id(db, user_id)
    balance = _require_credit_balance(user)

    return {"balance": balance}


def charge_credits(db: Database, user_id: str, amount: float, job_id: str) -> dict:
    """
    Deduct `amount` credits from the user's balance.
    Raises 400 if the resulting balance would go negative.
    """
    if amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Charge amount must be greater than zero",
        )

    user = _get_user_by_id(db, user_id)
    old_balance = _require_credit_balance(user)
    new_balance = old_balance - int(amount)

    if new_balance < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Insufficient credit balance",
        )

    try:
        db["users"].update_one(
            {"_id": user["_id"]},
            {"$set": {"creditBalance": new_balance}},
        )
        _record_transaction(
            db,
            user=user,
            operation="charge",
            amount=amount,
            old_balance=old_balance,
            new_balance=new_balance,
            job_id=job_id,
        )
    except PyMongoError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error during charge: {exc}",
        )

    return {
        "user_id":  user_id,
        "job_id":   job_id,
        "amount":   amount,
        "balance":  new_balance,
    }


def refund_credits(db: Database, user_id: str, amount: float, job_id: str) -> dict:
    """
    Add `amount` credits back to the user's balance.
    """
    if amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Refund amount must be greater than zero",
        )

    user = _get_user_by_id(db, user_id)
    old_balance = _require_credit_balance(user)
    new_balance = old_balance + int(amount)

    try:
        db["users"].update_one(
            {"_id": user["_id"]},
            {"$set": {"creditBalance": new_balance}},
        )
        _record_transaction(
            db,
            user=user,
            operation="refund",
            amount=amount,
            old_balance=old_balance,
            new_balance=new_balance,
            job_id=job_id,
        )
    except PyMongoError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error during refund: {exc}",
        )

    return {
        "user_id":  user_id,
        "job_id":   job_id,
        "amount":   amount,
        "balance":  new_balance,
    }