"""
Stripe Checkout integration for $1 trial payments.

Exposes:
  - create_trial_checkout_session(user, user_id, price_id) → session URL
  - handle_checkout_webhook(payload, sig_header) → bool

The webhook handler assigns the Plan to the user once payment succeeds,
using metadata embedded in the Checkout Session.
"""
import logging
from decimal import Decimal

import stripe
from django.conf import settings
from django.urls import reverse

logger = logging.getLogger(__name__)

stripe.api_key = settings.STRIPE_SECRET_KEY

PLAN_DISPLAY = {
    "starter": "Starter",
    "pro": "Pro",
    "elite": "Elite",
}

PLAN_NAME_ALIASES = {
    "starter": ["starter", "basic", "free"],
    "pro": ["pro", "premium"],
    "elite": ["elite"],
}

PLAN_AMOUNT_CENTS = {
    "starter": 1900,
    "pro": 4100,
    "elite": 9900,
}


def _ensure_customer_for_user(user):
    """
    Return a Stripe customer id for the user, creating one if needed.
    """
    if getattr(user, "stripe_customer_id", None):
        return user.stripe_customer_id

    try:
        customer = stripe.Customer.create(
            email=user.email,
            metadata={"user_id": str(user.pk)},
            name=(getattr(user, "user_name", "") or user.username or user.email),
        )
    except stripe.error.StripeError as e:
        logger.exception("Stripe customer creation failed for user %s: %s", user.pk, e)
        return None

    user.stripe_customer_id = customer.id
    user.save(update_fields=["stripe_customer_id"])
    return customer.id


def _resolve_plan(plan_name):
    """
    Resolve external checkout plan keys to actual DB plan records.
    Supports aliases (e.g. pro -> Premium) for legacy plan names.
    """
    from discount.models import Plan

    key = (plan_name or "").strip().lower()
    candidates = PLAN_NAME_ALIASES.get(key, [key])
    for candidate in candidates:
        plan = Plan.objects.filter(name__iexact=candidate).first()
        if plan:
            return plan
    return None


def _resolve_plan_by_amount(unit_amount):
    if unit_amount is None:
        return None
    try:
        amount = int(unit_amount)
    except Exception:
        return None
    for key, cents in PLAN_AMOUNT_CENTS.items():
        if cents == amount:
            return _resolve_plan(key)
    return None


def _resolve_plan_from_subscription_obj(subscription):
    """
    Resolve plan tier from a Stripe subscription payload.
    Priority:
      1) subscription metadata plan_name/planId
      2) first recurring item price amount
      
    """
    if not subscription:
        return None
    meta = subscription.get("metadata") or {}
    by_name = _resolve_plan((meta.get("plan_name") or meta.get("planId") or "").strip().lower())
    if by_name:
        return by_name

    items = (((subscription.get("items") or {}).get("data")) or [])
    if items:
        first_price = (items[0] or {}).get("price") or {}
        by_amount = _resolve_plan_by_amount(first_price.get("unit_amount"))
        if by_amount:
            return by_amount
    return None


