"""
Click-to-WhatsApp (CTWA) ads attribution and campaign conversion analytics.

Meta sends a ``referral`` object on the first Cloud API webhook after a
Facebook/Instagram Click-to-WhatsApp ad. We persist source_id / source_url /
headline on the customer's checkout session, copy them onto the order at
checkout, and expose ``calculate_campaign_performance`` to the AI Copilot.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal
from typing import Any, Optional

from django.db.models import Count, Max, Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

logger = logging.getLogger(__name__)

CONFIRMED_ORDER_EXCLUDED_STATUSES = ("cancelled", "returned")
_CLICK_DEBOUNCE = timedelta(hours=24)
DIRECT_SOURCE_ID = "direct"
DIRECT_HEADLINE = "Direct"


def _nonempty(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def parse_whatsapp_referral(referral: Any) -> dict:
    """
    Extract CTWA fields from a WhatsApp Cloud API message ``referral`` object.

    Returns a dict with ad_source_id, ad_source_url, ad_headline (possibly empty).
    """
    if not isinstance(referral, dict):
        return {"ad_source_id": "", "ad_source_url": "", "ad_headline": ""}
    source_id = _nonempty(referral.get("source_id"))[:128]
    source_url = _nonempty(referral.get("source_url"))[:500]
    headline = _nonempty(referral.get("headline"))[:255]
    return {
        "ad_source_id": source_id,
        "ad_source_url": source_url,
        "ad_headline": headline,
    }


def apply_ctwa_referral_to_checkout(channel, customer_phone: str, referral: Any):
    """
    Save CTWA referral fields onto the current WhatsAppCheckoutState and
    record a WhatsAppAdClick (debounced per phone + ad for 24h).

    Called when the inbound webhook contains a ``referral`` object.
    """
    from discount.models import WhatsAppAdClick
    from discount.services.checkout_state import get_or_create_checkout_state

    parsed = parse_whatsapp_referral(referral)
    if not parsed["ad_source_id"] and not parsed["ad_headline"] and not parsed["ad_source_url"]:
        return None
    if not channel or not customer_phone:
        return None

    phone = str(customer_phone).strip()
    state = get_or_create_checkout_state(channel, phone)
    if state is None:
        return None

    now = timezone.now()
    state.ad_source_id = parsed["ad_source_id"]
    state.ad_source_url = parsed["ad_source_url"]
    state.ad_headline = parsed["ad_headline"]
    state.ad_attributed_at = now
    state.save(
        update_fields=[
            "ad_source_id",
            "ad_source_url",
            "ad_headline",
            "ad_attributed_at",
            "updated_at",
        ]
    )

    if parsed["ad_source_id"]:
        recent = (
            WhatsAppAdClick.objects.filter(
                channel=channel,
                customer_phone=phone,
                ad_source_id=parsed["ad_source_id"],
                created_at__gte=now - _CLICK_DEBOUNCE,
            )
            .order_by("-created_at")
            .first()
        )
        if recent is None:
            try:
                WhatsAppAdClick.objects.create(
                    channel=channel,
                    customer_phone=phone,
                    ad_source_id=parsed["ad_source_id"],
                    ad_source_url=parsed["ad_source_url"],
                    ad_headline=parsed["ad_headline"],
                )
            except Exception as exc:
                logger.warning("WhatsAppAdClick create failed: %s", exc)

    logger.info(
        "CTWA referral saved channel=%s phone=%s source_id=%s headline=%r",
        getattr(channel, "id", None),
        phone,
        parsed["ad_source_id"] or "—",
        (parsed["ad_headline"] or "")[:80],
    )
    return state


def apply_direct_source_if_unattributed(channel, customer_phone: str):
    """
    First inbound without a Meta CTWA referral is organic traffic.
    Does not overwrite an existing ad source_id.
    """
    from discount.models import WhatsAppAdClick
    from discount.services.checkout_state import get_or_create_checkout_state

    if not channel or not customer_phone:
        return None
    phone = str(customer_phone).strip()
    try:
        state = get_or_create_checkout_state(channel, phone)
    except Exception as exc:
        logger.debug("apply_direct_source_if_unattributed: %s", exc)
        return None
    if state is None:
        return None

    existing = _nonempty(getattr(state, "ad_source_id", ""))
    if existing and existing != DIRECT_SOURCE_ID:
        return state

    now = timezone.now()
    if existing != DIRECT_SOURCE_ID:
        state.ad_source_id = DIRECT_SOURCE_ID
        state.ad_source_url = ""
        state.ad_headline = DIRECT_HEADLINE
        state.ad_attributed_at = now
        try:
            state.save(
                update_fields=[
                    "ad_source_id",
                    "ad_source_url",
                    "ad_headline",
                    "ad_attributed_at",
                    "updated_at",
                ]
            )
        except Exception as exc:
            logger.warning("direct source save failed: %s", exc)
            return state

    recent = (
        WhatsAppAdClick.objects.filter(
            channel=channel,
            customer_phone=phone,
            ad_source_id=DIRECT_SOURCE_ID,
            created_at__gte=now - _CLICK_DEBOUNCE,
        )
        .order_by("-created_at")
        .first()
    )
    if recent is None:
        try:
            WhatsAppAdClick.objects.create(
                channel=channel,
                customer_phone=phone,
                ad_source_id=DIRECT_SOURCE_ID,
                ad_source_url="",
                ad_headline=DIRECT_HEADLINE,
            )
        except Exception as exc:
            logger.warning("WhatsAppAdClick direct create failed: %s", exc)
    return state


def attribution_kwargs_for_customer(channel, customer_phone: str) -> dict:
    """Return SimpleOrder field kwargs copied from the current checkout state."""
    from discount.services.checkout_state import get_or_create_checkout_state

    if not channel or not customer_phone:
        return {}
    try:
        state = get_or_create_checkout_state(channel, str(customer_phone).strip())
    except Exception as exc:
        logger.debug("attribution_kwargs_for_customer: %s", exc)
        return {}
    if not state:
        return {
            "ad_source_id": DIRECT_SOURCE_ID,
            "ad_source_url": "",
            "ad_headline": DIRECT_HEADLINE,
        }
    source_id = _nonempty(getattr(state, "ad_source_id", ""))[:128]
    source_url = _nonempty(getattr(state, "ad_source_url", ""))[:500]
    headline = _nonempty(getattr(state, "ad_headline", ""))[:255]
    if not source_id:
        apply_direct_source_if_unattributed(channel, customer_phone)
        return {
            "ad_source_id": DIRECT_SOURCE_ID,
            "ad_source_url": "",
            "ad_headline": DIRECT_HEADLINE,
        }
    return {
        "ad_source_id": source_id,
        "ad_source_url": source_url,
        "ad_headline": headline or (DIRECT_HEADLINE if source_id == DIRECT_SOURCE_ID else ""),
    }


def _rate_pct(numerator: int, denominator: int) -> float:
    if not denominator:
        return 0.0
    return round((float(numerator) / float(denominator)) * 100.0, 2)


def calculate_campaign_performance(days: int, channel_id: Optional[int] = None) -> dict:
    """
    Group CTWA sessions and confirmed orders by ad_source_id.

    Returns a JSON-serializable summary of chats initiated vs orders confirmed
    and conversion rate per ad over the last ``days`` days.
    """
    from discount.models import Message, SimpleOrder, WhatsAppAdClick, WhatsAppCheckoutState

    try:
        window = max(1, int(days))
    except (TypeError, ValueError):
        window = 7

    now = timezone.now()
    cutoff = now - timedelta(days=window)

    clicks = WhatsAppAdClick.objects.filter(created_at__gte=cutoff)
    orders = SimpleOrder.objects.filter(created_at__gte=cutoff).exclude(
        status__in=CONFIRMED_ORDER_EXCLUDED_STATUSES
    )
    states = WhatsAppCheckoutState.objects.filter(ad_source_id__gt="")

    if channel_id is not None:
        clicks = clicks.filter(channel_id=channel_id)
        orders = orders.filter(channel_id=channel_id)
        states = states.filter(channel_id=channel_id)

    click_rows = list(
        clicks.filter(ad_source_id__gt="")
        .values("ad_source_id")
        .annotate(
            chats_initiated=Count("customer_phone", distinct=True),
            clicks=Count("id"),
            last_headline=Max("ad_headline"),
            last_source_url=Max("ad_source_url"),
        )
    )

    # Fallback: checkout states attributed in-window when no click rows exist yet
    # (e.g. data written before WhatsAppAdClick was introduced).
    state_rows = list(
        states.filter(ad_attributed_at__gte=cutoff)
        .values("ad_source_id")
        .annotate(
            chats_initiated=Count("id"),
            last_headline=Max("ad_headline"),
            last_source_url=Max("ad_source_url"),
        )
    )

    order_rows = list(
        orders.values("ad_source_id")
        .annotate(
            orders_confirmed=Count("id"),
            revenue=Coalesce(Sum("price"), Decimal("0")),
            last_headline=Max("ad_headline"),
            last_source_url=Max("ad_source_url"),
            last_currency=Max("currency"),
        )
    )

    by_id: dict[str, dict] = {}

    def _ensure(source_id: str) -> dict:
        row = by_id.get(source_id)
        if row is None:
            row = {
                "ad_source_id": source_id,
                "ad_headline": "",
                "ad_source_url": "",
                "chats_initiated": 0,
                "clicks": 0,
                "orders_confirmed": 0,
                "revenue": 0.0,
                "currency": "",
                "conversion_rate_pct": 0.0,
            }
            by_id[source_id] = row
        return row

    def _norm_sid(source_id) -> str:
        sid = _nonempty(source_id)
        return sid if sid else DIRECT_SOURCE_ID

    click_map = {_norm_sid(r["ad_source_id"]): r for r in click_rows if _norm_sid(r.get("ad_source_id"))}
    if click_map:
        for source_id, r in click_map.items():
            row = _ensure(source_id)
            row["chats_initiated"] = int(r.get("chats_initiated") or 0)
            row["clicks"] = int(r.get("clicks") or 0)
            row["ad_headline"] = _nonempty(r.get("last_headline")) or (
                DIRECT_HEADLINE if source_id == DIRECT_SOURCE_ID else ""
            )
            row["ad_source_url"] = _nonempty(r.get("last_source_url"))
    else:
        for r in state_rows:
            source_id = _norm_sid(r.get("ad_source_id"))
            row = _ensure(source_id)
            row["chats_initiated"] = int(r.get("chats_initiated") or 0)
            row["clicks"] = row["chats_initiated"]
            row["ad_headline"] = _nonempty(r.get("last_headline")) or (
                DIRECT_HEADLINE if source_id == DIRECT_SOURCE_ID else ""
            )
            row["ad_source_url"] = _nonempty(r.get("last_source_url"))

    for r in order_rows:
        source_id = _norm_sid(r.get("ad_source_id"))
        row = _ensure(source_id)
        row["orders_confirmed"] += int(r.get("orders_confirmed") or 0)
        try:
            row["revenue"] = round(float(row["revenue"]) + float(r.get("revenue") or 0), 2)
        except (TypeError, ValueError):
            pass
        if not row["ad_headline"]:
            row["ad_headline"] = _nonempty(r.get("last_headline")) or (
                DIRECT_HEADLINE if source_id == DIRECT_SOURCE_ID else ""
            )
        if not row["ad_source_url"]:
            row["ad_source_url"] = _nonempty(r.get("last_source_url"))
        row["currency"] = _nonempty(r.get("last_currency")) or row["currency"]

    inbound = Message.objects.filter(
        timestamp__gte=cutoff,
        timestamp__lte=now,
        is_from_me=False,
        is_internal=False,
    ).exclude(Q(sender__isnull=True) | Q(sender=""))
    if channel_id is not None:
        inbound = inbound.filter(channel_id=channel_id)
    inbound_phones = set(inbound.values_list("sender", flat=True))
    ctwa_phones = set(
        clicks.exclude(Q(ad_source_id="") | Q(ad_source_id=DIRECT_SOURCE_ID))
        .values_list("customer_phone", flat=True)
    )
    direct_chats = len(inbound_phones - ctwa_phones)
    if direct_chats or DIRECT_SOURCE_ID in by_id:
        drow = _ensure(DIRECT_SOURCE_ID)
        drow["chats_initiated"] = direct_chats
        drow["ad_headline"] = drow["ad_headline"] or DIRECT_HEADLINE

    for row in by_id.values():
        if row["ad_source_id"] == DIRECT_SOURCE_ID:
            row["ad_headline"] = row["ad_headline"] or DIRECT_HEADLINE
        row["conversion_rate_pct"] = _rate_pct(
            row["orders_confirmed"], row["chats_initiated"]
        )

    campaigns = sorted(
        by_id.values(),
        key=lambda x: (x["conversion_rate_pct"], x["orders_confirmed"], x["revenue"]),
        reverse=True,
    )

    total_chats = sum(c["chats_initiated"] for c in campaigns)
    total_orders = sum(c["orders_confirmed"] for c in campaigns)
    total_revenue = round(sum(c["revenue"] for c in campaigns), 2)
    currency = next((c["currency"] for c in campaigns if c.get("currency")), "")

    ads_only = [c for c in campaigns if c.get("ad_source_id") != DIRECT_SOURCE_ID]
    top = ads_only[0] if ads_only else None

    return {
        "success": True,
        "days": window,
        "period_start": cutoff.isoformat(),
        "period_end": now.isoformat(),
        "channel_id": channel_id,
        "campaigns": campaigns,
        "totals": {
            "chats_initiated": total_chats,
            "orders_confirmed": total_orders,
            "conversion_rate_pct": _rate_pct(total_orders, total_chats),
            "revenue": total_revenue,
            "currency": currency,
        },
        "top_converting_ad": (
            {
                "ad_source_id": top["ad_source_id"],
                "ad_headline": top["ad_headline"],
                "ad_source_url": top["ad_source_url"],
                "chats_initiated": top["chats_initiated"],
                "orders_confirmed": top["orders_confirmed"],
                "conversion_rate_pct": top["conversion_rate_pct"],
                "revenue": top["revenue"],
                "currency": top["currency"],
            }
            if top
            else None
        ),
    }
