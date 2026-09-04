"""
Post-sale support helpers for completed digital orders.

Used by the AI agent (complaint intake + proof flagging), the WhatsApp
router (media detection), and merchant dashboard APIs (replacement approve).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Active support states where the AI post-sale banner should remain injected.
_AI_ACTIVE_SUPPORT_STATUSES = frozenset({
    'none',
    'awaiting_proof',
    'under_review',
})

# Merchant dashboard: show the review card only when proof is queued.
_DASHBOARD_REVIEW_STATUS = 'under_review'


def _digits_only_phone(value: str) -> str:
    return ''.join(c for c in (value or '') if c.isdigit())


# Substrings that suggest the customer is asking about a PAST order (support), not a new sale.
_SUPPORT_INTENT_FRAGMENTS = (
    'ما خدامش', 'ما كيخدمش', 'ما خدام', 'ماشي خدام', 'ماشي شغال',
    'ما اشتغل', 'ما خدمنيش', 'password', 'mot de passe', 'compte bloqué',
    'not working', "doesn't work", 'broken', 'refund', 'replacement',
    'استرجاع', 'تعويض', 'استبدال', 'ما وصلني', 'ما وصلاتش', 'مشكل فالطلب',
    'الطلبية السابقة', 'المنتج اللي شريت', 'الحساب ما', 'كلمة السر',
    'screenshot', 'capture', 'صورة للمشكل', 'الكود ما', 'الرخصة ما',
)


def _body_looks_like_post_sale_support(body: str) -> bool:
    if not body or not str(body).strip():
        return False
    low = str(body).strip().lower()
    return any(frag in low for frag in _SUPPORT_INTENT_FRAGMENTS)


def has_active_sales_flow(channel, phone_param: str, resolved_sender: str, conversation_state: str = '') -> bool:
    """
    True when the customer is in an active NEW purchase / negotiation flow.
    Post-sale prompts must NOT inject in this case (even if they have old completed orders).
    """
    state = (conversation_state or '').strip().upper()
    if state == 'AWAITING_PAYMENT_RECEIPT':
        return True
    if state == 'POST_SALE_SUPPORT':
        return False
    phone = (resolved_sender or phone_param or '').strip()
    if not channel or not phone:
        return False
    try:
        from discount.models import ChatSession

        session = (
            ChatSession.objects
            .filter(
                channel=channel,
                customer_phone=phone,
                is_expired=False,
                is_completed=False,
            )
            .select_related('active_node', 'active_product')
            .first()
        )
        if session and (getattr(session, 'active_node_id', None) or getattr(session, 'active_product_id', None)):
            return True
    except Exception as exc:
        logger.debug('has_active_sales_flow ChatSession lookup: %s', exc)
    try:
        from discount.whatssapAPI.session_state import get_active_node_fast

        if get_active_node_fast(channel, phone):
            return True
    except Exception as exc:
        logger.debug('has_active_sales_flow cache lookup: %s', exc)
    return False


def should_inject_post_sale_support(
    channel,
    phone_param: str,
    resolved_sender: str,
    conversation_state: str = '',
    incoming_body: str = '',
) -> bool:
    """
    Post-sale banner when the sale is done: FSM POST_SALE_SUPPORT, a recent
    order on this chat, or a completed digital order (legacy path).
    Blocked during payment-wait and during an active NEW purchase.
    """
    state = (conversation_state or '').strip().upper()
    if state == 'AWAITING_PAYMENT_RECEIPT':
        return False
    if state == 'POST_SALE_SUPPORT':
        return True
    if has_active_sales_flow(channel, phone_param, resolved_sender, conversation_state):
        return False
    if latest_care_order(channel, phone_param, resolved_sender) is not None:
        return True
    return latest_completed_digital_order(channel, phone_param, resolved_sender) is not None


def lookup_simple_order_for_channel(channel, order_id: str, customer_phone: str = ''):
    """Resolve an order scoped to channel + optional customer phone match."""
    from discount.models import SimpleOrder

    order_id = (order_id or '').strip()
    if not order_id or not channel:
        return None
    qs = SimpleOrder.objects.filter(
        order_id=order_id,
        channel=channel,
        is_digital=True,
    ).select_related('product')
    order = qs.first()
    if not order:
        return None
    if customer_phone:
        cand = (customer_phone or '').strip()
        if cand and order.customer_phone != cand:
            dq_order = _digits_only_phone(order.customer_phone or '')
            dq_cand = _digits_only_phone(cand)
            if not dq_order or not dq_cand or not (
                dq_order.endswith(dq_cand[-9:]) or dq_cand.endswith(dq_order[-9:])
            ):
                return None
    return order


_CANCELLED_ORDER_STATUSES = frozenset({
    'cancelled', 'canceled', 'Cancelled', 'Canceled', 'CANCELLED', 'CANCELED',
})
_CARE_ORDER_LOOKBACK_DAYS = 45


def _phone_candidates(phone_param: str, resolved_sender: str) -> list[str]:
    candidates = []
    if resolved_sender:
        candidates.append(resolved_sender)
    if phone_param and phone_param not in candidates:
        candidates.append(phone_param)
    return candidates


def latest_care_order(channel, phone_param: str, resolved_sender: str):
    """
    Latest non-cancelled order for this WhatsApp chat (physical or digital).
    Used to switch the AI into customer-support after the sale.
    """
    from datetime import timedelta

    from django.utils import timezone

    from discount.models import SimpleOrder

    if not channel:
        return None
    since = timezone.now() - timedelta(days=_CARE_ORDER_LOOKBACK_DAYS)
    base_qs = (
        SimpleOrder.objects
        .filter(channel=channel, created_at__gte=since)
        .exclude(status__in=_CANCELLED_ORDER_STATUSES)
        .select_related('product')
        .order_by('-created_at')
    )
    for cand in _phone_candidates(phone_param, resolved_sender):
        order = base_qs.filter(customer_phone=cand).first()
        if order:
            return order
    dq = _digits_only_phone(phone_param or resolved_sender or '')
    if not dq or len(dq) < 9:
        return None
    tail = dq[-9:]
    for order in base_qs.iterator(chunk_size=40):
        if (_digits_only_phone(order.customer_phone or '') or '').endswith(tail):
            return order
    return None


def latest_completed_digital_order(channel, phone_param: str, resolved_sender: str):
    """
    Latest completed digital order for this chat that is still eligible
    for post-sale AI support (not resolved/rejected).
    """
    from discount.models import SimpleOrder

    if not channel:
        return None
    candidates = []
    if resolved_sender:
        candidates.append(resolved_sender)
    if phone_param and phone_param not in candidates:
        candidates.append(phone_param)

    base_qs = (
        SimpleOrder.objects
        .filter(
            channel=channel,
            is_digital=True,
            status='completed',
            support_status__in=_AI_ACTIVE_SUPPORT_STATUSES,
        )
        .select_related('product')
        .order_by('-created_at')
    )

    for cand in candidates:
        order = base_qs.filter(customer_phone=cand).first()
        if order:
            return order

    dq = _digits_only_phone(phone_param or resolved_sender or '')
    if not dq or len(dq) < 9:
        return None
    tail = dq[-9:]
    for order in base_qs.iterator(chunk_size=30):
        if (_digits_only_phone(order.customer_phone or '') or '').endswith(tail):
            return order
    return None


def active_support_review_order(channel, phone_param: str, resolved_sender: str):
    """Order with support_status=under_review for the dashboard review card."""
    from discount.models import SimpleOrder

    if not channel:
        return None
    candidates = []
    if resolved_sender:
        candidates.append(resolved_sender)
    if phone_param and phone_param not in candidates:
        candidates.append(phone_param)

    base_qs = (
        SimpleOrder.objects
        .filter(
            channel=channel,
            is_digital=True,
            status='completed',
            support_status=_DASHBOARD_REVIEW_STATUS,
        )
        .select_related('product')
        .order_by('-created_at')
    )

    for cand in candidates:
        order = base_qs.filter(customer_phone=cand).first()
        if order:
            return order

    dq = _digits_only_phone(phone_param or resolved_sender or '')
    if not dq or len(dq) < 9:
        return None
    tail = dq[-9:]
    for order in base_qs.iterator(chunk_size=30):
        if (_digits_only_phone(order.customer_phone or '') or '').endswith(tail):
            return order
    return None


def serialize_support_review_order(order) -> Optional[dict[str, Any]]:
    if not order:
        return None
    try:
        price = float(order.price) if order.price is not None else 0.0
    except (TypeError, ValueError):
        price = 0.0
    return {
        'id': order.order_id,
        'status': order.status,
        'support_status': getattr(order, 'support_status', None) or 'none',
        'complaint_summary': (getattr(order, 'complaint_summary', None) or '').strip(),
        'total_price': price,
        'currency': order.currency or 'MAD',
        'product_name': (order.product_name or '').strip(),
        'customer_name': (order.customer_name or '').strip(),
        'customer_phone': (order.customer_phone or '').strip(),
    }


def customer_has_post_sale_digital_order(
    channel, phone_param: str, resolved_sender: str,
) -> bool:
    """True when the customer has a completed digital order eligible for post-sale AI."""
    return latest_completed_digital_order(channel, phone_param, resolved_sender) is not None


def get_post_sale_support_context(
    channel,
    phone_param: str,
    resolved_sender: str,
    conversation_state: str = '',
    incoming_body: str = '',
) -> Optional[dict[str, Any]]:
    """
    Context dict for AI prompt injection after the sale (support team persona).
    """
    if not should_inject_post_sale_support(
        channel, phone_param, resolved_sender, conversation_state, incoming_body,
    ):
        return None
    digital = latest_completed_digital_order(channel, phone_param, resolved_sender)
    order = digital or latest_care_order(channel, phone_param, resolved_sender)
    if not order:
        return None
    is_digital = bool(getattr(order, 'is_digital', False))
    mode = 'digital_tech' if digital is not None else 'customer_care'
    return {
        'order_id': order.order_id,
        'product_name': (order.product_name or '').strip() or 'your product',
        'support_status': getattr(order, 'support_status', None) or 'none',
        'complaint_summary': (getattr(order, 'complaint_summary', None) or '').strip(),
        'is_digital': is_digital,
        'mode': mode,
    }


def _resolve_support_order(channel, customer_phone: str, order_id: str):
    """Lookup by order_id or fall back to latest completed digital order."""
    order = lookup_simple_order_for_channel(channel, order_id, customer_phone)
    if order:
        return order
    return latest_completed_digital_order(channel, customer_phone, customer_phone)


def register_support_complaint(channel, customer_phone: str, order_id: str, complaint_summary: str) -> dict:
    """AI tool: customer reported an issue — ask for screenshot next."""
    order = _resolve_support_order(channel, customer_phone, order_id)
    if not order:
        return {'success': False, 'message': 'Order not found for this customer.'}
    if order.status != 'completed':
        return {'success': False, 'message': 'Support is only available after delivery is completed.'}
    if order.support_status in ('under_review', 'resolved', 'rejected'):
        return {
            'success': False,
            'message': f'Support case already in status: {order.support_status}.',
        }
    summary = (complaint_summary or '').strip()[:2000]
    if not summary:
        return {'success': False, 'message': 'complaint_summary is required.'}
    order.support_status = 'awaiting_proof'
    order.complaint_summary = summary
    order.save(update_fields=['support_status', 'complaint_summary'])
    try:
        from discount.models import MerchantRiskEvent
        from discount.services.tenant_risk import record_event_for_channel
        record_event_for_channel(
            channel,
            MerchantRiskEvent.EVENT_SUPPORT_COMPLAINT,
            order=order,
            customer_phone=customer_phone,
            summary=summary,
            metadata={'order_id': order.order_id, 'source': 'register_support_complaint'},
        )
    except Exception as _risk_err:
        logger.warning('register_support_complaint risk log failed: %s', _risk_err)
    logger.info(
        'register_support_complaint: order=%s status→awaiting_proof',
        order.order_id,
    )
    return {
        'success': True,
        'support_status': 'awaiting_proof',
        'message': 'Complaint registered. Ask the customer for a screenshot of the error.',
    }


def flag_order_for_review(channel, customer_phone: str, order_id: str, complaint_summary: str) -> dict:
    """AI tool (+ backend fallback): visual proof received → merchant review queue."""
    order = _resolve_support_order(channel, customer_phone, order_id)
    if not order:
        return {'success': False, 'message': 'Order not found for this customer.'}
    if order.status != 'completed':
        return {'success': False, 'message': 'Support is only available after delivery is completed.'}
    if order.support_status in ('resolved', 'rejected'):
        return {
            'success': False,
            'message': f'Support case already closed: {order.support_status}.',
        }
    summary = (complaint_summary or '').strip()[:2000]
    if not summary:
        summary = (order.complaint_summary or '').strip() or 'Customer submitted visual proof.'
    order.support_status = 'under_review'
    order.complaint_summary = summary
    order.save(update_fields=['support_status', 'complaint_summary'])
    try:
        from discount.models import MerchantRiskEvent
        from discount.services.tenant_risk import record_event_for_channel
        record_event_for_channel(
            channel,
            MerchantRiskEvent.EVENT_FLAG_REVIEW,
            order=order,
            customer_phone=customer_phone,
            summary=summary,
            metadata={'order_id': order.order_id, 'source': 'flag_order_for_review'},
        )
    except Exception as _risk_err:
        logger.warning('flag_order_for_review risk log failed: %s', _risk_err)
    logger.info(
        'flag_order_for_review: order=%s status→under_review',
        order.order_id,
    )
    return {
        'success': True,
        'support_status': 'under_review',
        'order_id': order.order_id,
        'message': (
            '[SYSTEM: Order successfully flagged. Tell the customer politely that the tech '
            'team is reviewing their screenshot and will provide a replacement soon.]'
        ),
    }
