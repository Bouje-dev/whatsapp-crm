"""
Local WhatsApp AI sandbox.

Inbound messages are injected into ``process_messages`` with Meta-shaped
payloads. Outbound Graph API calls to sandbox phones are intercepted so
nothing is sent to real WhatsApp.
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Optional

from django.conf import settings
from django.db.models import Q

logger = logging.getLogger(__name__)

# Digit prefix unused by real Moroccan / GCC WhatsApp numbers.
SANDBOX_PREFIX = "99900"
SANDBOX_CONTACT_NAME = "Sandbox Tester"


def normalize_phone_digits(phone: str) -> str:
    return re.sub(r"\D", "", phone or "")


def is_sandbox_phone(phone: str) -> bool:
    return normalize_phone_digits(phone).startswith(SANDBOX_PREFIX)


def sandbox_phone_for(user, channel) -> str:
    uid = int(getattr(user, "id", 0) or 0)
    cid = int(getattr(channel, "id", 0) or 0)
    return f"{SANDBOX_PREFIX}{uid:04d}{cid:04d}"


def can_access_sandbox(user) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return bool(getattr(settings, "DEBUG", False))


def list_sandbox_channels(user):
    from discount.models import WhatsAppChannel

    if not user or not getattr(user, "is_authenticated", False):
        return WhatsAppChannel.objects.none()
    return (
        WhatsAppChannel.objects.filter(Q(owner=user) | Q(assigned_agents=user))
        .distinct()
        .order_by("id")
    )


def resolve_sandbox_channel(user, channel_id) -> Optional[object]:
    qs = list_sandbox_channels(user)
    if channel_id not in (None, "", "null", "undefined"):
        try:
            channel = qs.filter(id=int(channel_id)).first()
            if channel:
                return channel
        except (TypeError, ValueError):
            pass
    return qs.first()


class FakeGraphResponse:
    """Stand-in for ``requests.Response`` when Meta must not be called."""

    def __init__(self, payload=None, status_code=200):
        self.status_code = status_code
        if payload is None:
            payload = {"messages": [{"id": f"wamid.sandbox.{uuid.uuid4().hex[:24]}"}]}
        self._payload = payload
        self.text = json.dumps(payload)
        self.headers = {"X-Sandbox": "1"}

    def json(self):
        return self._payload


def build_inbound_message(
    phone: str,
    text: str = "",
    *,
    msg_type: str = "text",
    button_id: str = "",
    button_title: str = "",
    list_id: str = "",
    list_title: str = "",
    list_description: str = "",
    flow_token: str = "",
    flow_answers: Optional[dict] = None,
) -> dict:
    import time

    msg_id = f"wamid.sandbox.{uuid.uuid4().hex}"
    ts = str(int(time.time()))
    base = {"from": phone, "id": msg_id, "timestamp": ts, "type": msg_type}

    if msg_type in ("nfm_reply", "flow_reply") or (
        msg_type == "interactive" and isinstance(flow_answers, dict)
    ):
        answers = dict(flow_answers or {})
        token = (flow_token or answers.pop("flow_token", "") or "").strip()
        if token:
            answers["flow_token"] = token
        base["type"] = "interactive"
        base["interactive"] = {
            "type": "nfm_reply",
            "nfm_reply": {
                "name": "flow",
                "body": (text or "تم إرسال النموذج").strip() or "تم إرسال النموذج",
                "response_json": json.dumps(answers, ensure_ascii=False),
            },
        }
        return base

    if msg_type == "interactive":
        if list_title or list_id:
            base["interactive"] = {
                "type": "list_reply",
                "list_reply": {
                    "id": (list_id or f"row_sandbox_{uuid.uuid4().hex[:8]}").strip(),
                    "title": (list_title or text or "Option").strip()[:24],
                    "description": (list_description or "").strip()[:72],
                },
            }
        else:
            title = (button_title or text or "OK").strip()[:20]
            base["interactive"] = {
                "type": "button_reply",
                "button_reply": {
                    "id": (button_id or f"btn_sandbox_{uuid.uuid4().hex[:8]}").strip(),
                    "title": title,
                },
            }
        return base

    if msg_type == "button":
        base["button"] = {
            "text": (button_title or text or "OK").strip(),
            "payload": (button_id or "").strip(),
        }
        return base

    base["type"] = "text"
    base["text"] = {"body": (text or "").strip()}
    return base


def serialize_sandbox_message(msg) -> dict:
    from discount.whatssapAPI.process_messages import decode_interactive_captions

    interactive = None
    try:
        interactive = decode_interactive_captions(getattr(msg, "captions", None), msg.body or "")
    except Exception:
        interactive = None

    # Enrich WhatsApp Flow cards with pending form fields for the lab mock UI.
    if isinstance(interactive, dict) and interactive.get("kind") == "whatsapp_flow":
        try:
            from discount.whatssapAPI.whatsapp_flows import get_flow_pending

            channel = getattr(msg, "channel", None)
            sender = getattr(msg, "sender", None) or ""
            token = (interactive.get("flow_token") or "").strip()
            pending = get_flow_pending(channel, sender, token) if channel and sender else None
            if isinstance(pending, dict):
                content = pending.get("content") if isinstance(pending.get("content"), dict) else {}
                interactive["flow_token"] = (
                    (pending.get("flow_token") or token or "").strip()
                )
                interactive["fields"] = list(content.get("fields") or [])
                interactive["product_name"] = (content.get("product_name") or "").strip()
                interactive["screen_title"] = (content.get("screen_title") or "").strip()
                interactive["submit_label"] = (
                    (content.get("submit_label") or "تأكيد الطلب").strip()
                )
                interactive["product_id"] = pending.get("product_id") or content.get("product_id")
                if not interactive.get("cta") and content.get("cta_label"):
                    interactive["cta"] = str(content.get("cta_label")).strip()[:20]
        except Exception as exc:
            logger.debug("serialize_sandbox_message flow enrich: %s", exc)

    ts = getattr(msg, "timestamp", None) or getattr(msg, "created_at", None)
    return {
        "id": msg.id,
        "body": msg.body or "",
        "is_from_me": bool(msg.is_from_me),
        "is_internal": bool(getattr(msg, "is_internal", False)),
        "type": (msg.type or "") or ("note" if getattr(msg, "is_internal", False) else "text"),
        "media_type": msg.media_type or "",
        "media_url": msg.media_url or "",
        "timestamp": ts.isoformat() if ts else "",
        "interactive": interactive,
    }


def reset_sandbox_identity(channel, phone: str, *, wipe_messages: bool, wipe_orders: bool) -> dict:
    """
    Treat the sandbox phone as a brand-new customer.

    wipe_messages=False keeps the transcript visible, but the AI may still
    read those rows as conversation history. wipe_messages=True matches a
    first-time WhatsApp customer.
    """
    from discount.models import (
        ChatSession,
        Contact,
        FollowUpTask,
        HandoverLog,
        Message,
        SimpleOrder,
        WhatsAppCheckoutState,
    )
    from discount.whatssapAPI.session_state import clear_session_and_cache

    if not channel or not phone:
        return {"ok": False, "error": "channel_and_phone_required"}

    try:
        clear_session_and_cache(channel, phone, reason="sandbox_reset")
    except Exception as exc:
        logger.warning("sandbox clear_session_and_cache: %s", exc)

    deleted = {
        "sessions": 0,
        "messages": 0,
        "contacts": 0,
        "follow_ups": 0,
        "handovers": 0,
        "orders": 0,
        "checkout_states": 0,
    }

    deleted["sessions"] = ChatSession.objects.filter(
        channel=channel, customer_phone=phone
    ).delete()[0]
    deleted["checkout_states"] = WhatsAppCheckoutState.objects.filter(
        channel=channel, customer_phone=phone
    ).delete()[0]
    deleted["follow_ups"] = FollowUpTask.objects.filter(
        channel=channel, customer_phone=phone
    ).delete()[0]
    try:
        deleted["handovers"] = HandoverLog.objects.filter(
            channel=channel, customer_phone=phone
        ).delete()[0]
    except Exception:
        pass

    if wipe_messages:
        deleted["messages"] = Message.objects.filter(channel=channel, sender=phone).delete()[0]
        deleted["contacts"] = Contact.objects.filter(channel=channel, phone=phone).delete()[0]

    if wipe_orders:
        deleted["orders"] = SimpleOrder.objects.filter(
            channel=channel, customer_phone=phone
        ).delete()[0]

    return {"ok": True, "deleted": deleted}
