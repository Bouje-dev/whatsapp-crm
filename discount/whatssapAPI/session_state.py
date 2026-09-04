"""
Persistent Session-State Management — WhatsApp AI Agent Router
==============================================================

Architecture philosophy (Persistent State)
-------------------------------------------
Sessions are PERMANENT — they are never expired by time.
E-commerce users return after 20-30 days (payday) and must resume
seamlessly without re-sending trigger keywords.

A session is only resolved explicitly:
  • is_completed=True  — order submitted (submit_customer_order tool fired)
  • is_expired=True    — user sent a hard-reset keyword or HITL handover

Two-layer lookup
----------------
  Layer 1  Django cache  (in-memory / Redis / Memcached)
           TTL = SESSION_CACHE_TTL (7 days — covers frequent users).
           Used on EVERY incoming message — no SQL query needed for warm cache.
           Cold cache (returning after >7 days) automatically falls through to DB.

  Layer 2  ChatSession DB model  (source of truth, truly permanent)
           Consulted on cache-miss; result is back-filled into cache.

Global Interrupts
-----------------
Trigger evaluation ALWAYS runs first. If a trigger matches a DIFFERENT
flow than the current session, the session is switched (global interrupt).
This lets a customer who was buying Product A spontaneously ask about
Product B without needing to cancel first.

Public API (called from process_messages.py)
--------------------------------------------
  is_hard_reset_keyword(body)
  get_reset_ack(channel)
  get_active_node_fast(channel, phone)          → Node | None
  set_session_cache(channel, phone, node, ...)
  clear_session_and_cache(channel, phone, reason="")
  complete_session(channel, phone)              — marks is_completed=True
  get_session_context_data(channel, phone)      → dict
  update_session_context_data(channel, phone, patch)

  # Conversation state-machine (post-tool transitions)
  set_conversation_state(channel, phone, state, **extra)
  get_conversation_state(channel, phone)        → str | None
  clear_conversation_state(channel, phone)

Conversation states
-------------------
The router treats the value of ``context_data['conversation_state']`` as a
finite state machine. The AI prompt builder injects a strict guard banner
at the very top of the system prompt for every non-default state so the
LLM cannot regress to an earlier slot-filling step.

  IDLE                      — default; no override is injected.
  AWAITING_PAYMENT_RECEIPT  — digital order created; waiting for the
                              customer's payment screenshot/PDF. The AI
                              must NOT ask for name/address or call
                              submit_customer_order again.
  POST_SALE_SUPPORT         — order already registered. The AI is
                              customer support, not a closer: answer
                              then stop; never volunteer cancellation.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

# Cache TTL: 7 days covers frequent users.
# After 7 days the cache entry expires naturally; the DB is the fallback.
# (The session itself in the DB has NO expiry — it lives until explicitly resolved.)
SESSION_CACHE_TTL: int = 7 * 24 * 3600  # 7 days in seconds

_CACHE_KEY_PREFIX: str = "wachat_sess"

# ── Conversation state-machine values ────────────────────────────────────────
# These are the only legal values for ``context_data['conversation_state']``.
# Treat the key as a contract — every consumer (router + prompt builder)
# imports the constant rather than typing the string literal.
STATE_KEY: str = "conversation_state"
STATE_IDLE: str = "IDLE"
STATE_GATHERING_INFO: str = "GATHERING_INFO"
STATE_AWAITING_PAYMENT_RECEIPT: str = "AWAITING_PAYMENT_RECEIPT"
STATE_POST_SALE_SUPPORT: str = "POST_SALE_SUPPORT"

_LEGAL_STATES: frozenset[str] = frozenset({
    STATE_IDLE,
    STATE_GATHERING_INFO,
    STATE_AWAITING_PAYMENT_RECEIPT,
    STATE_POST_SALE_SUPPORT,
})

CTX_USER_TEXT_MSG_COUNT: str = "user_text_message_count"
CTX_CAN_READ: str = "can_read"
CTX_COLLECTED_ORDER_FIELDS: str = "collected_order_fields"

# Session context keys cleared on product pivot — negotiation, checkout, and locks
# tied to the PREVIOUS product must not carry over.
_PRODUCT_PIVOT_RESET_KEYS: frozenset[str] = frozenset({
    "has_asked_for_sale",
    "sales_stage",
    "sentiment",
    "memory_summary",
    "memory_summary_source_count",
    "memory_summary_recent_limit",
    "last_negotiated_price",
    "final_agreed_price",
    "negotiated_price",
    "checkout_pending",
    "pending_checkout",
    "awaiting_receipt_for_product",
    "last_order_id",
    "order_id",
    "upsell_pending",
    "payment_method_chosen",
    "checkout_capture_mode",
    "checkout_form_sent",
    "checkout_voice_pending_order",
})

# Reasons that indicate an explicit product pivot (preserve over node default).
_PIVOT_REASONS: frozenset[str] = frozenset({
    "switch_active_product_tool",
    "search_products",
    "search_products_auto_sync",
    "search_products_exact_match",
    "incoming_message",
    "send_product_media",
})

# Legacy alias — pricing-only clear (used on order complete / session clear).
_PRICING_SESSION_KEYS = _PRODUCT_PIVOT_RESET_KEYS


# ── Hard-reset keywords ───────────────────────────────────────────────────────
# Exact full-string match (case-insensitive, stripped).
# Partial matches NEVER trigger a reset (e.g. a product description
# containing the word "stop" is safe).
RESET_KEYWORDS: frozenset[str] = frozenset({
    # Modern Standard / Shared Arabic
    "إلغاء", "الغاء", "إلغء",
    "رجوع", "ارجع", "رجع",
    "وقف", "توقف", "أوقف",
    "خروج", "اخرج",
    "لا أريد", "لا اريد", "ما أبي", "ما ابي",
    "ابدأ من جديد", "من جديد", "من البداية",
    "بداية", "بدايه",
    # Moroccan Darija
    "wqef", "bda mn jdid", "mn jdid", "mchit", "rja3", "bghit nrja3",
    # Gulf / Saudi
    "وقف الحين", "ايقاف", "مو حابب",
    # English
    "cancel", "stop", "exit", "reset", "back", "restart", "quit", "start over",
    # French
    "annuler", "arrêter", "quitter", "recommencer",
})

_RESET_ACK_TEXT: dict[str, str] = {
    "ar":      "تم إلغاء المحادثة. كيف يمكنني مساعدتك؟",
    "default": "تم إلغاء المحادثة. كيف يمكنني مساعدتك؟",
    "fr":      "Conversation réinitialisée. Comment puis-je vous aider ?",
    "en":      "Session cleared. How can I help you?",
}


# ── Cache key ─────────────────────────────────────────────────────────────────

def _cache_key(channel_id: int, phone: str) -> str:
    clean = (phone or "").strip().replace("+", "").replace(" ", "")
    return f"{_CACHE_KEY_PREFIX}:{channel_id}:{clean}"


# ── Hard-reset detection ──────────────────────────────────────────────────────

def is_hard_reset_keyword(body: str) -> bool:
    """
    True iff ``body`` exactly matches a hard-reset keyword (case-insensitive,
    full string). A product description containing "stop" never fires this.
    """
    if not body:
        return False
    return (body or "").strip().lower() in RESET_KEYWORDS


def get_reset_ack(channel=None) -> str:
    lang = ""
    if channel:
        lang = (getattr(channel, "output_language", None) or "").strip().lower()
    return _RESET_ACK_TEXT.get(lang) or _RESET_ACK_TEXT["default"]


# ── Cache operations ──────────────────────────────────────────────────────────

def set_session_cache(
    channel,
    phone: str,
    node,
    context_data: dict | None = None,
    active_product=None,
) -> None:
    """
    Write the active-session entry to cache and touch the DB row.
    Call after every AI response to keep the 7-day cache TTL warm.
    """
    if not channel or not phone or not node:
        return
    channel_id = getattr(channel, "id", None)
    if not channel_id:
        return

    ctx = dict(context_data or {})
    ctx.setdefault("active_node_id", node.pk)
    if active_product is not None:
        pid = getattr(active_product, "pk", None) or getattr(active_product, "id", None)
        if pid is not None:
            ctx["active_product_id"] = int(pid)

    payload: dict = {
        "node_id": node.pk,
        "channel_id": channel_id,
        "phone": phone,
        "context_data": ctx,
    }
    if active_product is not None:
        pid = getattr(active_product, "pk", None) or getattr(active_product, "id", None)
        if pid is not None:
            payload["product_id"] = int(pid)
    cache.set(_cache_key(channel_id, phone), payload, timeout=SESSION_CACHE_TTL)
    logger.debug(
        "[SessionState] SET  channel=%s phone=…%s node=%s",
        channel_id, (phone or "")[-4:], node.pk,
    )
    try:
        from discount.models import ChatSession
        ChatSession.objects.filter(
            channel=channel,
            customer_phone=phone,
            is_expired=False,
            is_completed=False,
        ).update(last_interaction=timezone.now())
    except Exception as exc:
        logger.debug("[SessionState] DB touch skipped: %s", exc)


def persist_sticky_sales_session(channel, phone: str, node, active_product=None) -> None:
    """
    Sticky session: persist active_node (+ product) so later messages skip trigger keywords.
    Clears completed/expired flags when the customer re-enters a product flow.
    """
    if not channel or not phone or not node:
        return
    product = active_product
    if product is None and node and channel:
        try:
            ai_cfg = getattr(node, "ai_model_config", None) or {}
            pid = ai_cfg.get("product_id") if isinstance(ai_cfg, dict) else None
            if pid is not None:
                from discount.services.product_scope import get_channel_product

                product = get_channel_product(channel, product_id=pid)
        except Exception:
            product = None
    if product is not None:
        from discount.services.product_scope import product_belongs_to_channel

        if not product_belongs_to_channel(product, channel):
            product = None
    try:
        from discount.models import ChatSession

        ctx_patch = {
            "active_node_id": node.pk,
            "sticky_sales": True,
        }
        if product is not None:
            pid = getattr(product, "pk", None) or getattr(product, "id", None)
            if pid is not None:
                ctx_patch["active_product_id"] = int(pid)

        session, _created = ChatSession.objects.update_or_create(
            channel=channel,
            customer_phone=phone,
            defaults={
                "active_node": node,
                "active_product": product,
                "is_expired": False,
                "is_completed": False,
                "last_interaction": timezone.now(),
            },
        )
        existing_ctx = getattr(session, "context_data", None) or {}
        if not isinstance(existing_ctx, dict):
            existing_ctx = {}
        existing_ctx.update(ctx_patch)
        session.context_data = existing_ctx
        session.save(update_fields=["context_data", "last_interaction"])
        set_session_cache(channel, phone, node, existing_ctx, active_product=product)
        logger.info(
            "[SessionState] STICKY  channel=%s phone=…%s node=%s product=%s",
            getattr(channel, "id", "?"),
            (phone or "")[-4:],
            node.pk,
            getattr(product, "pk", None) if product else "—",
        )
    except Exception as exc:
        logger.warning("[SessionState] persist_sticky_sales_session failed: %s", exc)


def get_active_node_fast(channel, phone: str):
    """
    Return the active ``Node`` for (channel, phone), or ``None``.

    No time filter — sessions are permanent until explicitly resolved.

    Lookup order:
      1. Cache hit  → O(1), single PK lookup on Node.
      2. Cache miss → DB query, then back-fills cache.
      3. Nothing    → None.
    """
    if not channel or not phone:
        return None
    channel_id = getattr(channel, "id", None)
    if not channel_id:
        return None

    # Layer 1 — cache
    payload = cache.get(_cache_key(channel_id, phone))
    if payload:
        node_id = payload.get("node_id")
        if node_id:
            try:
                from discount.models import Node
                node = Node.objects.select_related("flow").filter(pk=node_id).first()
                if node:
                    logger.debug(
                        "[SessionState] CACHE HIT  channel=%s phone=…%s node=%s",
                        channel_id, (phone or "")[-4:], node_id,
                    )
                    return node
            except Exception as exc:
                logger.warning("[SessionState] Node PK lookup: %s", exc)

    # Layer 2 — DB fallback (no time cutoff — permanent sessions)
    try:
        from discount.models import ChatSession, Node
        session = (
            ChatSession.objects.filter(
                channel=channel,
                customer_phone=phone,
                is_expired=False,
                is_completed=False,
            )
            .select_related("active_node", "active_node__flow")
            .first()
        )
        if session and getattr(session, "active_node", None):
            node = session.active_node
            fill: dict = {
                "node_id": node.pk,
                "channel_id": channel_id,
                "phone": phone,
                "context_data": getattr(session, "context_data", None) or {},
            }
            cache.set(_cache_key(channel_id, phone), fill, timeout=SESSION_CACHE_TTL)
            logger.debug(
                "[SessionState] DB FALLBACK + CACHE FILL  channel=%s phone=…%s node=%s",
                channel_id, (phone or "")[-4:], node.pk,
            )
            return node
    except Exception as exc:
        logger.warning("[SessionState] DB session fallback: %s", exc)

    return None


def _strip_pricing_context(ctx: dict | None) -> dict:
    """Remove negotiation/checkout keys that must not carry across products."""
    cleaned = dict(ctx or {})
    for key in _PRODUCT_PIVOT_RESET_KEYS:
        cleaned.pop(key, None)
    return cleaned


def _reset_context_for_product_pivot(ctx: dict | None) -> dict:
    """
    Full session reset when the customer pivots to a different product.
    Clears checkout/negotiation locks and returns FSM to IDLE.
    """
    cleaned = _strip_pricing_context(ctx)
    cleaned[STATE_KEY] = STATE_IDLE
    cleaned.pop("product_pivot_active", None)
    return cleaned


def clear_session_pricing_state(channel, phone: str) -> None:
    """Clear product-specific negotiation state from cache + DB without expiring the session."""
    if not channel or not phone:
        return
    channel_id = getattr(channel, "id", None)
    if not channel_id:
        return
    key = _cache_key(channel_id, phone)
    payload = cache.get(key) or {}
    ctx = _strip_pricing_context(payload.get("context_data"))
    payload["context_data"] = ctx
    cache.set(key, payload, timeout=SESSION_CACHE_TTL)
    try:
        from discount.models import ChatSession
        session = ChatSession.objects.filter(
            channel=channel,
            customer_phone=phone,
            is_expired=False,
        ).first()
        if session:
            session.context_data = _strip_pricing_context(session.context_data)
            session.save(update_fields=["context_data", "last_interaction"])
    except Exception as exc:
        logger.warning("[SessionState] clear_session_pricing_state DB: %s", exc)


def set_session_active_product(channel, phone: str, product, *, reason: str = "") -> bool:
    """
    Force-update ``ChatSession.active_product`` and evict stale pricing/checkout locks.

    When the product changes (or reason is an explicit pivot), resets negotiation
    state and sets ``product_pivot_active`` so node-default products cannot revert
    the customer's chosen product on the next message.

    Returns True when the active product actually changed.
    """
    if not channel or not phone or not product:
        return False
    from discount.services.product_scope import product_belongs_to_channel

    if not product_belongs_to_channel(product, channel):
        logger.warning(
            "[SessionState] ACTIVE_PRODUCT rejected: product %s is not in channel %s catalog",
            getattr(product, "id", None),
            getattr(channel, "id", None),
        )
        return False
    pid = getattr(product, "pk", None) or getattr(product, "id", None)
    if pid is None:
        return False
    reason_key = (reason or "").strip()
    is_pivot = reason_key in _PIVOT_REASONS
    try:
        from discount.models import ChatSession

        session = (
            ChatSession.objects.filter(
                channel=channel,
                customer_phone=phone,
                is_expired=False,
            )
            .select_related("active_node")
            .first()
        )
        if not session:
            return False
        switched = session.active_product_id != int(pid)
        session.active_product_id = int(pid)
        ctx = getattr(session, "context_data", None) or {}
        if not isinstance(ctx, dict):
            ctx = {}
        if switched or is_pivot:
            ctx = _reset_context_for_product_pivot(ctx)
            ctx["product_pivot_active"] = True
            ctx["active_product_switched_at"] = timezone.now().isoformat()
        ctx["active_product_id"] = int(pid)
        session.context_data = ctx
        session.last_interaction = timezone.now()
        session.save(update_fields=["active_product", "context_data", "last_interaction"])
        node = getattr(session, "active_node", None)
        if node:
            set_session_cache(channel, phone, node, ctx, active_product=product)
        logger.info(
            "[SessionState] ACTIVE_PRODUCT channel=%s phone=…%s product=%s switched=%s pivot=%s reason=%s",
            getattr(channel, "id", "?"),
            (phone or "")[-4:],
            pid,
            switched,
            is_pivot or switched,
            reason_key or "—",
        )
        return switched
    except Exception as exc:
        logger.warning("[SessionState] set_session_active_product failed: %s", exc)
        return False


def clear_session_and_cache(channel, phone: str, reason: str = "") -> None:
    """
    Evict cache + mark DB session as expired (cancelled/handover).
    Does NOT set is_completed — use complete_session() for order completion.
    """
    if not channel or not phone:
        return
    clear_session_pricing_state(channel, phone)
    channel_id = getattr(channel, "id", None)
    if channel_id:
        cache.delete(_cache_key(channel_id, phone))
        logger.info(
            "[SessionState] CLEAR  channel=%s phone=…%s reason=%s",
            channel_id, (phone or "")[-4:], reason or "—",
        )
    try:
        from discount.models import ChatSession
        ChatSession.objects.filter(
            channel=channel,
            customer_phone=phone,
        ).update(is_expired=True)
    except Exception as exc:
        logger.warning("[SessionState] DB expire: %s", exc)


def complete_session(channel, phone: str) -> None:
    """
    Mark session as completed (order submitted).
    Evicts cache and clears product-specific pricing state so limits do not linger.
    """
    if not channel or not phone:
        return
    clear_session_pricing_state(channel, phone)
    channel_id = getattr(channel, "id", None)
    if channel_id:
        cache.delete(_cache_key(channel_id, phone))
        logger.info(
            "[SessionState] COMPLETE  channel=%s phone=…%s",
            channel_id, (phone or "")[-4:],
        )
    try:
        from discount.models import ChatSession
        ChatSession.objects.filter(
            channel=channel,
            customer_phone=phone,
        ).update(is_completed=True)
    except Exception as exc:
        logger.warning("[SessionState] DB complete: %s", exc)


def get_session_context_data(channel, phone: str) -> dict:
    """Return context_data for the active session, or {}."""
    if not channel or not phone:
        return {}
    channel_id = getattr(channel, "id", None)
    if not channel_id:
        return {}

    payload = cache.get(_cache_key(channel_id, phone))
    if payload:
        return payload.get("context_data") or {}

    try:
        from discount.models import ChatSession
        session = ChatSession.objects.filter(
            channel=channel,
            customer_phone=phone,
            is_expired=False,
            is_completed=False,
        ).first()
        return (getattr(session, "context_data", None) or {}) if session else {}
    except Exception:
        return {}


def update_session_context_data(channel, phone: str, patch: dict) -> None:
    """Merge ``patch`` into context_data in both cache and DB."""
    if not channel or not phone or not patch:
        return
    channel_id = getattr(channel, "id", None)
    if not channel_id:
        return
    key = _cache_key(channel_id, phone)
    payload = cache.get(key) or {}
    ctx: dict = payload.get("context_data") or {}
    ctx.update(patch)
    payload["context_data"] = ctx
    cache.set(key, payload, timeout=SESSION_CACHE_TTL)
    try:
        from discount.models import ChatSession
        session = ChatSession.objects.filter(
            channel=channel,
            customer_phone=phone,
            is_expired=False,
            is_completed=False,
        ).first()
        if session:
            existing: dict = session.context_data or {}
            existing.update(patch)
            session.context_data = existing
            session.save(update_fields=["context_data", "last_interaction"])
    except Exception as exc:
        logger.warning("[SessionState] update_context DB: %s", exc)


def record_user_text_message(channel, phone: str, increment: int = 1) -> dict:
    """
    Increment inbound text message counter (audio/voice excluded).
    Sets can_read=True when count > 1.
    Returns updated {user_text_message_count, can_read}.
    """
    if not channel or not phone:
        return {"user_text_message_count": 0, "can_read": False}

    try:
        increment = max(1, int(increment or 1))
    except (TypeError, ValueError):
        increment = 1

    ctx = get_session_context_data(channel, phone) or {}
    try:
        count = int(ctx.get(CTX_USER_TEXT_MSG_COUNT) or 0)
    except (TypeError, ValueError):
        count = 0
    count += increment
    can_read = count > 1
    patch = {
        CTX_USER_TEXT_MSG_COUNT: count,
        CTX_CAN_READ: can_read,
    }
    update_session_context_data(channel, phone, patch)
    return {"user_text_message_count": count, "can_read": can_read}


def get_can_read_flag(channel, phone: str) -> bool:
    ctx = get_session_context_data(channel, phone) or {}
    return bool(ctx.get(CTX_CAN_READ))


# ── Conversation state-machine helpers ────────────────────────────────────────

def set_conversation_state(
    channel,
    phone: str,
    state: str,
    **extra,
) -> None:
    """
    Transition the conversation state machine and persist it to both cache and DB.

    ``state`` MUST be one of the values defined in ``_LEGAL_STATES`` (e.g.
    ``STATE_AWAITING_PAYMENT_RECEIPT``). Any other value is rejected with a
    warning and the call becomes a no-op — defensive guard so a typo cannot
    silently put a session into an undefined state.

    Optional ``extra`` keyword arguments are merged into ``context_data``
    alongside the state, useful for storing things like ``order_id`` or
    ``payment_method_chosen`` next to the state itself.
    """
    if not channel or not phone:
        return
    if not state or state not in _LEGAL_STATES:
        logger.warning(
            "[SessionState] set_conversation_state: rejected illegal state=%r (channel=%s phone=…%s)",
            state, getattr(channel, "id", None), (phone or "")[-4:],
        )
        return
    patch: dict = {STATE_KEY: state}
    if extra:
        # Only persist JSON-safe scalars under namespaced keys to avoid
        # accidentally bloating context_data with non-serializable objects.
        for k, v in extra.items():
            if not isinstance(k, str) or not k:
                continue
            if isinstance(v, (str, int, float, bool)) or v is None:
                patch[k] = v
    update_session_context_data(channel, phone, patch)
    logger.info(
        "[SessionState] STATE channel=%s phone=…%s → %s (extras=%s)",
        getattr(channel, "id", None), (phone or "")[-4:], state,
        sorted([k for k in patch.keys() if k != STATE_KEY]) or "—",
    )


def get_conversation_state(channel, phone: str) -> str | None:
    """
    Return the active conversation-state string, or ``None`` when the session
    has no state set (treat as IDLE).
    """
    ctx = get_session_context_data(channel, phone) or {}
    state = ctx.get(STATE_KEY)
    if not state or not isinstance(state, str):
        return None
    if state not in _LEGAL_STATES:
        logger.warning(
            "[SessionState] get_conversation_state: ignoring unknown stored state=%r",
            state,
        )
        return None
    return state


def clear_conversation_state(channel, phone: str) -> None:
    """Reset the state machine back to IDLE (e.g. after the customer sends the receipt)."""
    if not channel or not phone:
        return
    prev = get_conversation_state(channel, phone)
    if prev == STATE_AWAITING_PAYMENT_RECEIPT:
        clear_session_pricing_state(channel, phone)
    update_session_context_data(channel, phone, {STATE_KEY: STATE_IDLE})
    logger.info(
        "[SessionState] STATE channel=%s phone=…%s → %s",
        getattr(channel, "id", None), (phone or "")[-4:], STATE_IDLE,
    )
