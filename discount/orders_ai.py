"""
Save order data extracted by AI (e.g. from GPT function calling or [ORDER_DATA: ...] tag).
Used by the AI voice / sales agent auto-reply flow.
"""
import json
import logging
import re
import uuid
from decimal import Decimal
from django.utils import timezone

from discount.models import SimpleOrder, Products, WhatsAppChannel, CustomUser

logger = logging.getLogger(__name__)


def get_or_create_ai_agent_user(owner, agent_name=None):
    """
    Get or create a Virtual Team Member (CustomUser with is_bot=True) for the given merchant.
    Used so orders created by the AI are attributed to this bot user instead of the account owner.
    """
    if not owner:
        return None
    agent_name = (agent_name or "AI Agent").strip() or "AI Agent"
    # Slug for uniqueness: first word or sanitized agent_name (e.g. "Simo - AI Closer" -> "simo")
    slug = "".join(c for c in agent_name.split()[0].lower() if c.isalnum()) if agent_name else "default"
    if not slug:
        slug = "agent"
    slug = slug[:30]
    owner_id = getattr(owner, "id", None) or getattr(owner, "pk", None)
    if not owner_id:
        return None
    username = f"bot_agent_{owner_id}_{slug}"
    email = f"bot+{owner_id}+{slug}@internal.bot"
    try:
        bot = CustomUser.objects.filter(
            bot_owner_id=owner_id,
            is_bot=True,
            agent_role=agent_name,
        ).first()
        if bot:
            return bot
        # Ensure unique username/email in case of race
        if CustomUser.objects.filter(username=username).exists():
            bot = CustomUser.objects.filter(bot_owner_id=owner_id, is_bot=True).first()
            return bot
        bot = CustomUser.objects.create(
            username=username,
            email=email,
            is_bot=True,
            agent_role=agent_name,
            bot_owner_id=owner_id,
            is_active=True,
        )
        bot.set_unusable_password()
        bot.save()
        logger.info("Created virtual team member (bot) for owner %s: %s", owner_id, agent_name)
        return bot
    except Exception as e:
        logger.warning("get_or_create_ai_agent_user failed: %s; falling back to owner", e)
        return owner

# Robust match for [ORDER_DATA: {...}] — extract JSON by brace-matching so commas/quotes inside values are safe
ORDER_DATA_TAG_PREFIX_RE = re.compile(r"\[ORDER_DATA:\s*(\{)", re.IGNORECASE)


def _extract_order_data_json(reply_text):
    """
    Find [ORDER_DATA: {...}] and return (start, end, json_str) for the first valid brace-balanced block.
    Returns (None, None, None) if not found or invalid.
    """
    if not reply_text or not isinstance(reply_text, str):
        return (None, None, None)
    m = ORDER_DATA_TAG_PREFIX_RE.search(reply_text)
    if not m:
        return (None, None, None)
    start_brace = m.start(1)
    i = start_brace + 1
    depth = 1
    while i < len(reply_text) and depth > 0:
        c = reply_text[i]
        if c == "\\" and i + 1 < len(reply_text):
            i += 2
            continue
        if c == '"':
            j = i + 1
            while j < len(reply_text):
                if reply_text[j] == "\\":
                    j += 2
                    continue
                if reply_text[j] == '"':
                    i = j + 1
                    break
                j += 1
            else:
                i = j
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                tag_end = i + 1
                while tag_end < len(reply_text) and reply_text[tag_end] in " \t\r\n]":
                    tag_end += 1
                return (m.start(), tag_end, reply_text[start_brace : i + 1])
        i += 1
    return (None, None, None)

