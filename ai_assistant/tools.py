"""
AI sales-agent tool executors — session/product state sync and related helpers.

Keeps Django ``ChatSession.active_product`` aligned with what the LLM is selling
so system-prompt pricing rules match the negotiated product.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)

_PRODUCT_LOCK_MARKER = "🔴 PRODUCT ID LOCK"


def _resolve_product_for_store(owner, *, product_id=None, product_name=None, channel=None):
    """Resolve a catalog product by numeric ID or name (channel-scoped when possible)."""
    if channel is not None:
        from discount.services.product_scope import channel_catalog_queryset, get_channel_product

        if product_id is not None:
            row = get_channel_product(channel, product_id=product_id)
            if row:
                return row
        name = (product_name or "").strip()
        if not name:
            return None
        try:
            from discount.services.product_search import find_matching_product

            hybrid = find_matching_product(name, channel=channel)
            if hybrid:
                return hybrid
        except Exception as exc:
            logger.debug("_resolve_product_for_store hybrid search: %s", exc)
        qs = channel_catalog_queryset(channel)
        row = qs.filter(name__iexact=name).first()
        if row:
            return row
        tokens = [w for w in re.split(r"\s+", name.lower()) if len(w) >= 2]
        if not tokens:
            return None
        scored: list[tuple[int, Any]] = []
        for p in qs.order_by("name")[:200]:
            pname = (getattr(p, "name", None) or "").strip().lower()
            aliases = " ".join(getattr(p, "aliases", None) or []).strip().lower()
            score = sum(10 for t in tokens if t in pname or t in aliases)
            if score > 0:
                scored.append((score, p))
        if not scored:
            return None
        scored.sort(key=lambda x: -x[0])
        if len(scored) == 1 or scored[0][0] > scored[1][0]:
            return scored[0][1]
        return None

    logger.warning("_resolve_product_for_store refused unscoped owner-wide lookup")
    return None


def should_auto_sync_search_product(query: str, top_product, top_score: int) -> bool:
    """
    True when search results identify a single product confidently enough to
    auto-switch ``active_product`` (exact name match or unique strong hit).
    """
    if not top_product or top_score <= 0:
        return False
    q = (query or "").strip().lower()
    if not q:
        return False
    name = (getattr(top_product, "name", None) or "").strip().lower()
    if not name:
        return False
    if q == name:
        return True
    if name.startswith(q) or q in name.split():
        return top_score >= 10
    return top_score >= 15


def execute_switch_active_product(
    channel,
    sender,
    *,
    product_id=None,
    product_name=None,
    current_node=None,
) -> dict[str, Any]:
    """
    LLM tool: bind the WhatsApp chat session to a catalog product in the DB.

    Clears stale negotiation/pricing session keys via ``set_session_active_product``.
    """
    if not channel or not sender:
        return {"success": False, "message": "Channel or sender missing."}

    owner = getattr(channel, "owner", None)
    if not owner:
        return {"success": False, "message": "Store owner missing."}

    ai_cfg = getattr(current_node, "ai_model_config", None) or {} if current_node else {}
    locked_pid = ai_cfg.get("product_id") if isinstance(ai_cfg, dict) else None
    if locked_pid is not None:
        try:
            locked_pid = int(locked_pid)
        except (TypeError, ValueError):
            locked_pid = None

    product = _resolve_product_for_store(
        owner, product_id=product_id, product_name=product_name, channel=channel
    )
    if not product:
        return {
            "success": False,
            "message": (
                "Product not found. Call search_products first, then pass "
                "product_id from [DB_PRODUCT_ID: X] or an exact product_name."
            ),
        }

    from discount.whatssapAPI.session_state import set_session_active_product

    switched = set_session_active_product(
        channel, sender, product, reason="switch_active_product_tool"
    )

    currency = (getattr(product, "currency", None) or "MAD").strip() or "MAD"
    official = getattr(product, "price", None)
    backup = getattr(product, "backup_price", None)

    node_default_note = ""
    if locked_pid is not None and int(product.id) != int(locked_pid):
        node_default_note = (
            " Previous flow default product was overridden — customer pivot allowed. "
            "Use ONLY this product's pricing from now on."
        )

    return {
        "success": True,
        "switched": switched,
        "product_id": int(product.id),
        "product_name": (getattr(product, "name", None) or "").strip(),
        "official_price": str(official) if official is not None else None,
        "backup_price": str(backup) if backup is not None else None,
        "currency": currency,
        "message": (
            f"Session active product is now '{product.name}' (ID {product.id}). "
            "Checkout locks and old negotiated prices were cleared."
            f"{node_default_note} "
            "Pricing rules and submit_customer_order product_id MUST use this product."
        ),
    }


def strip_product_lock_instruction(custom_instruction: str) -> str:
    """Remove stale PRODUCT ID LOCK block before re-injecting refreshed product context."""
    text = custom_instruction or ""
    idx = text.find(_PRODUCT_LOCK_MARKER)
    if idx >= 0:
        return text[:idx].rstrip()
    return text


def build_product_lock_instruction(prod) -> str:
    """Current checkout target — not a permanent lock; pivots via switch_active_product."""
    if not prod:
        return ""
    pname = (prod.name or "").strip()
    return (
        f"\n\n{_PRODUCT_LOCK_MARKER} — CURRENT CHECKOUT TARGET (updates when customer pivots)\n"
        f"Active product RIGHT NOW: \"{pname}\"\n"
        f"Real database ID: {prod.id}\n"
        f"✅ Pass product_id={prod.id} when calling submit_customer_order for THIS product.\n"
        f"✅ If the customer asks for a DIFFERENT product, call switch_active_product or search_products "
        f"immediately — you are NEVER locked to \"{pname}\" forever and must NEVER refuse a switch.\n"
        f"⛔ NEVER use 1, 2, 3, or any sequential/guessed product_id.\n"
        f"The [DB_PRODUCT_ID: {prod.id}] token in the product context above is the authoritative source."
    )


def refresh_active_product_prompt_bindings(
    channel,
    sender,
    store,
    *,
    flow_notes: str = "",
) -> dict[str, Any]:
    """
    Re-read ``ChatSession.active_product`` and rebuild LLM prompt bindings.

    Call after tools that may change active product (switch_active_product,
    search_products, send_product_media) and before ``continue_after_tool_calls``.
    """
    out: dict[str, Any] = {
        "product_id": None,
        "product_context": None,
        "product_lock_instruction": "",
        "pronoun_anchor_product_name": None,
    }
    if not channel or not sender or not store:
        return out

    try:
        from discount.models import ChatSession
        from discount.product_sales_prompt import build_product_context_for_prompt
        from discount.services.product_scope import get_channel_product, product_belongs_to_channel

        session = (
            ChatSession.objects.filter(
                channel=channel,
                customer_phone=sender,
                is_expired=False,
            )
            .select_related("active_product")
            .first()
        )
        if not session or not getattr(session, "active_product_id", None):
            return out

        prod = getattr(session, "active_product", None)
        if prod is not None and not product_belongs_to_channel(prod, channel):
            prod = None
        if prod is None:
            prod = get_channel_product(channel, product_id=session.active_product_id)
        if not prod:
            return out

        ctx = build_product_context_for_prompt(prod)
        if flow_notes and (flow_notes or "").strip():
            ctx = ctx + "\n\n---\n\nAdditional notes from flow builder:\n" + flow_notes.strip()

        out["product_id"] = int(prod.id)
        out["product_context"] = ctx
        out["product_lock_instruction"] = build_product_lock_instruction(prod)
        out["pronoun_anchor_product_name"] = (prod.name or "").strip() or None
    except Exception as exc:
        logger.warning("refresh_active_product_prompt_bindings failed: %s", exc)

    return out


def format_switch_active_product_tool_result(result: dict[str, Any]) -> str:
    """JSON string returned to the LLM after switch_active_product."""
    return json.dumps(result, ensure_ascii=False)


_ANALYZE_URL_TIMEOUT_SEC = 3
_ANALYZE_URL_ERROR = {"status": "error", "message": "Page could not be loaded."}
_ANALYZE_URL_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; DisoundBot/1.0; +https://disound.app) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ar,en;q=0.9,fr;q=0.8",
}


def _analyze_url_error_payload() -> str:
    return json.dumps(_ANALYZE_URL_ERROR, ensure_ascii=False)


def execute_analyze_url(url: Optional[str] = None) -> str:
    """
    LLM tool: fetch a customer-shared URL and extract page title + meta description.

    Uses ``requests`` + BeautifulSoup with a strict timeout so the WhatsApp webhook
    does not hang. Returns a JSON string for the model.

    Success shape::
        {"status": "ok", "url": "...", "title": "...", "description": "..."}

    Failure shape (timeouts, 4xx/5xx, bad URL, parse errors)::
        {"status": "error", "message": "Page could not be loaded."}

    # ADVANCED FALLBACK (placeholder):
    # For JavaScript-heavy SPAs or bot-protected pages (403 / empty shell HTML),
    # replace or extend this path with a headless browser scraper such as
    # Selenium Undetected Chromedriver / Playwright stealth. Keep the same
    # timeout budget and return shape so the LLM contract stays unchanged.
    """
    raw = (url or "").strip()
    if not raw.startswith(("http://", "https://")):
        return _analyze_url_error_payload()

    try:
        import requests
        from bs4 import BeautifulSoup
    except ImportError as exc:
        logger.warning("execute_analyze_url missing dependency: %s", exc)
        return _analyze_url_error_payload()

    try:
        resp = requests.get(
            raw,
            timeout=_ANALYZE_URL_TIMEOUT_SEC,
            headers=_ANALYZE_URL_HEADERS,
            allow_redirects=True,
        )
        if resp.status_code >= 400:
            logger.info(
                "execute_analyze_url HTTP %s for url=%s",
                resp.status_code,
                raw[:200],
            )
            return _analyze_url_error_payload()

        # Cap body size before parsing (defense against huge HTML dumps).
        html = (resp.text or "")[:500_000]
        soup = BeautifulSoup(html, "html.parser")

        title = ""
        if soup.title and soup.title.string:
            title = soup.title.string.strip()
        if not title:
            og_title = soup.find("meta", property="og:title")
            if og_title and og_title.get("content"):
                title = str(og_title["content"]).strip()

        description = ""
        meta_desc = soup.find("meta", attrs={"name": re.compile(r"^description$", re.I)})
        if meta_desc and meta_desc.get("content"):
            description = str(meta_desc["content"]).strip()
        if not description:
            og_desc = soup.find("meta", property="og:description")
            if og_desc and og_desc.get("content"):
                description = str(og_desc["content"]).strip()

        return json.dumps(
            {
                "status": "ok",
                "url": raw,
                "title": title[:500],
                "description": description[:1000],
            },
            ensure_ascii=False,
        )
    except Exception as exc:
        # Timeouts, connection errors, TLS failures, 403 via raise_for_status path, etc.
        logger.info("execute_analyze_url failed for url=%s: %s", raw[:200], exc)
        return _analyze_url_error_payload()
