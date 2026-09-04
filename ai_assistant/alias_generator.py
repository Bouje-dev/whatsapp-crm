"""
AI product-alias generator — inexpensive LLM (gpt-4o-mini) for synonyms / Darija variants.
"""
from __future__ import annotations

import json
import logging
import re

import requests
from django.conf import settings

from ai_assistant.services import OPENAI_API_URL, get_api_key
from discount.services.product_search import parse_aliases

logger = logging.getLogger(__name__)

ALIAS_SYSTEM_PROMPT = (
    "Generate 5 common alternative names, synonyms, or Moroccan Darija variations "
    "for this product. Return ONLY a JSON array of strings."
)
MIN_DESCRIPTION_WORDS = 6  # "more than 5 words"


def description_has_enough_words(description: str) -> bool:
    words = [w for w in re.split(r"\s+", (description or "").strip()) if w]
    return len(words) >= MIN_DESCRIPTION_WORDS


def generate_aliases(title: str, description: str) -> list[str]:
    """
    Call gpt-4o-mini to produce up to 5 alternative product names.
    Returns an empty list when the description is too short or the LLM fails.
    """
    if not description_has_enough_words(description):
        return []

    api_key = get_api_key()
    if not api_key:
        logger.warning("generate_aliases: OPENAI_API_KEY is not set")
        return []

    title = (title or "").strip() or "Product"
    description = (description or "").strip()
    payload = {
        "model": getattr(settings, "OPENAI_ALIAS_GENERATOR_MODEL", None) or "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": ALIAS_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Title: {title}\nDescription: {description}",
            },
        ],
        "max_tokens": 200,
        "temperature": 0.4,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    try:
        response = requests.post(OPENAI_API_URL, headers=headers, json=payload, timeout=20)
        if response.status_code != 200:
            logger.warning(
                "generate_aliases: API status %s, body %s",
                response.status_code,
                (response.text or "")[:200],
            )
            return []
        content = (
            ((response.json().get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        ).strip()
        if not content:
            return []
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```\s*$", "", content).strip()
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            parsed = parsed.get("aliases") or parsed.get("names") or []
        if not isinstance(parsed, list):
            return []
        aliases = parse_aliases(parsed)
        title_key = title.lower()
        aliases = [a for a in aliases if a.lower() != title_key]
        return aliases[:5]
    except (json.JSONDecodeError, requests.RequestException, KeyError, IndexError, TypeError, ValueError) as exc:
        logger.warning("generate_aliases: %s", exc)
        return []