# Buying-signal phrases: customer must show intent before we ask for name/city/address
BUYING_SIGNAL_PATTERNS = [
    r"\b(how much is it|how much|what.?s the price|is there a discount|any discount|how do i pay|how can i pay|i liked this|i like it|does it have a warranty|warranty\?|garantie)\b",
    r"\b(i want it|i want one|i'll take it|i'll take one|i need it|how can i buy|how do i buy|where can i buy)\b",
    r"\b(ok|okay|yes|confirm|confirmed|deal|done|let's do it|جيبلي|بدي|بدّي|كيفاش نشري|نشري|ونين نقدمو|نقدمو)\b",
    r"\b(je le prends|je veux|je prends|combien|comment acheter|j'achète|ça coûte|prix|réduction)\b",
    r"\b(السعر مناسب|الثمن مزيان|تمام|نعم|أكيد|كم الثمن|كم السعر|في تخفيض|ضمان)\b",
]
BUYING_SIGNAL_RE = re.compile("|".join(BUYING_SIGNAL_PATTERNS), re.IGNORECASE)

TRUST_SCORE_MIN_FOR_ORDER = 1  # Allow order save after 1+ helpful exchange (was 3; AI confirms only when it has name+address)
TRUST_SCORE_MAX = 10
TRUST_SCORE_CACHE_TIMEOUT = 3600


def get_trust_score(channel_id, sender):
    """Get current trust_score from cache (0 if missing)."""
    try:
        from django.core.cache import cache
        key = f"trust_score:{channel_id}:{sender}"
        val = cache.get(key)
        return max(0, min(TRUST_SCORE_MAX, int(val))) if val is not None else 0
    except Exception:
        return 0


def increment_trust_score(channel_id, sender):
    """Increment trust_score after a helpful reply (cap at TRUST_SCORE_MAX). Returns new value."""
    try:
        from django.core.cache import cache
        key = f"trust_score:{channel_id}:{sender}"
        current = get_trust_score(channel_id, sender)
        new_val = min(TRUST_SCORE_MAX, current + 1)
        cache.set(key, new_val, TRUST_SCORE_CACHE_TIMEOUT)
        return new_val
    except Exception:
        return 0


def reset_trust_score(channel_id, sender):
    """Reset trust_score to 0 (e.g. after order is saved)."""
    try:
        from django.core.cache import cache
        cache.set(f"trust_score:{channel_id}:{sender}", 0, TRUST_SCORE_CACHE_TIMEOUT)
    except Exception:
        pass


def customer_gave_buying_signal(conversation_messages, last_n=5):
    """
    Return True if any of the last_n customer messages contain a buying signal
    (e.g. "I want it", "how can I buy", "ok", "جيبلي"). Used to allow ORDER_DATA
    only after the customer has agreed to buy.
    """
    if not conversation_messages:
        return False
    customer_bodies = [
        (m.get("body") or "").strip()
        for m in conversation_messages[-last_n:]
        if m.get("role") == "customer"
    ]
    for body in customer_bodies:
        if body and BUYING_SIGNAL_RE.search(body):
            return True
    return False


def should_accept_order_data(conversation_messages, order_data, current_stage=None, trust_score=None):
    """
    Return True only when we should save ORDER_DATA (strict slot-filling).
    Required: name (full or first), phone (from sender), and delivery location (address or city).
    We require: name and (address or city) non-empty; trust_score >= TRUST_SCORE_MIN_FOR_ORDER if provided;
    and either stage is order_capture, customer gave a buying signal, or we have full slots and minimal trust (AI confirmed).
    """
    if not order_data or not isinstance(order_data, dict):
        return False
    name = (order_data.get("name") or order_data.get("customer_name") or "").strip()
    city = (order_data.get("city") or order_data.get("customer_city") or "").strip()
    address = (order_data.get("address") or "").strip()
    delivery = (address or city).strip()
    if not name or not delivery:
        return False
    ts = int(trust_score) if trust_score is not None else 0
    if trust_score is not None and ts < TRUST_SCORE_MIN_FOR_ORDER:
        return False
    if current_stage == "order_capture":
        return True
    if customer_gave_buying_signal(conversation_messages or []):
        return True
    # AI only outputs ORDER_DATA / calls save_order when it has name+address; accept with minimal trust
    if ts >= TRUST_SCORE_MIN_FOR_ORDER:
        return True
    return False


