"""
Context Integration - bridge AI session memory to the inbox Context Panel.

The AI agent stores live state in ``ChatSession.context_data`` (via session_state).
The Context Panel reads that same source through ``get_conversation_state_debug``.
"""
import logging
import re
from typing import Any, Dict, Optional

from discount.models import ChatSession, WhatsAppChannel, Products

logger = logging.getLogger(__name__)

_FIELD_LABELS_UI = {
    "customer_name": "Name",
    "phone_number": "Phone",
    "shipping_city": "City",
    "shipping_address": "Address",
    "email_address": "Email",
}


def _normalize_phone_digits(phone: str) -> str:
    return re.sub(r"\D", "", phone or "")


def _find_chat_session(channel_id: int, customer_phone: str) -> Optional[ChatSession]:
    """Resolve ChatSession across common phone formats (+212… vs 212…)."""
    clean = _normalize_phone_digits(customer_phone)
    candidates = []
    for val in (customer_phone, clean, f"+{clean}" if clean else None):
        if val and val not in candidates:
            candidates.append(val)

    for phone in candidates:
        session = (
            ChatSession.objects.filter(channel_id=channel_id, customer_phone=phone)
            .select_related("active_product", "active_node")
            .order_by("-last_interaction")
            .first()
        )
        if session:
            return session

    if len(clean) >= 9:
        return (
            ChatSession.objects.filter(
                channel_id=channel_id,
                customer_phone__endswith=clean[-9:],
            )
            .select_related("active_product", "active_node")
            .order_by("-last_interaction")
            .first()
        )
    return None


def _map_stage_for_ui(
    conversation_state: str,
    sales_stage: str,
    *,
    is_completed: bool = False,
    checkout_mode: str = "",
    last_order_id: str = "",
) -> str:
    cs = (conversation_state or "").strip().upper()
    ss = (sales_stage or "").strip().lower()
    mode = (checkout_mode or "").strip().lower()
    oid = (last_order_id or "").strip()

    if cs == "AWAITING_PAYMENT_RECEIPT":
        return "confirming"
    if is_completed or mode == "done" or (oid and cs != "GATHERING_INFO"):
        return "completed"
    if cs == "GATHERING_INFO":
        return "collecting_info"
    if ss in ("order_capture", "stage_5_closing", "soft_close"):
        return "confirming"
    if ss in ("stage_1_awareness", "stage_2_interest", "stage_3_consideration"):
        return "browsing"
    if ss:
        return "product_selected"
    if cs and cs != "IDLE":
        return cs.lower()
    return "initial"


def channel_accessible_for_user(channel: WhatsAppChannel, user) -> bool:
    if not channel or not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    if channel.owner_id == user.id:
        return True
    try:
        return channel.assigned_agents.filter(id=user.id).exists()
    except Exception:
        return False


