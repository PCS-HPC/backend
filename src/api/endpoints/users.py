from fastapi import APIRouter, Query, Request, HTTPException, status
from pydantic import BaseModel
from datetime import datetime
from requests import Request
from argon2 import PasswordHasher

class UserCreate(BaseModel):
	email: str
	password: str

router = APIRouter()

@router.post('/', status_code=status.HTTP_201_CREATED)
def create_user(user: UserCreate, request: Request):
	
	hashed_password = request.app.ph.hash(user.password)


	return {
		success: True,
		id: id
	}