def is_order_cap_reached(channel):
    """Return True if the channel's plan has max_monthly_orders and current month count >= cap."""
    store = getattr(channel, "owner", None)
    if not store or not hasattr(store, "get_plan") or not callable(store.get_plan):
        return False
    plan = store.get_plan()
    if not plan or getattr(plan, "max_monthly_orders", None) is None:
        return False
    start_of_month = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    count = SimpleOrder.objects.filter(channel=channel, created_at__gte=start_of_month).count()
    return count >= plan.max_monthly_orders


def _order_data_has_all_mandatory_slots(data):
    """Strict slot-filling: require name and delivery location (address required; city optional)."""
    if not data or not isinstance(data, dict):
        return False
    name = (data.get("name") or data.get("customer_name") or "").strip()
    city = (data.get("city") or data.get("customer_city") or "").strip()
    address = (data.get("address") or "").strip()
    return bool(name) and bool(address or city)


# Phrases that mean "order confirmed" — if these appear without [ORDER_DATA] we flag Incomplete Capture
ORDER_CONFIRMATION_PHRASES_RE = re.compile(
    r"(?:تم\s+تسجيل\s+طلبك|طلبك\s+تم\s+تسجيله|order\s+is\s+registered|your\s+order\s+is\s+confirmed|"
    r"commande\s+enregistrée|طلبك\s+مسجل)",
    re.IGNORECASE | re.UNICODE,
)


def looks_like_order_confirmation_without_data(reply_text):
    """
    True if the reply sounds like an order confirmation but we did not get valid [ORDER_DATA].
    Used to trigger retry / incomplete-capture handling.
    """
    if not reply_text or not isinstance(reply_text, str):
        return False
    return bool(ORDER_CONFIRMATION_PHRASES_RE.search(reply_text))


def extract_order_data_from_reply(reply_text):
    """
    If reply_text contains the hidden tag [ORDER_DATA: {...}], parse and return the dict
    only when all mandatory slots are present (name, city or address). Strip the tag from text.
    Uses brace-matching for robust JSON extraction. Returns (cleaned_reply, order_data_dict or None).
    """
    if not reply_text or not isinstance(reply_text, str):
        return (reply_text or "", None)
    start, end, json_str = _extract_order_data_json(reply_text)
    if start is None or not json_str:
        return (reply_text.strip(), None)
    try:
        data = json.loads(json_str)
        if not isinstance(data, dict):
            return (reply_text.strip(), None)
        # Normalize keys (name/customer_name, city/customer_city, address, sku/product_name)
        name = (data.get("name") or data.get("customer_name") or "").strip()
        city = (data.get("city") or data.get("customer_city") or "").strip()
        address = (data.get("address") or "").strip()
        sku = (data.get("sku") or "").strip()
        product_name = (data.get("product_name") or data.get("product") or "").strip()
        if not name or not (address or city):
            logger.warning("extract_order_data_from_reply: tag found but name/city/address missing or empty")
            return (reply_text.strip(), None)
        # Require product: do not accept [ORDER_DATA] without at least sku or product_name
        if not sku and not product_name:
            logger.warning("extract_order_data_from_reply: tag found but no product (sku or product_name); rejecting to avoid order without product")
            return (reply_text.strip(), None)
        order_data = {"name": name, "city": city or "", "address": address or "", "sku": sku, "product_name": product_name}
        cleaned = (reply_text[:start].strip() + " " + reply_text[end:].strip()).strip()
        return (cleaned, order_data)
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning("extract_order_data_from_reply parse error: %s", e)
    return (reply_text.strip(), None)


