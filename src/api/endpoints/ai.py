# derek's ai integration
from fastapi import UploadFile, APIRouter, Request, HTTPException, status, Depends, Form, File
from .auth import get_current_user
from ...service import ai, file
from pydantic import BaseModel
from bson import ObjectId
from fastapi.encoders import ENCODERS_BY_TYPE

ENCODERS_BY_TYPE[ObjectId] = str

class ChatMessage(BaseModel):
    message: str

router = APIRouter()

@router.get("/convo")
def get_convo_list(
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    user_id = current_user["_id"]
    list_o_convo = list(request.app.db.conversations.find({"owner": user_id}))
    return list_o_convo

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
async def create_chat(
    request: Request,
    message: str = Form(...),
    files: list[UploadFile] = File(default=[]),
    current_user: dict = Depends(get_current_user)
):
    db = request.app.db
    user_id = current_user["_id"]
    user_name = current_user["username"]
    user_role = current_user["role"]

    uploaded_files = await file.batch_upload(files, user_name) if files else []

    result, convo_id = await ai.get_chat_completion(
        context=[],
        new_message=message,
        user_id=user_id,
        user_name=user_name,
        user_role=user_role,
        db=db,
        conversation_id=None,
        title=message[:60] + ("..." if len(message) > 60 else ""),
        files=uploaded_files or None,
    )

    return result | { "convo_id": convo_id }

@router.get("/convo/{convo_id}", status_code=status.HTTP_200_OK)
def get_chat(
    convo_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    db = request.app.db

    convo = db.conversations.find_one({"_id": convo_id})
    if not convo or convo['owner'] != current_user['_id']:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    convo["_id"] = str(convo["_id"])
    convo.pop("owner")
    dialogues = ai.get_conversation_history(convo_id, db)
    return {"conversation": convo, "dialogues": dialogues}

@router.post("/convo/{convo_id}", status_code=status.HTTP_201_CREATED)
async def continue_conversation(
    convo_id: str, 
    request: Request, 
    message: str = Form(...),
    files: list[UploadFile] = File(default=[]),
    current_user: dict = Depends(get_current_user)
):
    db = request.app.db
    user_id = current_user["_id"]
    user_name = current_user["username"]
    user_role = current_user["role"]

    conversation = db.conversations.find_one({"_id": convo_id})
    if not conversation or conversation['owner'] != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    uploaded_files = await file.batch_upload(files, user_name) if files else []

    # Check token count and summarize if needed
    summary = conversation.get("summary", "")
    cutoff_id = conversation.get("summary_cutoff_id")  # only fetch messages after this

    # Rebuild context from dialogue history
    context = ai.get_conversation_history(convo_id, db, after_id=cutoff_id)

    max_tokens = ai.get_max_token()
    total_tokens = await ai.estimate_token(ai.build_prompt(summary, context, message))
    if max_tokens and total_tokens > max_tokens:
        summary, cutoff_id  = await ai.summarize_context(summary, context)
        db.conversations.update_one(
            {"_id": convo_id}, 
            {"$set": {"summary": summary, "summary_cutoff_id": cutoff_id}}
        )
        context = []

    result, _ = await ai.get_chat_completion(
        context=context,
        new_message=message,
        user_id=user_id,
        user_name=user_name,
        user_role=user_role,
        db=db,
        conversation_id=convo_id,
        summary=summary,
        files=uploaded_files
    )

    return result

@router.get("/convo/{convo_id}/context", status_code=status.HTTP_200_OK)
async def get_context_left(
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
    total_tokens = await ai.estimate_token(ai.build_prompt(summary, context, ""))

    return {
        "max_tokens": max_tokens,
        "total_tokens": total_tokens,
        "percentage": total_tokens / max_tokens
    }