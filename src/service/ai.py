import os
import httpx
import re
from typing import Literal, Optional, Dict, Any, Tuple, List

AI_CLUSTER_URL = os.getenv('AI_CLUSTER_URL', 'http://192.168.10.7:8005')

def sanitize_llm_response(text: str) -> str:
    """
    Cleans out structural tags and ensures that if an entry starts with 
    or consists only of stray end-tags, it gets filtered properly.
    """
    if not text:
        return ""

    # 1. First, wipe a complete well-formed block out of the text
    full_block_pattern = r"<\|\s*channel.*?channel\s*\|>"
    text = re.sub(full_block_pattern, "", text, flags=re.DOTALL)

    # 2. Handle the "orphaned end tag" scenario:
    # If the text has an isolated end tag, match it and drop everything after it
    # We also include a lookahead/check for a trailing '<' that often hangs around.
    end_tag_pattern = r"(?:<\s*)?channel\s*\|>.*$"
    text = re.sub(end_tag_pattern, "", text, flags=re.DOTALL)

    # 3. Clean up loose characters left over from broken tag fragments (like that lone '<')
    # If a message block starts with a stray '<' right before prose, snip it.
    text = text.strip()
    if text.startswith("<") and not text.endswith(">"):
        text = text[1:].strip()

    cleaned = text.strip()

    # 5. Drop the message entirely if it just says "thought" or is completely empty
    if cleaned.lower() == "thought" or not cleaned:
        return ""

    return cleaned

async def get_chat_completion(
    prompt: str, 
    files: list, 
    user_id: str, 
    user_role: Literal["user", "admin"] = "user",
    session_id: Optional[str] = None,
) -> Tuple[Dict[str, Any], Optional[str]]:
    """
    Sends the latest user prompt to the NemoClaw Prompt Router.
    """
    if files:
        file_refs = "\n".join(f'{f["name"]}: {f["path"]}' for f in files)
        prompt = f"{prompt}\n\nFiles added can be located in:\n{file_refs}"
    
    payload = {
        "user_id": user_id,
        "user_role": user_role,
        "prompt": prompt
    }
    
    if session_id:
        payload["session_id"] = session_id

    print('sending:', payload)
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{AI_CLUSTER_URL}/api/v1/chat", 
            json=payload, 
            timeout=420  
        )
        response.raise_for_status()
        result = response.json() 
        print(result)
    
    # DEFENSIVE SANITIZATION: Clean real-time responses before sending to frontend
    if "final_response" in result:
        result["final_response"] = sanitize_llm_response(result["final_response"])

    returned_session_id = result.get("session_id")
    return result, returned_session_id


async def get_user_history_adapter(user_name: str) -> List[Dict[str, Any]]:
    """
    Fetches history from the Prompt Router and transforms it into the old sidebar UI contract.
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{AI_CLUSTER_URL}/api/v1/history/{user_name}")
        response.raise_for_status()
        data = response.json()
        
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
    Fetches specific session messages and filters out phantom/empty thoughts blocks.
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{AI_CLUSTER_URL}/api/v1/history/{user_name}/{convo_id}")
        response.raise_for_status()
        data = response.json()

        messages = data.get("messages", [])
        
        dialogues = []
        for msg in messages:
            # 1. Clean out the raw leaked tokens from historical logs
            cleaned_content = sanitize_llm_response(msg.get("content", ""))
            
            # 2. FIX EMPTY BUBBLES: If the block is empty after scrubbing, 
            # skip it entirely so the UI doesn't render a phantom bubble
            if not cleaned_content:
                continue

            dialogues.append({
                "sent_by": "user" if msg["role"] == "user" else "ai",
                "content": cleaned_content,
                "timestamp": msg["timestamp"]
            })

        convo_title = dialogues[0]["content"][:60] + "..." if dialogues else "Conversation"

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