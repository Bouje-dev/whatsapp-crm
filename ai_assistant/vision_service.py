"""
Vision service for incoming WhatsApp image messages.
Uses GPT-4o to analyze images (e.g. product screenshots, receipts) for the AI flow context.
"""
import base64
import json
import logging
import re
import tempfile
import os
import requests
from django.conf import settings

logger = logging.getLogger(__name__)

OPENAI_VISION_URL = "https://api.openai.com/v1/chat/completions"
VISION_MODEL = "gpt-4o"

# Classifier prompt for digital-order payment phase (strict receipt vs unrelated photo).
_PAYMENT_MEDIA_CLASSIFIER_PROMPT = (
    "You are a strict payment-receipt validator for a Moroccan e-commerce WhatsApp agent.\n"
    "Look at the image and classify it for checkout payment verification.\n\n"
    "PAYMENT_RECEIPT = bank transfer confirmation, mobile banking screenshot, payment app "
    "success screen, ATM/CIH/Attijari/BMCE/Banque Populaire receipt, virement proof, "
    "RIB transfer, amount in MAD/DH/€, transaction reference, PDF-style bank document photo, "
    "or any screen clearly showing money sent to a merchant account.\n\n"
    "UNRELATED = furniture, products for sale, people/faces, landscapes, memes, logos only, "
    "random objects, marketing photos, chat screenshots without payment proof, or any image "
    "that is NOT proof of a bank/payment transfer.\n\n"
    "Reply with ONLY valid JSON (no markdown):\n"
    '{"classification":"payment_receipt"|"unrelated","summary":"one sentence describing what you see"}'
)


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


def _parse_vision_classifier_json(raw: str) -> dict | None:
    """Extract classification JSON from model output."""
    if not raw:
        return None
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1)
    else:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def classify_payment_phase_media(media_content, mime_type="image/jpeg") -> dict | None:
    """
    Strict vision gate for the digital payment-wait phase.

    Returns:
        {
            "is_payment_receipt": bool,
            "classification": "payment_receipt" | "unrelated" | "uncertain",
            "summary": str,
            "context_line": str,  # injected into LLM conversation as customer message context
        }
        or None on API failure.
    """
    if not media_content:
        return None
    api_key = get_openai_api_key()
    if not api_key:
        logger.warning("vision_service: OPENAI_API_KEY not set (payment classifier)")
        return None

    b64 = base64.standard_b64encode(media_content).decode("ascii")
    content = [
        {"type": "text", "text": _PAYMENT_MEDIA_CLASSIFIER_PROMPT},
        {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64}"}},
    ]
    payload = {
        "model": VISION_MODEL,
        "messages": [{"role": "user", "content": content}],
        "max_tokens": 180,
        "temperature": 0.1,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    try:
        resp = requests.post(OPENAI_VISION_URL, json=payload, headers=headers, timeout=35)
        if resp.status_code != 200:
            logger.warning(
                "Payment vision classifier error %s: %s",
                resp.status_code,
                resp.text[:300],
            )
            return None
        data = resp.json()
        raw = (data.get("choices", [{}])[0].get("message", {}) or {}).get("content") or ""
        parsed = _parse_vision_classifier_json(raw)
        if not parsed:
            logger.warning("Payment vision classifier: unparseable response: %s", raw[:200])
            return None

        classification = (parsed.get("classification") or "").strip().lower()
        summary = (parsed.get("summary") or "").strip() or "Image received."
        if classification == "payment_receipt":
            is_receipt = True
            label = "payment_receipt"
        elif classification == "unrelated":
            is_receipt = False
            label = "unrelated"
        else:
            is_receipt = False
            label = "uncertain"

        if is_receipt:
            context_line = (
                "[SYSTEM VISION — PAYMENT PHASE]: The attached image was classified as a "
                f"likely payment/bank transfer proof. Visual summary: {summary}"
            )
        else:
            context_line = (
                "[SYSTEM VISION — PAYMENT PHASE]: The attached image was classified as NOT a "
                f"payment receipt (unrelated or unclear). Visual summary: {summary}. "
                "Do NOT treat this as proof of payment."
            )

        return {
            "is_payment_receipt": is_receipt,
            "classification": label,
            "summary": summary,
            "context_line": context_line,
        }
    except requests.exceptions.Timeout:
        logger.warning("Payment vision classifier timeout")
        return None
    except Exception as exc:
        logger.exception("classify_payment_phase_media: %s", exc)
        return None