def create_trial_checkout_session(user, user_id, price_id=None, plan_name=None, app_url=None):
    """
    Create a Stripe Checkout Session for "$1 paid trial + recurring subscription".

    Returns the session URL to redirect the user to, or None on failure.
    """
    app_url = (app_url or getattr(settings, "APP_URL", "")).rstrip("/")
    customer_id = _ensure_customer_for_user(user)
    if not customer_id:
        return None

    # Backward compatibility: if price_id is not provided, derive a recurring monthly price
    # from plan_name so old frontend payloads ({planId}) keep working.
    plan_key = (plan_name or "").strip().lower()
    plan_amounts_usd = {
        "starter": 19,
        "basic": 19,
        "free": 19,
        "pro": 41,
        "premium": 41,
        "elite": 99,
    }
    recurring_item = None
    if price_id:
        recurring_item = {"price": price_id, "quantity": 1}
    else:
        amount = plan_amounts_usd.get(plan_key)
        if not amount:
            return None
        recurring_item = {
            "price_data": {
                "currency": "usd",
                "recurring": {"interval": "month"},
                "product_data": {
                    "name": f"Waselytics {PLAN_DISPLAY.get(plan_key, plan_key.title() or 'Plan')} Monthly",
                },
                "unit_amount": int(amount * 100),
            },
            "quantity": 1,
        }

    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            # Charge $1 now and start a 7-day trial for the recurring subscription price.
            # Stripe will automatically bill the recurring price on day 8 unless canceled.
            mode="subscription",
            customer=customer_id,
            line_items=[
                {
                    "price_data": {
                        "currency": "usd",
                        "unit_amount": 100,
                        "product_data": {
                            "name": "7-Day Trial Setup Fee",
                        },
                    },
                    "quantity": 1,
                },
                recurring_item,
            ],
            subscription_data={
                "trial_period_days": 7,
                "metadata": {
                    "userId": str(user_id),
                },
            },
            client_reference_id=str(user_id),
            metadata={
                "user_id": str(user_id),
                "userId": str(user_id),
                "price_id": price_id or "",
                "plan_name": plan_key,
            },
            success_url=f"{app_url}/tracking/?session_id={{CHECKOUT_SESSION_ID}}&success=true",
            cancel_url=f"{app_url}/?canceled=true#pricing",
        )
        if session.get("customer") and not user.stripe_customer_id:
            user.stripe_customer_id = session.get("customer")
            user.save(update_fields=["stripe_customer_id"])
        return session.url
    except stripe.error.StripeError as e:
        logger.exception("Stripe checkout session creation failed: %s", e)
        return None


def create_billing_portal_session(user, return_url=None):
    """
    Create a Stripe Billing Portal session for subscription management.
    """
    customer_id = _ensure_customer_for_user(user)
    if not customer_id:
        return None

    app_url = (getattr(settings, "APP_URL", "") or "").rstrip("/")
    return_url = return_url or f"{app_url}/tracking/user/?tab=current-plan"

    try:
        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=return_url,
        )
        return session.url
    except stripe.error.StripeError as e:
        logger.exception("Stripe portal session creation failed: %s", e)
        return None


def create_wallet_topup_checkout_session(user, user_id, amount, app_url=None):
    """
    Create a one-time Stripe Checkout Session to top up wallet credits.
    """
    app_url = (app_url or getattr(settings, "APP_URL", "")).rstrip("/")
    customer_id = _ensure_customer_for_user(user)
    if not customer_id:
        return None

    try:
        dollars = Decimal(str(amount))
    except Exception:
        return None
    if dollars <= 0:
        return None
    cents = int(dollars * 100)

    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            mode="payment",
            customer=customer_id,
            line_items=[
                {
                    "price_data": {
                        "currency": "usd",
                        "unit_amount": cents,
                        "product_data": {"name": "AI Token Credits Top-Up"},
                    },
                    "quantity": 1,
                }
            ],
            client_reference_id=str(user_id),
            metadata={
                "user_id": str(user_id),
                "userId": str(user_id),
                "type": "wallet_topup",
                "topupAmount": str(dollars),
            },
            success_url=f"{app_url}/tracking/user/?tab=current-plan&wallet_topup=success",
            cancel_url=f"{app_url}/tracking/user/?tab=current-plan&wallet_topup=canceled",
        )
        return session.url
    except stripe.error.StripeError as e:
        logger.exception("Stripe wallet topup session creation failed: %s", e)
        return None


def _subscription_is_extra_channel_addon(sub):
    """Detect add-on subscriptions so we never overwrite the user's main plan subscription fields."""
    if not sub:
        return False
    meta = sub.get("metadata") or {}
    if str(meta.get("type") or "").strip().lower() == "extra_channel_slot":
        return True
    sub_id = sub.get("id")
    if not sub_id:
        return False
    from discount.models import ExtraChannelSlotSubscription

    return ExtraChannelSlotSubscription.objects.filter(stripe_subscription_id=sub_id).exists()


