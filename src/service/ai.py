# wow derek, your ai has so much functionalities!
# ok not really i think im overcomplicating things
import requests
import os
import uuid
from datetime import datetime
from typing import Literal
import httpx

AI_CLUSTER_URL = os.getenv('AI_CLUSTER_URL')

def get_max_token():
    # Derek Feedback:
    # For Gemma 4 we got 128k token context length. whenever user's previous prompt's convo bloats up to 90k tokens 
    # (check using my tokenizer API), you just call summarise and it will reduce down to around 64k token context 
    # length and put in
    return 90000

async def estimate_token(total_context):
    """
    Count tokens in a conversation block using the Gemma 4 vLLM tokenizer.

    Args:
        total_context (str): The <previous_prompts_and_response>...</previous_prompts_and_response> block.

    Returns:
        int: Token count for the conversation block.

    Raises:
        requests.HTTPError: On non-2xx responses.
    """
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{AI_CLUSTER_URL}/api/v1/context/token-count",
            json={"conversation_block": total_context},
            timeout=30,
        )
        response.raise_for_status()
        return response.json()["token_count"]

def get_conversation_history(convo_id, db, after_id=None):
    query = {"conversation_id": convo_id}
    if after_id:
        # only fetch dialogues after the summarization cutoff
        # i sure do hope _id is monotonically increasing 
        query["_id"] = {"$gt": after_id}  

    dialogues = list(
        db.dialogues.find(query).sort("timestamp", 1)
    )

    return dialogues

def save_convo(
    db,
    content: str,
    sent_by: Literal["user", "ai"],  # "user" or "ai"
    user_id: str,
    conversation_id: str = None,
    title: str = None,
    files: list[dict] | None = None,
) -> None:
    if conversation_id is None:
        conversation_id = str(uuid.uuid4())
        db.conversations.insert_one({"_id": conversation_id, "title": title, "owner": user_id})

    db.dialogues.insert_one(
        {
            "conversation_id": conversation_id,
            "content": content,
            "sent_by": sent_by,
            "timestamp": datetime.utcnow(),
            "files": files or [],
        }
    )

    return conversation_id

def build_prompt(summary, context, new_message, files: list[dict] | None = None):
    history_block = ""
    history_lines = [f"summarised={summary}\n"] if summary and len(summary) else []

    for dialogue in context:
        if dialogue['sent_by'] == 'user':
            content = dialogue['content']
            if dialogue.get('files'):
                file_refs = "\n".join(f'{f["name"]}: {f["path"]}' for f in dialogue['files'])
                content = f"{content}\n\nFiles added can be located in:\n{file_refs}"
            history_lines.append(f"prompt={content}")
        elif dialogue['sent_by'] == 'ai':
            history_lines.append(f"response={dialogue['content']}")

    history_block = (
        "<previous_prompts_and_response>\n"
        + "\n".join(history_lines)
        + "\n</previous_prompts_and_response>\n\n"
    )

    if files:
        file_refs = "\n".join(f'{f["name"]}: {f["path"]}' for f in files)
        new_message = f"{new_message}\n\nFiles added can be located in:\n{file_refs}"

    return (
        f"{history_block}"
        f"<current_prompt>\n{new_message}\n</current_prompt>"
    )

async def get_chat_completion(
    context, 
    new_message, 
    user_id, 
    user_name,
    user_role,
    db = None,
    conversation_id: str = None,
    title: str = None,
    summary: str = "",
    files: list[dict] | None = None,  # <-- add this
):
    """
        Sends a new message to the NemoClaw LangGraph API, incorporating prior
        context using structured XML-style tags.

        Args:
            context:     List of prior turns, each a dict with keys:
                        - "prompt"   (str) the user's message
                        - "response" (str) the assistant's final_response
                        - "requires_clarification" (bool, optional)
            new_message: The new user prompt to send.
            user_id: username of submitter
            user_role: "user" or "admin" (default: "user").

        Returns:
            The full JSON response dict from the API:
            {
                "is_safe":                bool,
                "requires_clarification": bool,
                "final_response":         str,
                "execution_data":         dict | None,
                "safety_hazard":          str | None,
            }

        Raises:
            requests.HTTPError: On non-2xx responses.
            RuntimeError:       If the prompt is flagged as unsafe.
    """
    prompt = build_prompt(summary, context, new_message, files=files)

    payload = {
        "user_id": user_name,
        "user_role": user_role,
        "prompt": prompt,
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{AI_CLUSTER_URL}/api/v1/chat", json=payload, timeout=180
        )
        response.raise_for_status()

    result = response.json()

    if not result.get("is_safe"):
        return result, conversation_id

    if db is not None:
        conversation_id = save_convo(
            db, content=new_message, sent_by="user", user_id=user_id,
            conversation_id=conversation_id, title=title, files=files
        )

        save_convo(
            db, content=result.get("final_response", ""), sent_by="ai", user_id=user_id,
            conversation_id=conversation_id, title=title,
        )

    return result, conversation_id

async def summarize_context(previous_summary: str, context: list[dict]):
    """
    Condenses a conversation context list into a single summarized prompt
    string, suitable for injecting into a fresh request when the context
    window grows too large.

    Uses the NemoClaw API itself (Hermes/Gemma 4 via the Summarizer node)
    to produce the summary by asking it to compress the history.

    Args:
        context: List of prior turns with "prompt" and "response" keys.

    Returns:
        A plain-text summary of the conversation so far.
    """
    if not context:
        return previous_summary, None

    transcript = build_prompt(previous_summary, context, "")

    async with httpx.AsyncClient() as client:
        response = requests.post(
            f"{AI_CLUSTER_URL}/api/v1/context/summarize",
            json={"conversation_block": transcript},
            timeout=60,
        )
        response.raise_for_status()

    # cutoff marker — everything up to here is now summarized
    last_id = context[-1]["_id"]  
    return response.json()["conversation_block"], last_id
