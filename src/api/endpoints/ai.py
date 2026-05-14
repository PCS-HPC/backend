# derek's ai integration
from fastapi import APIRouter, Request, HTTPException, status, Depends
from auth import get_current_user
from ...service import ai
from pydantic import BaseModel

class ChatMessage(BaseModel):
    message: str

router = APIRouter()

@router.get("/convo")
def get_convo_list(
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    user_id = current_user["_id"]
    return request.db.conversations.find({"owner": user_id})

@router.delete("/convo/{convo_id}")
def delete_convo_list(
    convo_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    db = request.app.db

    conversation = db.conversations.find_one({"_id": convo_id})
    if not conversation or conversation['owner'] != current_user['_id']:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    db.conversations.delete_one({"_id": convo_id})
    db.dialogues.delete_many({"conversation_id": convo_id})
    return {"message": "Success"}


# new conversation
@router.post("/convo", status_code=status.HTTP_201_CREATED)
def create_chat(
    body: ChatMessage,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    db = request.app.db
    user_id = current_user["_id"]
    message = body.message

    result, convo_id = ai.get_chat_completion(
        context=[],
        new_message=message,
        user_id=user_id,
        db=db,
        conversation_id=None,
        title=message[:60] + ("..." if len(message) > 60 else "")
    )

    return {
        "response": result.get("final_response"),
        "blocked": not result.get("is_safe"),
        "requires_clarification": result.get("requires_clarification"),
        "convo_id": convo_id,
    }

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
    if not conversation or conversation['owner'] != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    # Check token count and summarize if needed
    summary = conversation.get("summary", "")
    cutoff_id = conversation.get("summary_cutoff_id")  # only fetch messages after this

    # Rebuild context from dialogue history
    context = ai.get_conversation_history(convo_id, db, after_id=cutoff_id)

    max_tokens = ai.get_max_token()
    total_tokens = ai.estimate_token(ai.build_prompt(summary, context, new_msg))
    if max_tokens and total_tokens > max_tokens:
        summary, cutoff_id  = ai.summarize_context(summary, context)
        db.conversations.update_one(
            {"_id": convo_id}, 
            {"$set": {"summary": summary, "summary_cutoff_id": cutoff_id}}
        )
        context = []

    result, _ = ai.get_chat_completion(
        context=context,
        new_message=new_msg,
        user_id=user_id,
        db=db,
        conversation_id=convo_id,
        summary=summary
    )

    return {
        "response": result.get("final_response"),
        "blocked": not result.get("is_safe"),
        "requires_clarification": result.get("requires_clarification"),
        "convo_id": convo_id,
    }

@router.get("/convo/{convo_id}/context", status_code=status.HTTP_200_OK)
def get_context_left(
    convo_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    db = request.app.db

    conversation = db.conversations.find_one({"_id": convo_id})
    if not conversation or conversation['owner'] != current_user['_id']:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    # Check token count
    summary = conversation.get("summary", "")
    cutoff_id = conversation.get("summary_cutoff_id")  # same cutoff as continue_conversation

    context = ai.get_conversation_history(convo_id, db, after_id=cutoff_id)
    max_tokens = ai.get_max_token()
    total_tokens = ai.estimate_token(ai.build_prompt(summary, context, ""))

    return {
        "max_tokens": max_tokens,
        "total_tokens": total_tokens,
        "percentage": total_tokens / max_tokens
    }