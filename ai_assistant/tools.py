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


def _resolve_product_for_store(owner, *, product_id=None, product_name=None):
    """Resolve a catalog product by numeric ID or name (tenant-scoped)."""
    if not owner:
        return None
    from discount.models import Products

    if product_id is not None:
        try:
            row = Products.objects.filter(id=int(product_id), admin=owner).first()
            if row:
                return row
        except (TypeError, ValueError):
            pass

    name = (product_name or "").strip()
    if not name:
        return None

    row = Products.objects.filter(admin=owner, name__iexact=name).first()
    if row:
        return row

    tokens = [w for w in re.split(r"\s+", name.lower()) if len(w) >= 2]
    if not tokens:
        return None

    scored: list[tuple[int, Any]] = []
    for p in Products.objects.filter(admin=owner).order_by("name")[:200]:
        pname = (getattr(p, "name", None) or "").strip().lower()
        score = sum(10 for t in tokens if t in pname)
        if score > 0:
            scored.append((score, p))
    if not scored:
        return None
    scored.sort(key=lambda x: -x[0])
    if len(scored) == 1 or scored[0][0] > scored[1][0]:
        return scored[0][1]
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
        owner, product_id=product_id, product_name=product_name
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
        from discount.models import Products, ChatSession
        from discount.product_sales_prompt import build_product_context_for_prompt

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
        if prod is None:
            prod = Products.objects.filter(
                id=int(session.active_product_id), admin=store
            ).first()
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