def track_order(customer_phone, channel=None):
    """
    Find the latest order for the given customer_phone (optionally scoped to channel).
    Returns a dict with status, shipping_company, expected_delivery_date, customer_name, and found (bool).
    If no order is found, returns found=False and status=None, etc.
    """
    if not customer_phone or not isinstance(customer_phone, str):
        return {
            "found": False,
            "status": None,
            "shipping_company": None,
            "expected_delivery_date": None,
            "days_until_delivery": None,
            "customer_name": None,
        }
    qs = SimpleOrder.objects.filter(customer_phone=customer_phone.strip()).order_by("-created_at")
    if channel:
        qs = qs.filter(channel=channel)
    order = qs.first()
    if not order:
        return {
            "found": False,
            "status": None,
            "shipping_company": None,
            "expected_delivery_date": None,
            "days_until_delivery": None,
            "customer_name": None,
        }
    expected_date = None
    days_until_delivery = None
    if getattr(order, "expected_delivery_date", None):
        expected_date = order.expected_delivery_date.isoformat()
        today = timezone.now().date()
        delta = order.expected_delivery_date - today
        days_until_delivery = max(0, delta.days)
    return {
        "found": True,
        "status": (order.status or "").strip() or "pending",
        "shipping_company": (getattr(order, "shipping_company", None) or "").strip() or None,
        "expected_delivery_date": expected_date,
        "days_until_delivery": days_until_delivery,
        "customer_name": (order.customer_name or "").strip() or None,
    }


def save_order_from_ai(channel, customer_phone, customer_name=None, customer_city=None,
                       sku=None, product_name=None, price=None, quantity=1,
                       agent_name=None, bot_session_id=None, **kwargs):
    """
    Create a SimpleOrder from AI-extracted data. Order is attributed to a Virtual Team Member (bot user).

    Args:
        channel: WhatsAppChannel instance (required).
        customer_phone: str (required).
        customer_name: str (optional).
        customer_city: str (optional) – address/city.
        sku: str (optional) – product SKU.
        product_name: str (optional).
        price: number or str (optional).
        quantity: number (default 1).
        agent_name: str (optional) – e.g. "Simo - AI Closer"; used to get/create the bot user.
        bot_session_id: str (optional) – conversation/session ID for tracing.
        **kwargs: ignored or used for other fields (e.g. customer_country).

    Returns:
        SimpleOrder instance or None on failure.
    """
    if not channel or not customer_phone:
        logger.warning("save_order_from_ai: channel and customer_phone required")
        return None

    store = getattr(channel, "owner", None)
    ai_agent_user = get_or_create_ai_agent_user(store, agent_name=agent_name)
    order_agent = ai_agent_user if ai_agent_user else store

    # Plan: max_monthly_orders cap (stop auto-order when reached)
    if store and hasattr(store, "get_plan") and callable(store.get_plan):
        plan = store.get_plan()
        if plan and getattr(plan, "max_monthly_orders", None) is not None:
            start_of_month = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            count = SimpleOrder.objects.filter(channel=channel, created_at__gte=start_of_month).count()
            if count >= plan.max_monthly_orders:
                logger.info("save_order_from_ai: max_monthly_orders (%s) reached for channel %s", plan.max_monthly_orders, channel.id)
                return None

    try:
        product_instance = None
        if sku and getattr(channel, "owner", None):
            try:
                product_instance = Products.objects.filter(admin=channel.owner).filter(sku=sku).first()
                if not product_instance:
                    product_instance = Products.objects.filter(sku=sku).first()
            except Exception as e:
                logger.warning("save_order_from_ai product lookup for sku=%s: %s", sku, e)

        order_id = str(uuid.uuid4())[:8]
        # Ensure uniqueness
        while SimpleOrder.objects.filter(order_id=order_id).exists():
            order_id = str(uuid.uuid4())[:8]

        price_val = Decimal("0")
        if price is not None:
            try:
                price_val = Decimal(str(price))
            except Exception:
                pass
        qty_val = Decimal("1")
        if quantity is not None:
            try:
                qty_val = Decimal(str(quantity))
            except Exception:
                pass

        order = SimpleOrder.objects.create(
            product=product_instance,
            agent=order_agent,
            channel=channel,
            sku=sku or "",
            product_name=(product_name or (product_instance.name if product_instance else "") or ""),
            customer_name=customer_name or customer_phone,
            customer_phone=customer_phone,
            customer_city=customer_city or "",
            customer_country=kwargs.get("customer_country"),
            order_id=order_id,
            status="pending",
            created_at=timezone.now(),
            price=price_val,
            quantity=qty_val,
            created_by_ai=True,
            created_by_bot_session=(bot_session_id or "")[:100] or None,
            sheets_export_status="pending",
        )
        logger.info("save_order_from_ai created order_id=%s for %s", order_id, customer_phone)
        # Stop logic: cancel pending follow-up tasks when customer places an order
        try:
            from discount.whatssapAPI.follow_up import cancel_pending_follow_up_tasks_for_customer
            cancel_pending_follow_up_tasks_for_customer(channel, customer_phone)
        except Exception as e:
            logger.warning("cancel_pending_follow_up_tasks_for_customer: %s", e)
        _notify_owner_order_created(channel, order)
        return order
    except Exception as e:
        logger.exception("save_order_from_ai failed: %s", e)
        return None


