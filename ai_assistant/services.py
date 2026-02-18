import logging
import requests
from django.conf import settings

logger = logging.getLogger(__name__)

OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = "gpt-4o-mini"


def get_api_key():
    """Retrieve the OpenAI API key from Django settings or environment."""
    import os
    return getattr(settings, "OPENAI_API_KEY", None) or os.environ.get("OPENAI_API_KEY", "")


def build_system_prompt(language_hint="auto"):
    """
    Build the system prompt that instructs the AI how to behave
    as a customer-service assistant.
    """
    return (
        "You are a professional customer-service assistant for a COD (Cash on Delivery) "
        "e-commerce business. Your job is to help agents craft the perfect reply to customers "
        "on WhatsApp.\n\n"
        "Rules:\n"
        "- Analyse the conversation history provided and generate ONE concise, professional reply.\n"
        "- Match the language the customer is using (Arabic, French, English, etc.).\n"
        "- Be polite, helpful, and solution-oriented.\n"
        "- If the customer is angry, de-escalate with empathy.\n"
        "- If the customer asks about order status, tracking, or delivery, acknowledge and offer help.\n"
        "- Keep the reply short (1-3 sentences max) unless more detail is clearly needed.\n"
        "- Do NOT include greetings like 'Dear customer' unless the conversation just started.\n"
        "- Do NOT add quotes, markdown, or formatting — return plain text only.\n"
        "- Return ONLY the suggested reply text, nothing else."
    )


def build_messages_payload(conversation_messages, custom_instruction=None):
    """
    Convert the conversation history into the OpenAI messages format.

    conversation_messages: list of dicts with keys:
        - role: 'customer' or 'agent'
        - body: message text
    """
    system_prompt = build_system_prompt()
    if custom_instruction:
        system_prompt += f"\n\nAdditional instruction from the agent: {custom_instruction}"

    messages = [{"role": "system", "content": system_prompt}]

    for msg in conversation_messages:
        if msg["role"] == "customer":
            messages.append({"role": "user", "content": msg["body"]})
        else:
            messages.append({"role": "assistant", "content": msg["body"]})

    if not conversation_messages or conversation_messages[-1]["role"] == "agent":
        messages.append({
            "role": "user",
            "content": "(The customer is waiting for a reply. Suggest what the agent should say next.)",
        })

    return messages


def generate_reply(conversation_messages, custom_instruction=None, model=None):
    """
    Call OpenAI API and return the suggested reply.

    Returns: dict with keys 'reply', 'prompt_tokens', 'completion_tokens', 'model'
    Raises: ValueError on configuration errors, RuntimeError on API errors.
    """
    api_key = get_api_key()
    if not api_key:
        raise ValueError(
            "OpenAI API key is not configured. "
            "Set OPENAI_API_KEY in your .env file."
        )

    model = model or DEFAULT_MODEL
    messages = build_messages_payload(conversation_messages, custom_instruction)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": 300,
        "temperature": 0.7,
    }

    try:
        response = requests.post(
            OPENAI_API_URL,
            headers=headers,
            json=payload,
            timeout=30,
        )
    except requests.exceptions.Timeout:
        raise RuntimeError("OpenAI API request timed out. Please try again.")
    except requests.exceptions.ConnectionError:
        raise RuntimeError("Could not connect to OpenAI API. Check your internet connection.")

    if response.status_code == 401:
        raise ValueError("Invalid OpenAI API key. Please check your OPENAI_API_KEY.")
    if response.status_code == 429:
        raise RuntimeError("OpenAI rate limit reached. Please wait a moment and try again.")
    if response.status_code != 200:
        logger.error("OpenAI API error %s: %s", response.status_code, response.text[:500])
        raise RuntimeError(f"OpenAI API returned status {response.status_code}.")

    data = response.json()
    choice = data.get("choices", [{}])[0]
    reply_text = choice.get("message", {}).get("content", "").strip()
    usage = data.get("usage", {})

    return {
        "reply": reply_text,
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "model": model,
    }
