# wow derek, your ai has so much functionalities!
# ok not really i think im overcomplicating things
import requests
import os
import uuid
import datetime

AI_CLUSTER_URL = os.getenv('AI_CLUSTER_URL')

def get_max_token():
    # TODO: pending derek API
    return requests.get()

def estimate_token(total_context):
    # TODO: pending derek API
    # in an ideal world, i literally just dump the context in and call it a day
    return requests.post(total_context)

def get_conversation_history(convo_id, db):
    dialogues = list(db.dialogues.find({"conversation_id": convo_id}).sort("timestamp", 1))
    context = []
    for i in range(0, len(dialogues) - 1, 2):
        user_turn = dialogues[i]
        ai_turn = dialogues[i + 1] if i + 1 < len(dialogues) else None
        context.append({
            "prompt": user_turn.get("content", ""),
            "response": ai_turn.get("content", "") if ai_turn else "",
        })
    return context

def save_convo(
    db,
    content: str,
    sent_by: str,  # "user" or "ai"
    user_id: str,
    conversation_id: str = None,
    title: str = None,
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
        }
    )

    return conversation_id

def build_prompt(summary, context, new_message):
    history_block = ""
    if context:
        history_lines = [f"summarised={summary}\n"] if summary and len(summary) else []
        for turn in context:
            history_lines.append(f"prompt={turn.get('prompt', '')}")
            history_lines.append(f"response={turn.get('response', '')}")
        history_block = (
            "<previous_prompts_and_response>\n"
            + "\n".join(history_lines)
            + "\n</previous_prompts_and_response>\n\n"
        )

    return (
        f"{history_block}"
        f"<current_prompt>\n{new_message}\n</current_prompt>"
    )


def get_chat_completion(
    context, 
    new_message, 
    user_id, 
    user_role = 'user',
    db = None,
    conversation_id: str = None,
    title: str = None,
    summary: str = "",
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
    prompt = build_prompt(summary, context, new_message)

    if db:
        conversation_id = save_convo(
            db, content=new_message, sent_by="user", user_id=user_id,
            conversation_id=conversation_id, title=title,
        )

    payload = {
        "user_id": user_id,
        "user_role": user_role,
        "prompt": prompt,
    }

    response = requests.post(AI_CLUSTER_URL, json=payload, timeout=60)
    response.raise_for_status()

    result = response.json()

    if not result.get("is_safe"):
        hazard = result.get("safety_hazard", "unknown")
        raise RuntimeError(
            f"Prompt blocked by Llama Guard. Safety category: {hazard}"
        )

    if db:
        save_convo(
            db, content=result.get("final_response", ""), sent_by="ai", user_id=user_id,
            conversation_id=conversation_id, title=title,
        )

    return result

def summarize_context(previous_summary: str, context: list[dict]):
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
        return previous_summary

    # Build a transcript of the recent turns
    transcript_lines = []
    for i, turn in enumerate(context, start=1):
        transcript_lines.append(f"[Turn {i}]")
        transcript_lines.append(f"User: {turn.get('prompt', '')}")
        transcript_lines.append(f"Assistant: {turn.get('response', '')}")

    transcript = "\n".join(transcript_lines)

    prior_summary_block = (
        f"Previous summary:\n{previous_summary}\n\n"
        if previous_summary else ""
    )

    summary_prompt = (
        "The following is a conversation history between a user and an HPC assistant. "
        "Please summarize it concisely in a few sentences, preserving the key facts "
        "(job IDs, file paths, errors, decisions made) so it can be used as context "
        "for future requests.\n\n"
        f"{prior_summary_block}"
        f"Recent turns:\n{transcript}"
    )

    # TODO: pending derek API
    response = requests.post("", summary_prompt)

    return response.get("final_response", "")

def get_max_token() -> int:
    # TODO: replace with Derek's API endpoint when available
    response = requests.get("")
    pass
