"""
OpenAI embedding helpers for hybrid product search.

Uses ``text-embedding-3-small`` (1536 dimensions). Failures are logged and
return None so callers can fall back to exact/alias matching.
"""
from __future__ import annotations

import logging

import requests
from django.conf import settings

from ai_assistant.services import get_api_key

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536
OPENAI_EMBEDDINGS_URL = "https://api.openai.com/v1/embeddings"


def product_embedding_text(product=None, *, title=None, description=None) -> str:
    """Build the canonical text that is embedded for a product (title + description)."""
    if product is not None:
        title = getattr(product, "name", None) if title is None else title
        description = getattr(product, "description", None) if description is None else description
    title = (title or "").strip()
    description = (description or "").strip()
    return f"{title}\n{description}".strip()


def embed_text(text: str):
    """
    Return a 1536-d embedding list for ``text``, or None on failure / empty input.
    """
    payload_text = (text or "").strip()
    if not payload_text:
        return None
    api_key = get_api_key()
    if not api_key:
        logger.warning("embed_text: OPENAI_API_KEY is not set")
        return None
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": getattr(settings, "OPENAI_EMBEDDING_MODEL", None) or EMBEDDING_MODEL,
        "input": payload_text[:8000],
        "dimensions": EMBEDDING_DIMENSIONS,
    }
    try:
        response = requests.post(OPENAI_EMBEDDINGS_URL, headers=headers, json=body, timeout=20)
        if response.status_code != 200:
            logger.warning(
                "embed_text: API status %s, body %s",
                response.status_code,
                (response.text or "")[:200],
            )
            return None
        data = response.json()
        vector = (data.get("data") or [{}])[0].get("embedding")
        if not isinstance(vector, list) or len(vector) != EMBEDDING_DIMENSIONS:
            logger.warning("embed_text: unexpected embedding payload")
            return None
        return vector
    except (requests.RequestException, ValueError, TypeError, IndexError, KeyError) as exc:
        logger.warning("embed_text: %s", exc)
        return None


def refresh_product_embedding(product_id: int) -> bool:
    """
    Recompute and persist the embedding for a product id.

    Uses QuerySet.update() so Django signals are not re-fired.
    """
    from discount.models import Products

    product = Products.objects.filter(pk=product_id).only("id", "name", "description").first()
    if not product:
        return False
    vector = embed_text(product_embedding_text(product))
    if vector is None:
        return False
    Products.objects.filter(pk=product_id).update(embedding=vector)
    return True
