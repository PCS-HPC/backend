# derek's ai integration
from fastapi import APIRouter, Request, HTTPException, status, Depends
from auth import get_current_user
from ...service import ai

router = APIRouter()

# new conversation
@router.post("/convo", status_code=status.HTTP_201_CREATED)
def create_chat(request: Request, current_user: dict = Depends(get_current_user)):
    pass

@router.get("/convo/{convo_id}", status_code=status.HTTP_201_CREATED)
def get_chat(convo_id: str, current_user: dict = Depends(get_current_user)):
    pass

@router.post("/convo/{convo_id}", status_code=status.HTTP_201_CREATED)
def create_conversation(convo_id: str, current_user: dict = Depends(get_current_user)):
    pass
