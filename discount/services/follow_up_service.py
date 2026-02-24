"""
AI-powered follow-up message generation for Smart Follow-up Node.
Uses conversation history to generate a short, friendly re-engagement (15–20 words).
"""
import logging

from discount.models import Message
from discount.whatssapAPI.process_messages import get_conversation_history

logger = logging.getLogger(__name__)

FOLLOW_UP_SYSTEM_PROMPT = (
    "You are the same AI sales persona the customer was talking to. "
    "The customer stopped responding. Send a single short, friendly, non-pushy follow-up message (15–20 words). "
    "If they were asking about price, offer a small nudge. If they were stuck on shipping, ask if they need help. "
    "Use the same dialect (Darija/Arabic or the language they used) as in the conversation. "
    "Reply with ONLY the follow-up message, no quotes or extra text."
)


def generate_follow_up_text(channel, customer_phone, limit=10):
    """
    Generate a short personalized follow-up message using GPT and the last
    `limit` messages of the conversation.

    Returns:
        str: Follow-up text (15–20 words), or empty string on failure.
    """
    try:
        conversation = get_conversation_history(customer_phone, channel, limit=limit)
        if not conversation:
            return ""
        from ai_assistant.services import generate_reply
        result = generate_reply(
            conversation,
            custom_instruction=FOLLOW_UP_SYSTEM_PROMPT,
        )
        reply = (result.get("reply") or "").strip()
        if reply:
            # Trim to reasonable length (e.g. 200 chars)
            return reply[:300].strip()
        return ""
    except Exception as e:
        logger.exception("generate_follow_up_text: %s", e)
        return ""