def sync_extra_addon_subscription_from_stripe(sub, event_type):
    """Keep ExtraChannelSlotSubscription.active in sync (webhook-driven)."""
    from discount.models import ExtraChannelSlotSubscription

    sub_id = sub.get("id")
    if not sub_id:
        return
    if event_type == "customer.subscription.deleted":
        ExtraChannelSlotSubscription.objects.filter(stripe_subscription_id=sub_id).update(active=False)
        return
    status = (sub.get("status") or "").strip().lower()
    active = status in ("active", "trialing", "past_due", "unpaid")
    ExtraChannelSlotSubscription.objects.filter(stripe_subscription_id=sub_id).update(active=active)


def grant_extra_channel_slot_from_checkout_session(session):
    """
    Idempotent: one row per Stripe subscription id.
    Called from checkout.session.completed webhook and optional success-url verify.
    """
    from django.db import transaction

    from discount.models import CustomUser, ExtraChannelSlotSubscription

    meta = session.get("metadata") or {}
    owner_id = str(meta.get("billing_owner_id") or meta.get("user_id") or "").strip()
    sub_id = session.get("subscription")
    customer_id = session.get("customer") or ""
    if not owner_id or not sub_id:
        logger.warning("extra_channel_slot: missing billing_owner_id or subscription in session metadata")
        return False
    with transaction.atomic():
        owner = CustomUser.objects.select_for_update().filter(pk=owner_id).first()
        if not owner:
            logger.warning("extra_channel_slot: billing owner %s not found", owner_id)
            return False
        ExtraChannelSlotSubscription.objects.update_or_create(
            stripe_subscription_id=sub_id,
            defaults={
                "billing_owner": owner,
                "stripe_customer_id": customer_id or None,
                "active": True,
            },
        )
    logger.info(
        "extra_channel_slot granted owner=%s subscription=%s",
        owner_id,
        sub_id,
    )
    return True


def create_extra_channel_checkout_session(billing_owner_user, app_url=None):
    """
    Recurring monthly add-on (+1 channel vs plan base cap). Does not replace the main plan subscription.
    """
    app_url = (app_url or getattr(settings, "APP_URL", "")).rstrip("/")
    customer_id = _ensure_customer_for_user(billing_owner_user)
    if not customer_id:
        return None

    price_id = (getattr(settings, "STRIPE_EXTRA_CHANNEL_PRICE_ID", None) or "").strip()
    monthly = float(getattr(settings, "EXTRA_CHANNEL_MONTHLY_USD", 5))
    cents = int(round(monthly * 100))
    if cents < 50:
        logger.error("EXTRA_CHANNEL_MONTHLY_USD too low for Stripe")
        return None

    line_item = {"quantity": 1}
    if price_id:
        line_item["price"] = price_id
    else:
        line_item["price_data"] = {
            "currency": "usd",
            "recurring": {"interval": "month"},
            "product_data": {"name": "Extra WhatsApp channel (monthly add-on)"},
            "unit_amount": cents,
        }

    rel_success = reverse("whatsapp") + "?extra_channel_success=1&session_id={CHECKOUT_SESSION_ID}"
    rel_cancel = reverse("whatsapp") + "?extra_channel_canceled=1"

    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            customer=customer_id,
            line_items=[line_item],
            metadata={
                "type": "extra_channel_slot",
                "billing_owner_id": str(billing_owner_user.pk),
                "user_id": str(billing_owner_user.pk),
            },
            subscription_data={
                "metadata": {
                    "type": "extra_channel_slot",
                    "billing_owner_id": str(billing_owner_user.pk),
                }
            },
            success_url=f"{app_url}{rel_success}",
            cancel_url=f"{app_url}{rel_cancel}",
        )
        return session.url
    except stripe.error.StripeError as e:
        logger.exception("extra_channel_slot checkout session failed: %s", e)
        return None


def confirm_extra_channel_checkout_session(session_id, billing_owner_user):
    """
    Fallback after redirect if webhook is slow. Verifies Stripe session belongs to this customer and type.
    """
    if not session_id:
        return False, "missing_session"
    try:
        session = stripe.checkout.Session.retrieve(session_id)
    except stripe.error.StripeError as e:
        logger.warning("confirm_extra_channel: retrieve failed %s", e)
        return False, "stripe_error"

    if session.get("payment_status") != "paid":
        return False, "not_paid"

    meta = session.get("metadata") or {}
    if str(meta.get("type") or "").strip().lower() != "extra_channel_slot":
        return False, "wrong_type"

    owner_id = str(meta.get("billing_owner_id") or meta.get("user_id") or "").strip()
    if owner_id != str(billing_owner_user.pk):
        return False, "forbidden"

    session_customer = session.get("customer")
    user_cust = getattr(billing_owner_user, "stripe_customer_id", None) or ""
    if session_customer and user_cust and session_customer != user_cust:
        return False, "customer_mismatch"

    if not grant_extra_channel_slot_from_checkout_session(session):
        return False, "grant_failed"
    return True, None


