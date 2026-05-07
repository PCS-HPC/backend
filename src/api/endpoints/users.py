from datetime import datetime, timezone

from fastapi import APIRouter, Request, HTTPException, status
from pydantic import BaseModel, EmailStr


router = APIRouter()


class UserCreate(BaseModel):
    email: EmailStr
    password: str


@router.post("/", status_code=status.HTTP_201_CREATED)
def create_user(user: UserCreate, request: Request):
    db = request.app.db

    email = user.email.lower()

    existing_user = db["users"].find_one({"email": email})

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already exists"
        )

    hashed_password = request.app.ph.hash(user.password)

    new_user = {
        "email": email,
        "passwordHash": hashed_password,
        "role": "student",
        "status": "active",
        "createdAt": datetime.now(timezone.utc),
        "lastLoginAt": None
    }

    result = db["users"].insert_one(new_user)

    return {
        "success": True,
        "id": str(result.inserted_id),
        "email": email,
        "role": "student",
        "status": "active"
    }