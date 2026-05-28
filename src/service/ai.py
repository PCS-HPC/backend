import os
import httpx
from typing import Literal, Optional, Dict, Any, Tuple, List # Fixed: Added List

# This should point to your Prompt Router node (e.g., http://192.168.10.7:8005)
AI_CLUSTER_URL = os.getenv('AI_CLUSTER_URL', 'http://192.168.10.7:8005')

async def get_chat_completion(
    prompt: str, 
    files: list, # Explicitly typing this
    user_id: str, # This must be the LDAP/SLURM username
    user_role: Literal["user", "admin"] = "user",
    session_id: Optional[str] = None,
) -> Tuple[Dict[str, Any], Optional[str]]:
    """
    Sends the latest user prompt to the NemoClaw Prompt Router.
    Handles session tracking dynamically via session_id.
    """

    # Fixed: Changed uploaded_files to files to match the parameter name
    if files:
        file_refs = "\n".join(f'{f["name"]}: {f["path"]}' for f in files)
        prompt = f"{prompt}\n\nFiles added can be located in:\n{file_refs}"
    
    payload = {
        "user_id": user_id,
        "user_role": user_role,
        "prompt": prompt,
        "session_id": session_id
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{AI_CLUSTER_URL}/api/v1/chat", 
            json=payload, 
            timeout=420  # Keeping your robust timeout for deep execution tasks
        )
        response.raise_for_status()
        result = response.json() # Fixed: Read JSON inside the context block safely
    
    # Extract the stable session_id returned by the router
    returned_session_id = result.get("session_id")

    return result, returned_session_id


async def get_user_history_adapter(user_name: str) -> List[Dict[str, Any]]:
    """
    Fetches history from the Prompt Router and transforms it into the old
    List[dict] shape that your sidebar UI currently loops over.
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{AI_CLUSTER_URL}/api/v1/history/{user_name}")
        response.raise_for_status()
        data = response.json()
        
        # Translate Hermes schemas back into old MongoDB UI structures
        old_format_list = []
        for session in data.get("sessions", []):
            old_format_list.append({
                "_id": session["session_id"],
                "title": session["title"] or session["preview"] or "Untitled Conversation",
                "owner": user_name
            })
        return old_format_list


async def get_conversation_history_adapter(convo_id: str, user_name: str) -> Dict[str, Any]:
    """
    Fetches specific session messages and formats them into the old
    {"conversation": ..., "dialogues": ...} contract.
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{AI_CLUSTER_URL}/api/v1/history/{user_name}/{convo_id}")
        response.raise_for_status()
        data = response.json()

        messages = data.get("messages", [])
        
        # Translate message keys: role -> sent_by ('assistant' -> 'ai')
        dialogues = []
        for msg in messages:
            dialogues.append({
                "sent_by": "user" if msg["role"] == "user" else "ai",
                "content": msg["content"],
                "timestamp": msg["timestamp"]
            })

        # Dynamically infer a title if none exists
        convo_title = messages[0]["content"][:60] + "..." if messages else "Conversation"

        return {
            "conversation": {
                "_id": convo_id,
                "title": convo_title
            },
            "dialogues": dialogues
        }


async def delete_session(user_name: str, session_id: str) -> Dict[str, Any]:
    """
    Triggers session deletion via the Prompt Router.
    """
    async with httpx.AsyncClient() as client:
        response = await client.delete(f"{AI_CLUSTER_URL}/api/v1/history/{user_name}/{session_id}")
        response.raise_for_status()
        return response.json()