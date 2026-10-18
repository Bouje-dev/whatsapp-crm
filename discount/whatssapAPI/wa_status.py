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


def meta_failure_reason(payload) -> str:
    """Readable reason from a Graph API error body or a status-webhook errors list."""
    import json

    data = payload
    if isinstance(payload, str):
        text = payload.strip()
        if not text:
            return ""
        try:
            data = json.loads(text)
        except Exception:
            return text[:500]
    if not isinstance(data, dict):
        return ""

    items = []
    err = data.get("error")
    if isinstance(err, dict):
        items.append(err)
    raw_errors = data.get("errors")
    if isinstance(raw_errors, list):
        items.extend(item for item in raw_errors if isinstance(item, dict))
    elif isinstance(raw_errors, dict):
        items.append(raw_errors)

    parts = []
    for item in items:
        details = ""
        error_data = item.get("error_data")
        if isinstance(error_data, dict):
            details = str(error_data.get("details") or "").strip()
        message = str(item.get("message") or item.get("title") or "").strip()
        if details:
            parts.append(details)
        elif message:
            parts.append(message)
    reason = " — ".join(dict.fromkeys(part for part in parts if part))
    return reason[:500]


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
