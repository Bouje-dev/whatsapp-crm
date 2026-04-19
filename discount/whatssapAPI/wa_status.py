"""
Normalize WhatsApp Cloud API message status webhook values for DB + inbox UI.

Meta may send values we do not store on Message (e.g. engagement signals for audio).
Those must map to sent|delivered|read|failed so the dashboard ticks stay correct.
"""

from __future__ import annotations

import datetime as _dt
import logging

logger = logging.getLogger(__name__)


def normalize_whatsapp_delivery_status(raw) -> str:
    """Map webhook status strings to Message.status choices."""
    if raw is None or raw == "":
        return "sent"
    s = str(raw).strip().lower()
    if s in ("sent", "delivered", "read", "failed"):
        return s
    # Voice/audio engagement — show double blue ticks like "read"
    if s in ("played", "listened"):
        return "read"
    if "fail" in s:
        return "failed"
    logger.debug("Unknown WhatsApp delivery status %r — defaulting to sent", raw)
    return "sent"


def status_timestamp_from_meta_webhook(status_dict: dict):
    """Parse Meta status.timestamp (unix seconds, string or number) to aware UTC datetime."""
    ts = (status_dict or {}).get("timestamp")
    if ts is None:
        return _dt.datetime.now(_dt.timezone.utc)
    try:
        sec = int(float(str(ts).strip()))
        return _dt.datetime.fromtimestamp(sec, tz=_dt.timezone.utc)
    except Exception:
        return _dt.datetime.now(_dt.timezone.utc)
