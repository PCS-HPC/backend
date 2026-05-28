from fastapi import UploadFile, APIRouter, Request, HTTPException, status, Depends, Form, File
from .auth import get_current_user
from ...service import ai, file

router = APIRouter()

@router.get("/convo")
async def get_convo_list(
    current_user: dict = Depends(get_current_user)
):
    # CRITICAL: Use username (LDAP), not database ObjectId string
    user_name = current_user["username"]
    return await ai.get_user_history_adapter(user_name)


@router.delete("/convo/{convo_id}")
async def delete_convo_list(
    convo_id: str,
    current_user: dict = Depends(get_current_user)
):
    user_name = current_user["username"]
    try:
        await ai.delete_session(user_name, convo_id)
        return {"message": "Success"}
    except Exception:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")


@router.post("/convo", status_code=status.HTTP_201_CREATED)
async def create_chat(
    message: str = Form(...),
    files: list[UploadFile] = File(default=[]),
    current_user: dict = Depends(get_current_user)
):
    user_name = current_user["username"]
    user_role = current_user["role"]

    uploaded_files = await file.batch_upload(files, user_name) if files else []

    # Fixed: Unpacked the return tuple, matched parameter 'user_id', added missing comma
    result, session_id = await ai.get_chat_completion(
        prompt=message,
        files=uploaded_files,
        user_id=user_name,
        user_role=user_role,
        session_id=None
    )

    # Maintain frontend compatibility by explicitly mapping session_id back to 'convo_id'
    return result | { "convo_id": session_id }


@router.get("/convo/{convo_id}", status_code=status.HTTP_200_OK)
async def get_chat(
    convo_id: str,
    current_user: dict = Depends(get_current_user)
):
    user_name = current_user["username"]
    try:
        return await ai.get_conversation_history_adapter(convo_id, user_name)
    except Exception:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")


@router.post("/convo/{convo_id}", status_code=status.HTTP_201_CREATED)
async def continue_conversation(
    convo_id: str, 
    message: str = Form(...),
    files: list[UploadFile] = File(default=[]),
    current_user: dict = Depends(get_current_user)
):
    user_name = current_user["username"]
    user_role = current_user["role"]

    uploaded_files = await file.batch_upload(files, user_name) if files else []

    # Fixed: Unpacked return tuple and matched parameter name 'user_id'
    result, _ = await ai.get_chat_completion(
        prompt=message,
        files=uploaded_files,
        user_id=user_name,
        user_role=user_role,
        session_id=convo_id
    )

    return result | { "convo_id": session_id }