def handle_checkout_webhook(payload, sig_header):
    """
    Verify and process a Stripe webhook event.

    On `checkout.session.completed`, assigns the plan from metadata to the user.
    Returns True if processed, False otherwise.
    """
    endpoint_secret = getattr(settings, "STRIPE_WEBHOOK_SECRET", "")
    if not endpoint_secret:
        logger.warning("STRIPE_WEBHOOK_SECRET not configured — skipping webhook")
        return False

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
    except (ValueError, stripe.error.SignatureVerificationError) as e:
        logger.warning("Stripe webhook signature verification failed: %s", e)
        return False

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        meta = session.get("metadata") or {}
        user_id = str(meta.get("user_id") or meta.get("userId") or session.get("client_reference_id") or "").strip()
        session_type = str(meta.get("type") or "").strip().lower()
        plan_name = (meta.get("plan_name") or "").strip().lower()
        customer_id = session.get("customer")
        subscription_id = session.get("subscription")
        sub_status = "active"
        resolved_plan = _resolve_plan(plan_name) if plan_name else None

        if not user_id:
            logger.warning("Stripe checkout.session.completed missing user id: %s", meta)
            return True

        try:
            from discount.models import CustomUser

            user = CustomUser.objects.filter(pk=user_id).first()
            if not user:
                logger.warning("Stripe webhook: user %s not found", user_id)
                return True

            # Wallet top-up checkout flow
            if session_type == "wallet_topup":
                try:
                    topup_amount = Decimal(str(meta.get("topupAmount") or "0"))
                except Exception:
                    topup_amount = Decimal("0")
                if topup_amount > 0:
                    user.wallet_balance = Decimal(getattr(user, "wallet_balance", 0) or 0) + topup_amount
                update_fields = ["wallet_balance"] if topup_amount > 0 else []
                if customer_id and getattr(user, "stripe_customer_id", None) != customer_id:
                    user.stripe_customer_id = customer_id
                    update_fields.append("stripe_customer_id")
                if update_fields:
                    user.save(update_fields=update_fields)
                return True

            # Extra WhatsApp channel slot ($/mo add-on) — must not touch main plan subscription fields.
            if session_type == "extra_channel_slot":
                grant_extra_channel_slot_from_checkout_session(session)
                return True

            # Retrieve subscription to capture status and infer plan if not provided in metadata.
            if subscription_id:
                try:
                    sub = stripe.Subscription.retrieve(subscription_id)
                    sub_status = (sub.get("status") or "active").strip().lower()
                    resolved_plan = resolved_plan or _resolve_plan_from_subscription_obj(sub)
                except stripe.error.StripeError as se:
                    logger.warning("Stripe checkout.session.completed subscription retrieve failed: %s", se)

            update_fields = []
            if resolved_plan:
                user.plan = resolved_plan
                update_fields.append("plan")
            # $1 welcome gift on successful trial checkout
            current_wallet = Decimal(getattr(user, "wallet_balance", 0) or 0)
            if current_wallet < Decimal("1.00"):
                user.wallet_balance = Decimal("1.00")
                update_fields.append("wallet_balance")
            if customer_id and getattr(user, "stripe_customer_id", None) != customer_id:
                user.stripe_customer_id = customer_id
                update_fields.append("stripe_customer_id")
            if subscription_id and getattr(user, "stripe_subscription_id", None) != subscription_id:
                user.stripe_subscription_id = subscription_id
                update_fields.append("stripe_subscription_id")
            if getattr(user, "stripe_subscription_status", None) != sub_status:
                user.stripe_subscription_status = sub_status
                update_fields.append("stripe_subscription_status")
            if not update_fields:
                return True
            user.save(update_fields=update_fields)
            logger.info(
                "Stripe checkout.session.completed synced user=%s plan=%s customer=%s subscription=%s status=%s",
                user_id,
                getattr(user.plan, "name", None),
                customer_id,
                subscription_id,
                sub_status,
            )
            return True
        except Exception:
            logger.exception("Stripe webhook: plan assignment failed")
            return True

    if event["type"] == "customer.subscription.updated":
        sub = event["data"]["object"]
        if _subscription_is_extra_channel_addon(sub):
            sync_extra_addon_subscription_from_stripe(sub, event["type"])
            return True
        customer_id = sub.get("customer")
        sub_id = sub.get("id")
        sub_status = (sub.get("status") or "").strip().lower()
        resolved_plan = _resolve_plan_from_subscription_obj(sub)
        if not customer_id:
            return True
        try:
            from discount.models import CustomUser

            user = CustomUser.objects.filter(stripe_customer_id=customer_id).first()
            if not user:
                logger.warning("Stripe subscription.updated: no user for customer %s", customer_id)
                return True
            if resolved_plan:
                user.plan = resolved_plan
            user.stripe_subscription_id = sub_id
            user.stripe_subscription_status = sub_status
            update_fields = ["stripe_subscription_id", "stripe_subscription_status"]
            if resolved_plan:
                update_fields.append("plan")
            user.save(update_fields=update_fields)
            return True
        except Exception:
            logger.exception("Stripe subscription.updated handling failed")
            return True

    if event["type"] == "customer.subscription.deleted":
        sub = event["data"]["object"]
        if _subscription_is_extra_channel_addon(sub):
            sync_extra_addon_subscription_from_stripe(sub, event["type"])
            return True
        customer_id = sub.get("customer")
        if not customer_id:
            return True
        try:
            from discount.models import CustomUser

            user = CustomUser.objects.filter(stripe_customer_id=customer_id).first()
            if not user:
                logger.warning("Stripe subscription.deleted: no user for customer %s", customer_id)
                return True
            user.stripe_subscription_id = None
            user.stripe_subscription_status = "canceled"
            user.plan = None
            user.save(update_fields=["stripe_subscription_id", "stripe_subscription_status", "plan"])
            return True
        except Exception:
            logger.exception("Stripe subscription.deleted handling failed")
            return True

    # Acknowledge receipt for any other event types (prevents Stripe retry storms / noisy 400 logs).
    logger.info("Stripe webhook: unhandled event type '%s'", event.get("type"))
    return True


