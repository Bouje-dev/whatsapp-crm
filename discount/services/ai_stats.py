"""
AI Sales Agent analytics: KPIs, time saved, conversion rate, top products.
Uses Django aggregation for performance. Exportable for Google Sheets / Zapier.
"""
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from discount.models import Message, SimpleOrder, AIUsageLog, FollowUpSentLog


# Assume every AI message saves 2 minutes of human agent time
MINUTES_SAVED_PER_AI_MESSAGE = 2


def _channel_qs(channel):
    if not channel:
        return Message.objects.none()
    return Message.objects.filter(channel=channel)


def get_ai_analytics(channel, date_from, date_to):
    """
    Compute AI Sales Agent KPIs for a channel and date range.

    Returns:
        dict with:
        - total_ai_conversations: distinct senders that received at least one AI (is_from_me) message
        - total_ai_messages: count of messages sent by AI (is_from_me=True)
        - total_ai_orders: SimpleOrder with created_by_ai=True in range
        - total_manual_orders: SimpleOrder with created_by_ai=False in range (or null)
        - ai_conversion_rate: (total_ai_orders / total_ai_conversations) * 100 if conversations > 0 else 0
        - hours_saved: total_ai_messages * 2 / 60
        - hours_saved_label: "Xh Ym" for display
        - top_products: list of { product_name, count } for AI orders, sorted by count desc
        - api_characters_used: sum of characters_used from AIUsageLog in range
        - api_credits_remaining: optional (e.g. from plan); None if not tracked
        - chart_ai_vs_manual: list of { date, ai_orders, manual_orders } for last 30 days
    """
    if not channel:
        return _empty_analytics()

    base_msg = _channel_qs(channel).filter(
        timestamp__gte=date_from,
        timestamp__lte=date_to,
    )
    ai_messages = base_msg.filter(is_from_me=True)
    total_ai_messages = ai_messages.count()

    # Unique conversations: senders that have at least one AI reply in range
    senders_with_ai_reply = ai_messages.values_list("sender", flat=True).distinct()
    total_ai_conversations = len(list(senders_with_ai_reply))

    orders_base = SimpleOrder.objects.filter(
        channel=channel,
        created_at__gte=date_from,
        created_at__lte=date_to,
    )
    total_ai_orders = orders_base.filter(created_by_ai=True).count()
    total_manual_orders = orders_base.filter(created_by_ai=False).count()

    if total_ai_conversations > 0:
        ai_conversion_rate = round((total_ai_orders / total_ai_conversations) * 100, 1)
    else:
        ai_conversion_rate = Decimal("0")

    minutes_saved = total_ai_messages * MINUTES_SAVED_PER_AI_MESSAGE
    hours_saved = minutes_saved / 60
    h = int(hours_saved)
    m = int((hours_saved - h) * 60)
    if m > 0:
        hours_saved_label = f"{h}h {m}m"
    else:
        hours_saved_label = f"{h}h"

    # Top products by AI orders (product_name)
    top_products = (
        orders_base.filter(created_by_ai=True)
        .values("product_name")
        .annotate(count=Count("id"))
        .order_by("-count")[:10]
    )
    top_products = [{"product_name": (x["product_name"] or "—")[:80], "count": x["count"]} for x in top_products]

    # API usage (characters)
    api_logs = AIUsageLog.objects.filter(
        channel=channel,
        date__gte=date_from.date(),
        date__lte=date_to.date(),
    )
    api_characters_used = api_logs.aggregate(s=Sum("characters_used"))["s"] or 0

    # Chart: last 30 days AI vs Manual orders per day
    chart_end = date_to
    chart_start = chart_end - timedelta(days=30)
    chart_orders = SimpleOrder.objects.filter(
        channel=channel,
        created_at__gte=chart_start,
        created_at__lte=chart_end,
    )
    daily = (
        chart_orders.values(day=TruncDate("created_at"))
        .annotate(
            ai_orders=Count("id", filter=Q(created_by_ai=True)),
            manual_orders=Count("id", filter=Q(created_by_ai=False)),
        )
    )
    day_map = {d["day"]: {"date": str(d["day"]), "ai_orders": d["ai_orders"], "manual_orders": d["manual_orders"]} for d in daily}
    chart_ai_vs_manual = []
    for i in range(31):
        d = chart_end.date() - timedelta(days=i)
        chart_ai_vs_manual.append(day_map.get(d, {"date": str(d), "ai_orders": 0, "manual_orders": 0}))
    chart_ai_vs_manual.reverse()

    # Follow-up node: count of sent follow-ups in range (for Analytics dashboard)
    follow_up_sent_count = FollowUpSentLog.objects.filter(
        channel=channel,
        sent_at__gte=date_from,
        sent_at__lte=date_to,
    ).count()

    return {
        "total_ai_conversations": total_ai_conversations,
        "total_ai_messages": total_ai_messages,
        "total_ai_orders": total_ai_orders,
        "total_manual_orders": total_manual_orders,
        "ai_conversion_rate": float(ai_conversion_rate),
        "hours_saved": round(hours_saved, 2),
        "hours_saved_label": hours_saved_label,
        "top_products": top_products,
        "api_characters_used": api_characters_used,
        "api_credits_remaining": None,
        "chart_ai_vs_manual": chart_ai_vs_manual,
        "follow_up_sent_count": follow_up_sent_count,
    }


def _empty_analytics():
    return {
        "total_ai_conversations": 0,
        "total_ai_messages": 0,
        "total_ai_orders": 0,
        "total_manual_orders": 0,
        "ai_conversion_rate": 0.0,
        "hours_saved": 0.0,
        "hours_saved_label": "0h",
        "top_products": [],
        "api_characters_used": 0,
        "api_credits_remaining": None,
        "chart_ai_vs_manual": [],
        "follow_up_sent_count": 0,
    }


def sync_to_external_platforms(order_data):
    """
    Placeholder for future Google Sheets, Zapier, or other integrations.
    Call this after an order is created (e.g. from save_order_from_ai) to push data.

    Args:
        order_data: dict with order fields (order_id, customer_name, customer_phone, product_name, price, etc.)
    """
    # TODO: Google Sheets append row, Zapier webhook, etc.
    pass
