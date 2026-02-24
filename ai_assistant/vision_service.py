"""
Vision service for incoming WhatsApp image messages.
Uses GPT-4o to analyze images (e.g. product screenshots, receipts) for the AI flow context.
"""
import base64
import logging
import tempfile
import os
import requests
from django.conf import settings

logger = logging.getLogger(__name__)

OPENAI_VISION_URL = "https://api.openai.com/v1/chat/completions"
VISION_MODEL = "gpt-4o"


def get_openai_api_key():
    import os
    return getattr(settings, "OPENAI_API_KEY", None) or os.environ.get("OPENAI_API_KEY", "")


def analyze_image(media_content, mime_type="image/jpeg"):
    """
    Analyze image bytes with GPT-4o Vision and return a short description
    suitable for conversation context (e.g. product screenshot, receipt).

    Args:
        media_content: bytes of the image.
        mime_type: MIME type (image/jpeg, image/png, etc.).

    Returns:
        Description string (e.g. "The customer sent a screenshot of..."), or None on failure.
    """
    if not media_content:
        return None
    api_key = get_openai_api_key()
    if not api_key:
        logger.warning("vision_service: OPENAI_API_KEY not set")
        return None

    b64 = base64.standard_b64encode(media_content).decode("ascii")
    content = [
        {
            "type": "text",
            "text": (
                "Describe this image in one or two short sentences for a customer support context. "
                "If it looks like a product, screenshot, or receipt, say what it is and what the customer might be asking about (e.g. price, order). "
                "Use English or the same language you detect in the image. Be concise."
            ),
        },
        {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64}"}},
    ]

    payload = {
        "model": VISION_MODEL,
        "messages": [{"role": "user", "content": content}],
        "max_tokens": 200,
        "temperature": 0.3,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    try:
        resp = requests.post(OPENAI_VISION_URL, json=payload, headers=headers, timeout=30)
        if resp.status_code != 200:
            logger.warning("Vision API error %s: %s", resp.status_code, resp.text[:300])
            return None
        data = resp.json()
        choice = data.get("choices", [{}])[0]
        text = (choice.get("message", {}).get("content") or "").strip()
        if not text:
            return None
        return f"The customer sent an image. {text}"
    except requests.exceptions.Timeout:
        logger.warning("Vision API timeout")
        return None
    except Exception as e:
        logger.exception("analyze_image: %s", e)
        return None