def assign_plan_from_success_session(session_id, expected_user_id):
    """
    Fallback activation when the user returns from Stripe success URL.
    Verifies the Checkout Session with Stripe, then assigns the plan.
    """
    if not session_id or not expected_user_id:
        return False

    try:
        session = stripe.checkout.Session.retrieve(session_id)
    except stripe.error.StripeError as e:
        logger.warning("Stripe session retrieve failed for %s: %s", session_id, e)
        return False

    if session.get("payment_status") != "paid":
        logger.warning("Stripe session %s is not paid yet", session_id)
        return False

    meta = session.get("metadata") or {}
    user_id = str(meta.get("user_id") or "")
    plan_name = (meta.get("plan_name") or "").strip()
    if user_id != str(expected_user_id) or not plan_name:
        logger.warning(
            "Stripe success session metadata mismatch: expected_user=%s got_user=%s plan=%s",
            expected_user_id,
            user_id,
            plan_name,
        )
        return False

    try:
        from discount.models import CustomUser

        user = CustomUser.objects.filter(pk=expected_user_id).first()
        if not user:
            return False

        plan = _resolve_plan(plan_name)
        if not plan:
            logger.warning("Stripe success session: plan '%s' not found", plan_name)
            return False

        if user.plan_id == plan.id:
            return True
        user.plan = plan
        user.save(update_fields=["plan"])
        logger.info("Stripe success session: user %s assigned plan '%s'", user.pk, plan.name)
        return True
    except Exception:
        logger.exception("Stripe success session: plan assignment failed")
        return False