def get_conversation_state_debug(channel_id: int, customer_phone: str) -> dict:
    """
    Build Context Panel payload from the live ChatSession (source of truth for the AI agent).
    """
    session = _find_chat_session(channel_id, customer_phone)
    ctx: dict = {}
    if session and isinstance(session.context_data, dict):
        ctx = session.context_data

    product = None
    active_product = getattr(session, "active_product", None) if session else None
    if active_product:
        price = getattr(active_product, "price", None)
        try:
            price_val = float(price) if price is not None else None
        except (TypeError, ValueError):
            price_val = None
        product = {
            "id": active_product.id,
            "name": (getattr(active_product, "name", None) or "").strip(),
            "price": price_val,
            "sku": getattr(active_product, "sku", None),
        }

    collected = ctx.get("collected_order_fields") or {}
    if not isinstance(collected, dict):
        collected = {}

    customer_data = {
        "name": (collected.get("customer_name") or ctx.get("customer_name") or "").strip() or None,
        "city": (collected.get("shipping_city") or ctx.get("customer_city") or "").strip() or None,
        "address": (collected.get("shipping_address") or ctx.get("customer_address") or "").strip() or None,
        "phone": (collected.get("phone_number") or customer_phone or "").strip() or None,
    }

    missing_keys: list[str] = []
    if active_product:
        try:
            from ai_assistant.order_checkout import compute_missing_order_fields
            missing_keys = compute_missing_order_fields(
                active_product,
                collected,
                customer_phone or "",
            )
        except Exception as exc:
            logger.debug("compute_missing_order_fields for context panel: %s", exc)

    missing_fields = [_FIELD_LABELS_UI.get(k, k.replace("_", " ").title()) for k in missing_keys]

    conversation_state = (ctx.get("conversation_state") or "IDLE").strip()
    sales_stage = (ctx.get("sales_stage") or "").strip()
    checkout_mode = (ctx.get("checkout_capture_mode") or "").strip()
    last_order_id = (ctx.get("last_order_id") or "").strip()
    is_completed = bool(session and session.is_completed)
    stage = _map_stage_for_ui(
        conversation_state,
        sales_stage,
        is_completed=is_completed,
        checkout_mode=checkout_mode,
        last_order_id=last_order_id,
    )

    notes: list[str] = []
    if ctx.get("memory_summary"):
        summary = str(ctx["memory_summary"]).strip()
        if summary:
            notes.append(f"Memory: {summary[:160]}{'…' if len(summary) > 160 else ''}")
    if conversation_state and conversation_state.upper() != "IDLE":
        notes.append(f"State: {conversation_state}")
    if sales_stage:
        notes.append(f"Sales stage: {sales_stage}")
    if ctx.get("sentiment"):
        notes.append(f"Sentiment: {ctx['sentiment']}")
    if ctx.get("checkout_capture_mode"):
        notes.append(f"Checkout: {ctx['checkout_capture_mode']}")
    if ctx.get("checkout_form_sent"):
        notes.append("WhatsApp form sent")
    if ctx.get("can_read"):
        notes.append("Text-comfortable customer (can_read)")
    text_count = ctx.get("user_text_message_count")
    if text_count:
        notes.append(f"Text messages: {text_count}")
    if ctx.get("last_order_id"):
        notes.append(f"Last order: {ctx['last_order_id']}")
    if ctx.get("final_agreed_price") or ctx.get("last_negotiated_price"):
        notes.append(
            f"Agreed price: {ctx.get('final_agreed_price') or ctx.get('last_negotiated_price')}"
        )
    if session and session.handover_reason:
        notes.append(f"Handover: {session.handover_reason}")
    if session and not session.ai_enabled:
        notes.append("AI paused — human agent active")

    ready = bool(
        product
        and not missing_keys
        and any(customer_data.values())
        and not is_completed
        and checkout_mode != "done"
    )

    state_summary = (
        f"ChatSession(product={product['name'] if product else 'None'}, "
        f"stage={stage}, fsm={conversation_state or 'IDLE'}, "
        f"missing={len(missing_fields)})"
    )

    return {
        "channel_id": channel_id,
        "customer_phone": customer_phone,
        "product": product,
        "customer_data": customer_data,
        "stage": stage,
        "intent": ctx.get("sentiment") or sales_stage or None,
        "missing_fields": missing_fields,
        "ready_to_order": ready,
        "notes": notes[-10:],
        "state_summary": state_summary,
        "conversation_state": conversation_state,
        "sales_stage": sales_stage,
        "can_read": bool(ctx.get("can_read")),
        "collected_fields": collected,
        "is_completed": is_completed,
        "last_order_id": last_order_id or None,
        "session_active": bool(
            session and not session.is_expired and not session.is_completed
        ),
        "ai_enabled": getattr(session, "ai_enabled", True) if session else None,
    }


def reset_conversation_context(channel_id: int, customer_phone: str):
    """Reset panel memory by clearing ChatSession checkout context."""
    channel = WhatsAppChannel.objects.filter(id=channel_id).first()
    if not channel:
        return
    try:
        from discount.whatssapAPI.session_state import (
            clear_session_and_cache,
            set_conversation_state,
            STATE_IDLE,
        )

        clear_session_and_cache(channel, customer_phone, reason="context_panel_reset")
        set_conversation_state(channel, customer_phone, STATE_IDLE)
        logger.info(
            "Context reset for channel=%s phone=…%s",
            channel_id,
            (_normalize_phone_digits(customer_phone) or "")[-4:],
        )
    except Exception as exc:
        logger.warning("reset_conversation_context ChatSession: %s", exc)


# Legacy cache-based API (docs / scripts) — not used by the live Context Panel.
def get_conversation_state(channel_id: int, customer_phone: str):
    from discount.services.conversation_state import get_conversation_state as _legacy_get
    return _legacy_get(channel_id, customer_phone)