def _notify_owner_order_created(channel, order):
    """If channel has order_notify_method (EMAIL or WHATSAPP), send owner a notification. Runs after order is created."""
    method = getattr(channel, "order_notify_method", None) or ""
    if not method or method not in ("EMAIL", "WHATSAPP"):
        return
    try:
        if method == "EMAIL":
            to_email = (getattr(channel, "order_notify_email", None) or "").strip()
            if not to_email and getattr(channel, "owner", None):
                to_email = (getattr(channel.owner, "email", None) or "").strip()
            if not to_email:
                return
            from django.core.mail import send_mail
            from django.conf import settings
            subject = f"New order #{getattr(order, 'order_id', '')} from AI"
            body = (
                f"A new order was created by the AI sales agent.\n\n"
                f"Order ID: {getattr(order, 'order_id', '')}\n"
                f"Customer: {getattr(order, 'customer_name', '')} / {getattr(order, 'customer_phone', '')}\n"
                f"Address/City: {getattr(order, 'customer_city', '')}\n"
                f"Product: {getattr(order, 'product_name', '')}\n"
                f"Price: {getattr(order, 'price', '')} x {getattr(order, 'quantity', 1)}\n"
            )
            send_mail(
                subject=subject,
                message=body,
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@example.com"),
                recipient_list=[to_email],
                fail_silently=True,
            )
            logger.info("order notify email sent to %s for order_id=%s", to_email, getattr(order, "order_id", ""))
        elif method == "WHATSAPP":
            to_phone = (getattr(channel, "order_notify_whatsapp_phone", None) or "").strip()
            if not to_phone and getattr(channel, "owner", None):
                to_phone = (getattr(channel.owner, "phone", None) or "").strip()
            if not to_phone:
                return
            to_phone = "".join(c for c in to_phone if c.isdigit())
            if not to_phone or len(to_phone) < 10:
                return
            from discount.whatssapAPI.process_messages import send_automated_response
            msg = (
                f"🆕 New order from AI\n"
                f"Order ID: {getattr(order, 'order_id', '')}\n"
                f"Customer: {getattr(order, 'customer_name', '')} / {getattr(order, 'customer_phone', '')}\n"
                f"Address: {getattr(order, 'customer_city', '')}\n"
                f"Product: {getattr(order, 'product_name', '')}"
            )
            send_automated_response(to_phone, [{"type": "text", "content": msg}], channel=channel)
            logger.info("order notify WhatsApp sent to %s for order_id=%s", to_phone, getattr(order, "order_id", ""))
    except Exception as e:
        logger.exception("_notify_owner_order_created failed: %s", e)
