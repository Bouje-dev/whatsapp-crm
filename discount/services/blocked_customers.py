"""Block-list helpers for inbound WhatsApp webhook filtering."""
import logging
import re
from typing import Iterable, Optional

from discount.models import BlockedCustomer, WhatsAppChannel

logger = logging.getLogger(__name__)


def normalize_phone_digits(phone: str) -> str:
    return re.sub(r"\D", "", phone or "")


def phone_candidates(phone: str) -> list[str]:
    clean = normalize_phone_digits(phone)
    candidates: list[str] = []
    for val in (phone, clean, f"+{clean}" if clean else None):
        if val and val not in candidates:
            candidates.append(val)
    return candidates


def is_customer_blocked(channel, phone: str) -> bool:
    """True when ``phone`` is blocked on this WhatsApp channel."""
    if not channel or not phone:
        return False
    channel_id = getattr(channel, "id", None)
    if not channel_id:
        return False

    qs = BlockedCustomer.objects.filter(channel_id=channel_id)
    for cand in phone_candidates(phone):
        if qs.filter(phone=cand).exists():
            return True

    clean = normalize_phone_digits(phone)
    if len(clean) >= 9:
        suffix = clean[-9:]
        for stored in qs.values_list("phone", flat=True):
            stored_digits = normalize_phone_digits(stored)
            if stored_digits == clean or (suffix and stored_digits.endswith(suffix)):
                return True
    return False


def block_customer(
    channel,
    phone: str,
    *,
    blocked_by=None,
    reason: str = "",
) -> BlockedCustomer:
    clean = normalize_phone_digits(phone)
    canonical = clean or (phone or "").strip()
    if not channel or not canonical:
        raise ValueError("channel and phone are required")

    row, created = BlockedCustomer.objects.get_or_create(
        channel=channel,
        phone=canonical,
        defaults={
            "blocked_by": blocked_by,
            "reason": (reason or "").strip()[:255],
        },
    )
    if not created:
        updates: list[str] = []
        if reason and row.reason != reason.strip()[:255]:
            row.reason = reason.strip()[:255]
            updates.append("reason")
        if blocked_by and row.blocked_by_id != getattr(blocked_by, "id", None):
            row.blocked_by = blocked_by
            updates.append("blocked_by")
        if updates:
            row.save(update_fields=updates)
    logger.info(
        "Customer blocked channel=%s phone=…%s created=%s",
        getattr(channel, "id", None),
        canonical[-4:],
        created,
    )
    return row


def unblock_customer(channel, phone: str) -> int:
    if not channel or not phone:
        return 0
    deleted = 0
    channel_id = getattr(channel, "id", None)
    if not channel_id:
        return 0
    qs = BlockedCustomer.objects.filter(channel_id=channel_id)
    for cand in phone_candidates(phone):
        deleted += qs.filter(phone=cand).delete()[0]
    clean = normalize_phone_digits(phone)
    if len(clean) >= 9:
        suffix = clean[-9:]
        for row in qs:
            stored = normalize_phone_digits(row.phone)
            if stored == clean or (suffix and stored.endswith(suffix)):
                row.delete()
                deleted += 1
    return deleted


def any_blocked_in_batch(channel, phones: Iterable[str]) -> bool:
    for phone in phones:
        if phone and is_customer_blocked(channel, phone):
            return True
    return False
