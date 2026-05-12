from fastapi import APIRouter, Request, HTTPException, status
from pydantic import BaseModel, EmailStr
from ldap3.core.exceptions import LDAPEntryAlreadyExistsResult, LDAPNoSuchObjectResult
from ...service import ldap
import os

LDAP_ACTIVATED = os.getenv("LDAP_ACTIVATED")

router = APIRouter()

class UserCreate(BaseModel):
    email: EmailStr
    password: str


def parse_monash_email(email: str) -> dict:
    clean_email = email.strip().lower()

    if clean_email.endswith("@student.monash.edu"):
        local_part = clean_email.split("@")[0]
        username = local_part[:8]

        if len(username) != 8:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Student Monash username must be 8 characters",
            )

        return {
            "email": clean_email,
            "username": username,
            "role": "student",
        }

    if clean_email.endswith("@monash.edu"):
        local_part = clean_email.split("@")[0]

        if not local_part:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid Monash staff email",
            )

        return {
            "email": clean_email,
            "username": local_part,
            "role": "staff",
        }

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Only Monash email addresses are allowed",
    )


@router.post("/", status_code=status.HTTP_201_CREATED)
def create_user(user: UserCreate, request: Request):
    db = request.app.db

    parsed_email = parse_monash_email(user.email)

    existing_user = db["users"].find_one({
        "email": parsed_email["email"]
    })

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already exists",
        )

    existing_username = db["users"].find_one({
        "username": parsed_email["username"]
    })

    if existing_username:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already exists",
        )

    hashed_password = request.app.ph.hash(user.password)

    new_user = {
        "email": parsed_email["email"],
        "username": parsed_email["username"],
        "passwordHash": hashed_password,
        "role": parsed_email["role"],
        "status": "active",
    }

    result = db["users"].insert_one(new_user)

    # create openldap user
    # this should run the background but eh too lazy :P
    payload = ldap.User(
        username=new_user['username'],
        password=user.password
    )

    if (LDAP_ACTIVATED):
        ldap.create_user_with_group(payload, request.app.ldap)

    return {
        "success": True,
        "id": str(result.inserted_id),
        "email": new_user["email"],
        "username": new_user["username"],
        "role": new_user["role"],
        "status": new_user["status"],
    }