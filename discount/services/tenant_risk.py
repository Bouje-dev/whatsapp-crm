"""
Founder HQ — tenant risk metrics, complaint logging, and proactive alerting.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.core.mail import send_mail
from django.db.models import Count, Q
from django.utils import timezone

logger = logging.getLogger(__name__)

# Complaints in rolling 24h above this → red flag + email alert
COMPLAINT_THRESHOLD_24H = int(getattr(settings, "FOUNDER_RISK_COMPLAINT_THRESHOLD_24H", 5))

_COMPLETED_STATUSES = ("completed", "delivered")
_PENDING_STATUSES = ("pending_payment", "pending_verification")
_SUPPORT_COMPLAINT_STATUSES = (
    "awaiting_proof",
    "under_review",
    "resolved",
    "rejected",
)


@dataclass
class MerchantRiskSnapshot:
    merchant_id: int
    total_complaints: int
    complaints_24h: int
    first_time_success_rate: float
    pending_orders_count: int
    completed_orders_count: int
    is_red_flag: bool
    email: str
    user_name: str
    is_suspended: bool
    suspension_reason: str


def _merchant_channel_filter(merchant_id: int) -> Q:
    return Q(channel__owner_id=merchant_id)


def record_risk_event(
    *,
    merchant,
    event_type: str,
    channel=None,
    order=None,
    customer_phone: str = "",
    summary: str = "",
    metadata: dict | None = None,
    check_alert: bool = True,
):
    """Persist an auditable incident and optionally notify the founder."""
    from discount.models import FounderRiskAlert, MerchantRiskEvent

    if not merchant or getattr(merchant, "is_bot", False):
        return None
    try:
        event = MerchantRiskEvent.objects.create(
            merchant=merchant,
            channel=channel,
            order=order,
            customer_phone=(customer_phone or "")[:30],
            event_type=event_type,
            summary=(summary or "")[:4000],
            metadata=metadata or {},
        )
    except Exception as exc:
        logger.exception("record_risk_event failed: %s", exc)
        return None

    if check_alert:
        try:
            maybe_send_founder_risk_alert(merchant)
        except Exception as alert_exc:
            logger.exception("maybe_send_founder_risk_alert failed: %s", alert_exc)
    return event


def resolve_merchant_from_channel(channel):
    if not channel:
        return None
    return getattr(channel, "owner", None)


def record_event_for_channel(
    channel,
    event_type: str,
    *,
    order=None,
    customer_phone: str = "",
    summary: str = "",
    metadata: dict | None = None,
):
    merchant = resolve_merchant_from_channel(channel)
    if not merchant:
        return None
    return record_risk_event(
        merchant=merchant,
        event_type=event_type,
        channel=channel,
        order=order,
        customer_phone=customer_phone,
        summary=summary,
        metadata=metadata,
    )


def compute_merchant_metrics(merchant_id: int, *, window_hours: int = 24) -> dict[str, Any]:
    """Aggregate risk KPIs for one seller (used by audit detail + dashboard rows)."""
    from discount.models import MerchantRiskEvent, SimpleOrder

    since = timezone.now() - timedelta(hours=window_hours)
    channel_q = _merchant_channel_filter(merchant_id)

    total_complaints = MerchantRiskEvent.objects.filter(merchant_id=merchant_id).count()
    complaints_24h = MerchantRiskEvent.objects.filter(
        merchant_id=merchant_id,
        created_at__gte=since,
    ).count()

    orders = SimpleOrder.objects.filter(channel_q)
    pending_orders_count = orders.filter(status__in=_PENDING_STATUSES).count()
    completed_orders_count = orders.filter(status__in=_COMPLETED_STATUSES).count()
    clean_completions = orders.filter(
        status__in=_COMPLETED_STATUSES,
        support_status="none",
    ).count()

    if completed_orders_count > 0:
        first_time_success_rate = round(100.0 * clean_completions / completed_orders_count, 1)
    else:
        first_time_success_rate = 100.0 if orders.exists() else 0.0

    return {
        "total_complaints": total_complaints,
        "complaints_24h": complaints_24h,
        "pending_orders_count": pending_orders_count,
        "completed_orders_count": completed_orders_count,
        "first_time_success_rate": first_time_success_rate,
        "is_red_flag": complaints_24h > COMPLAINT_THRESHOLD_24H,
    }


def build_merchant_snapshot(merchant) -> MerchantRiskSnapshot:
    metrics = compute_merchant_metrics(merchant.id)
    return MerchantRiskSnapshot(
        merchant_id=merchant.id,
        email=getattr(merchant, "email", "") or "",
        user_name=(getattr(merchant, "user_name", None) or getattr(merchant, "username", "") or ""),
        is_suspended=bool(getattr(merchant, "is_suspended", False)),
        suspension_reason=(getattr(merchant, "suspension_reason", None) or ""),
        **metrics,
    )


def get_risk_dashboard_merchants():
    """All sellers sorted by total_complaints descending."""
    from discount.models import CustomUser

    merchants = list(
        CustomUser.objects.filter(is_bot=False, is_superuser=False)
        .only(
            "id",
            "email",
            "user_name",
            "username",
            "is_suspended",
            "suspension_reason",
            "stripe_subscription_status",
            "date_joined",
        )
        .order_by("-date_joined")
    )
    rows = []
    for m in merchants:
        snap = build_merchant_snapshot(m)
        rows.append({"merchant": m, "metrics": snap})
    rows.sort(key=lambda r: (-r["metrics"].total_complaints, -r["metrics"].complaints_24h))
    return rows


def get_affected_contacts_for_merchant(merchant_id: int, *, limit: int = 50) -> list[dict]:
    """
    Contacts / phones tied to risk events or open support orders (audit list).
    """
    from discount.models import Contact, MerchantRiskEvent, SimpleOrder

    phones: dict[str, dict] = {}
    channel_q = _merchant_channel_filter(merchant_id)

    for ev in (
        MerchantRiskEvent.objects.filter(merchant_id=merchant_id)
        .select_related("channel", "order")
        .order_by("-created_at")[:200]
    ):
        phone = (ev.customer_phone or "").strip()
        if not phone:
            continue
        entry = phones.setdefault(
            phone,
            {
                "phone": phone,
                "last_event_at": ev.created_at,
                "event_types": set(),
                "summaries": [],
                "channel_id": getattr(ev.channel, "id", None),
                "channel_name": getattr(ev.channel, "name", "") if ev.channel else "",
            },
        )
        entry["event_types"].add(ev.event_type)
        if ev.summary and len(entry["summaries"]) < 3:
            entry["summaries"].append(ev.summary[:300])
        if ev.created_at > entry["last_event_at"]:
            entry["last_event_at"] = ev.created_at

    for order in (
        SimpleOrder.objects.filter(channel_q)
        .exclude(support_status="none")
        .order_by("-created_at")[:100]
    ):
        phone = (order.customer_phone or "").strip()
        if not phone:
            continue
        entry = phones.setdefault(
            phone,
            {
                "phone": phone,
                "last_event_at": order.created_at,
                "event_types": set(),
                "summaries": [],
                "channel_id": getattr(order.channel, "id", None),
                "channel_name": getattr(order.channel, "name", "") if order.channel else "",
            },
        )
        entry["event_types"].add("support_order")
        if order.complaint_summary and len(entry["summaries"]) < 3:
            entry["summaries"].append((order.complaint_summary or "")[:300])

    contact_names = {}
    if phones:
        for c in Contact.objects.filter(
            channel__owner_id=merchant_id,
            phone__in=list(phones.keys()),
        ).only("phone", "name", "channel_id"):
            contact_names[c.phone] = (c.name or "").strip()

    out = []
    for phone, data in phones.items():
        data["name"] = contact_names.get(phone, "")
        data["event_types"] = sorted(data["event_types"])
        out.append(data)
    out.sort(key=lambda x: x["last_event_at"], reverse=True)
    return out[:limit]


def get_catalog_summary(merchant_id: int) -> list[dict]:
    from discount.models import Products

    products = Products.objects.filter(admin_id=merchant_id).order_by("-id")[:40]
    rows = []
    for p in products:
        rows.append(
            {
                "id": p.id,
                "name": p.name,
                "price": p.price,
                "currency": p.currency or "MAD",
                "is_digital": bool(getattr(p, "is_digital", False)),
                "sku": getattr(p, "sku", "") or "",
            }
        )
    return rows


def fetch_chat_transcript(
    merchant_id: int,
    customer_phone: str,
    *,
    channel_id: int | None = None,
    limit: int = 80,
) -> dict[str, Any]:
    """Raw WhatsApp messages for founder audit (read-only)."""
    from discount.models import Message, WhatsAppChannel

    phone = (customer_phone or "").strip()
    if not phone:
        return {"success": False, "message": "customer_phone required", "messages": []}

    channels = WhatsAppChannel.objects.filter(owner_id=merchant_id)
    if channel_id:
        channels = channels.filter(pk=channel_id)
    channel = channels.first()
    if not channel:
        return {"success": False, "message": "No channel found for merchant", "messages": []}

    msgs = list(
        Message.objects.filter(
            channel=channel,
            sender=phone,
            is_internal=False,
        )
        .order_by("-timestamp")[:limit]
    )
    msgs.reverse()
    rendered = []
    for m in msgs:
        body = (m.body or "").strip()
        cap = (m.captions or "").strip() if getattr(m, "captions", None) else ""
        text = body or cap
        if not text and m.media_type:
            text = f"[{m.media_type}]"
        rendered.append(
            {
                "role": "Merchant/AI" if m.is_from_me else "Customer",
                "text": text[:8000],
                "timestamp": m.timestamp.isoformat() if m.timestamp else "",
                "media_type": m.media_type or "",
            }
        )
    return {
        "success": True,
        "channel_id": channel.id,
        "channel_name": channel.name,
        "customer_phone": phone,
        "messages": rendered,
    }


def suspend_merchant_account(merchant, *, reason: str = "") -> bool:
    """Kill switch: block dashboard + AI webhook (middleware + webhook guard)."""
    if not merchant:
        return False
    merchant.is_suspended = True
    merchant.suspension_reason = (reason or "Suspended by Founder HQ risk review.")[:2000]
    merchant.save(update_fields=["is_suspended", "suspension_reason"])
    logger.warning(
        "Founder HQ kill-switch: merchant_id=%s suspended. reason=%s",
        merchant.id,
        merchant.suspension_reason[:120],
    )
    return True


def _founder_alert_recipients() -> list[str]:
    emails = list(
        getattr(settings, "FOUNDER_RISK_ALERT_EMAILS", None)
        or getattr(settings, "ADMINS", [])
        or []
    )
    if emails:
        flat = []
        for item in emails:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                flat.append(item[1])
            elif isinstance(item, str):
                flat.append(item)
        return [e for e in flat if e]
    from discount.models import CustomUser

    return list(
        CustomUser.objects.filter(is_superuser=True, is_active=True)
        .exclude(email="")
        .values_list("email", flat=True)[:5]
    )


def maybe_send_founder_risk_alert(merchant) -> bool:
    """Email superadmins when 24h complaints exceed threshold (once per merchant per day)."""
    from discount.models import FounderRiskAlert

    metrics = compute_merchant_metrics(merchant.id)
    if not metrics["is_red_flag"]:
        return False

    today = timezone.localdate()
    alert, created = FounderRiskAlert.objects.get_or_create(
        merchant=merchant,
        alert_date=today,
        defaults={"complaints_count": metrics["complaints_24h"]},
    )
    if not created:
        return False

    recipients = _founder_alert_recipients()
    if not recipients:
        logger.warning("Founder risk alert: no recipient emails configured")
        return False

    label = (
        getattr(merchant, "user_name", None)
        or getattr(merchant, "username", None)
        or merchant.email
    )
    subject = f"🚩 Founder HQ: High risk tenant — {label}"
    body = (
        f"Merchant: {label} (id={merchant.id}, {merchant.email})\n"
        f"Complaints (last 24h): {metrics['complaints_24h']} (threshold: {COMPLAINT_THRESHOLD_24H})\n"
        f"Total complaints (all time): {metrics['total_complaints']}\n"
        f"First-time delivery success rate: {metrics['first_time_success_rate']}%\n"
        f"Pending orders: {metrics['pending_orders_count']}\n\n"
        f"Review: {getattr(settings, 'SITE_URL', '')}/founder-hq/risk/audit/{merchant.id}/\n"
    )
    try:
        send_mail(
            subject,
            body,
            getattr(settings, "DEFAULT_FROM_EMAIL", None),
            recipients,
            fail_silently=False,
        )
        logger.info(
            "Founder risk alert sent for merchant_id=%s to %s",
            merchant.id,
            recipients,
        )
        return True
    except Exception as exc:
        logger.exception("Founder risk alert email failed: %s", exc)
        FounderRiskAlert.objects.filter(pk=alert.pk).delete()
        return False
