# derek's ai integration
from fastapi import APIRouter, Request, HTTPException, status, Depends
from auth import get_current_user
from ...service import ai
from pydantic import BaseModel

class ChatMessage(BaseModel):
    message: str

router = APIRouter()

# new conversation
@router.post("/convo", status_code=status.HTTP_201_CREATED)
def create_chat(
    body: ChatMessage,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    db = request.app.db
    user_id = current_user["_id"]

    result = ai.get_chat_completion(
        context=[],
        new_message=body.message,
        user_id=user_id,
        db=db,
        conversation_id=None,
        title="Generic Title", # Oops! No title
    )

    return {"response": result.get("final_response")}

@router.get("/convo/{convo_id}", status_code=status.HTTP_200_OK)
def get_chat(
    convo_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    db = request.app.db

    conversation = db.conversations.find_one({"_id": convo_id})
    if not conversation or conversation['owner'] != current_user['_id']:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    dialogues = ai.get_conversation_history(convo_id, db)

    return {"conversation": conversation, "dialogues": dialogues}

@router.post("/convo/{convo_id}", status_code=status.HTTP_201_CREATED)
def continue_conversation(
    convo_id: str, 
    body: ChatMessage,
    request: Request, 
    current_user: dict = Depends(get_current_user)
):
    db = request.app.db
    user_id = current_user["_id"]
    new_msg = body.message

    conversation = db.conversations.find_one({"_id": convo_id})
    if not conversation or conversation['owner'] != current_user['_id']:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    # Rebuild context from dialogue history
    context = ai.get_conversation_history(convo_id, db)

    # Check token count and summarize if needed
    summary = conversation.get("summary", "")
    max_tokens = ai.get_max_token()
    total_tokens = ai.estimate_token(ai.build_prompt(summary, context, new_msg))
    if max_tokens and total_tokens > max_tokens:
        new_summary = ai.summarize_context(summary, context)
        db.conversations.update_one({"_id": convo_id}, {"$set": {"summary": new_summary}})

    result = ai.get_chat_completion(
        context=context,
        new_message=new_msg,
        user_id=user_id,
        db=db,
        conversation_id=convo_id,
        summary=summary
    )

    return {"response": result.get("final_response")}

@router.get("/convo/{convo_id}/token", status_code=status.HTTP_200_OK)
def get_token_left(
    convo_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    db = request.app.db

    conversation = db.conversations.find_one({"_id": convo_id})
    if not conversation or conversation['owner'] != current_user['_id']:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    # Rebuild context from dialogue history
    context = ai.get_conversation_history(convo_id, db)

    # Check token count and summarize if needed
    summary = conversation.get("summary", "")
    max_tokens = ai.get_max_token()
    total_tokens = ai.estimate_token(ai.build_prompt(summary, context, ""))

    return {
        "max_tokens": max_tokens,
        "total_tokens": total_tokens,
        "percentage": total_tokens / max_tokens
    }