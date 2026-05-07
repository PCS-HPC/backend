import os
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from jwt.exceptions import InvalidTokenError
from argon2.exceptions import VerifyMismatchError, VerificationError
from bson import ObjectId
from fastapi import APIRouter, Request, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr


router = APIRouter()
security = HTTPBearer()


class UserLogin(BaseModel):
    email: EmailStr
    password: str


def utc_now():
    """
    MongoDB/PyMongo often returns datetime values without timezone info.
    This helper keeps all database datetime values UTC but timezone-naive,
    so comparisons like now - lastActivityAt will not crash.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def create_access_token(user: dict):
    secret_key = os.getenv("JWT_SECRET_KEY")
    algorithm = os.getenv("JWT_ALGORITHM", "HS256")
    expire_minutes = int(os.getenv("JWT_EXPIRE_MINUTES", "1440"))

    if not secret_key:
        raise RuntimeError("JWT_SECRET_KEY not found. Check your .env file.")

    jti = str(uuid.uuid4())

    # Keep JWT exp timezone-aware because PyJWT expects proper UTC expiry.
    jwt_expire_time = datetime.now(timezone.utc) + timedelta(minutes=expire_minutes)

    payload = {
        "sub": str(user["_id"]),
        "email": user["email"],
        "role": user.get("role", "student"),
        "jti": jti,
        "exp": jwt_expire_time
    }

    token = jwt.encode(payload, secret_key, algorithm=algorithm)

    # Store DB datetime as timezone-naive UTC to avoid comparison errors.
    token_expire_time_for_db = jwt_expire_time.replace(tzinfo=None)

    return token, jti, token_expire_time_for_db


def decode_token(token: str) -> dict:
    secret_key = os.getenv("JWT_SECRET_KEY")
    algorithm = os.getenv("JWT_ALGORITHM", "HS256")

    if not secret_key:
        raise RuntimeError("JWT_SECRET_KEY not found. Check your .env file.")

    try:
        return jwt.decode(token, secret_key, algorithms=[algorithm])
    except InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    token = credentials.credentials
    payload = decode_token(token)

    jti = payload.get("jti")
    user_id = payload.get("sub")

    if not jti or not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload"
        )

    blacklisted_token = request.app.db["blacklisted_tokens"].find_one({
        "jti": jti
    })

    if blacklisted_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been logged out"
        )

    idle_timeout_minutes = int(os.getenv("SESSION_IDLE_TIMEOUT_MINUTES", "30"))
    now = utc_now()

    session = request.app.db["sessions"].find_one({
        "jti": jti
    })

    if not session or session.get("revoked"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or logged out"
        )

    last_activity = session.get("lastActivityAt")

    if not last_activity:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session"
        )

    # Extra safety in case old session documents still contain timezone-aware dates.
    if last_activity.tzinfo is not None:
        last_activity = last_activity.astimezone(timezone.utc).replace(tzinfo=None)

    if now - last_activity > timedelta(minutes=idle_timeout_minutes):
        request.app.db["sessions"].update_one(
            {"jti": jti},
            {
                "$set": {
                    "revoked": True,
                    "revokedAt": now
                }
            }
        )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired due to inactivity"
        )

    request.app.db["sessions"].update_one(
        {"jti": jti},
        {
            "$set": {
                "lastActivityAt": now,
                "expiresAt": now + timedelta(minutes=idle_timeout_minutes)
            }
        }
    )

    try:
        object_user_id = ObjectId(user_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user ID in token"
        )

    user = request.app.db["users"].find_one({
        "_id": object_user_id
    })

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )

    if user.get("status") != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is not active"
        )

    return user


@router.post("/login")
def login_user(user_login: UserLogin, request: Request):
    db = request.app.db

    email = user_login.email.lower()

    user = db["users"].find_one({
        "email": email
    })

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    try:
        request.app.ph.verify(user["passwordHash"], user_login.password)
    except (VerifyMismatchError, VerificationError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    access_token, jti, token_expire_time = create_access_token(user)

    idle_timeout_minutes = int(os.getenv("SESSION_IDLE_TIMEOUT_MINUTES", "30"))
    now = utc_now()

    db["sessions"].insert_one({
        "jti": jti,
        "userId": user["_id"],
        "createdAt": now,
        "lastActivityAt": now,
        "expiresAt": now + timedelta(minutes=idle_timeout_minutes),
        "tokenExpiresAt": token_expire_time,
        "revoked": False
    })

    db["users"].update_one(
        {"_id": user["_id"]},
        {"$set": {"lastLoginAt": now}}
    )

    return {
        "success": True,
        "accessToken": access_token,
        "tokenType": "bearer",
        "expiresInMinutes": int(os.getenv("JWT_EXPIRE_MINUTES", "1440")),
        "idleTimeoutMinutes": idle_timeout_minutes,
        "user": {
            "id": str(user["_id"]),
            "email": user["email"],
            "role": user.get("role", "student"),
            "status": user.get("status", "active")
        }
    }


@router.post("/logout")
def logout_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    token = credentials.credentials
    payload = decode_token(token)

    jti = payload.get("jti")
    exp = payload.get("exp")

    if not jti or not exp:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload"
        )

    now = utc_now()

    request.app.db["blacklisted_tokens"].insert_one({
        "jti": jti,
        "blacklistedAt": now,
        "expiresAt": datetime.fromtimestamp(exp, tz=timezone.utc).replace(tzinfo=None)
    })

    request.app.db["sessions"].update_one(
        {"jti": jti},
        {
            "$set": {
                "revoked": True,
                "revokedAt": now
            }
        }
    )

    return {
        "success": True,
        "message": "Logged out successfully"
    }


@router.get("/me")
def get_me(current_user: dict = Depends(get_current_user)):
    return {
        "id": str(current_user["_id"]),
        "email": current_user["email"],
        "role": current_user.get("role", "student"),
        "status": current_user.get("status", "active")
    }