"""
Subscription plan limit enforcement.

Provides PLAN_LIMITS defaults (applied when the Plan row has NULL in a limit
field), a reusable checker function, and a Django view decorator factory that
gates any view behind a specific resource limit.

Usage in views:
    from discount.services.plan_limits import check_plan_limit

    @require_POST
    @check_plan_limit("max_channels")
    def create_channel_api(request):
        ...
"""
import logging
from functools import wraps

from django.conf import settings
from django.http import JsonResponse
from django.utils import timezone

logger = logging.getLogger(__name__)

# ── Source-of-truth defaults ────────────────────────────────────────────
# Applied when the Plan DB row has NULL for a limit field.  Keep in sync
# with the pricing page and admin-set values.
PLAN_LIMITS = {
    "starter": {"max_channels": 1, "max_team_members": 2, "max_monthly_orders": 500},
    "pro":     {"max_channels": 3, "max_team_members": 5, "max_monthly_orders": None},   # None = unlimited
    "elite":   {"max_channels": None, "max_team_members": None, "max_monthly_orders": None},
}

# Friendly names for the 403 response.
_RESOURCE_LABELS = {
    "max_channels": "WhatsApp channels",
    "max_team_members": "team members",
    "max_monthly_orders": "monthly orders",
}


# ── Core logic ──────────────────────────────────────────────────────────

def _resolve_admin_user(user):
    """Walk team_admin chain so team members inherit the admin's plan."""
    if getattr(user, "team_admin_id", None):
        return user.team_admin
    return user


def _get_limit(plan, resource_type):
    """
    Return the numeric limit for *resource_type* from the Plan row.
    Falls back to PLAN_LIMITS defaults keyed by plan name (case-insensitive).
    Returns None when the resource is unlimited.
    """
    db_value = getattr(plan, resource_type, None) if plan else None
    if db_value is not None:
        return db_value
    plan_name = (getattr(plan, "name", "") or "").strip().lower()
    defaults = PLAN_LIMITS.get(plan_name, {})
    return defaults.get(resource_type)


def count_extra_channel_slots(admin_user):
    """Paid Stripe add-ons: each active subscription row adds +1 to channel cap."""
    from discount.models import ExtraChannelSlotSubscription

    return ExtraChannelSlotSubscription.objects.filter(
        billing_owner=admin_user, active=True
    ).count()


def _count_current_usage(admin_user, resource_type):
    """
    Fast DB count of how many of *resource_type* the admin_user currently has.
    """
    from discount.models import WhatsAppChannel, CustomUser

    if resource_type == "max_channels":
        return WhatsAppChannel.objects.filter(owner=admin_user).count()

    if resource_type == "max_team_members":
        return (
            CustomUser.objects
            .filter(team_admin=admin_user, is_bot=False)
            .count()
        )

    if resource_type == "max_monthly_orders":
        from discount.models import SimpleOrder
        start_of_month = timezone.now().replace(
            day=1, hour=0, minute=0, second=0, microsecond=0,
        )
        return SimpleOrder.objects.filter(
            channel__owner=admin_user,
            created_at__gte=start_of_month,
        ).count()

    return 0


def is_limit_reached(user, resource_type):
    """
    Return (reached: bool, limit: int|None, current: int).
    limit=None means unlimited. For max_channels, limit is the effective cap (plan + paid add-ons).
    """
    admin_user = _resolve_admin_user(user)
    plan = admin_user.get_plan() if hasattr(admin_user, "get_plan") else None
    limit = _get_limit(plan, resource_type)
    if limit is None:
        return False, None, 0
    current = _count_current_usage(admin_user, resource_type)
    if resource_type == "max_channels":
        extra = count_extra_channel_slots(admin_user)
        effective = limit + extra
        return current >= effective, effective, current
    return current >= limit, limit, current


def get_max_channels_status(user):
    """
    JSON-serializable snapshot for the WhatsApp UI and billing APIs.
    """
    admin_user = _resolve_admin_user(user)
    plan = admin_user.get_plan() if hasattr(admin_user, "get_plan") else None
    base_limit = _get_limit(plan, "max_channels")
    current = _count_current_usage(admin_user, "max_channels")
    extra_slots = count_extra_channel_slots(admin_user)
    is_owner = user.pk == admin_user.pk

    if base_limit is None:
        return {
            "success": True,
            "unlimited": True,
            "current": current,
            "base_limit": None,
            "extra_slots": 0,
            "effective_limit": None,
            "at_limit": False,
            "can_purchase_extra": False,
            "is_billing_owner": is_owner,
            "extra_monthly_usd": float(getattr(settings, "EXTRA_CHANNEL_MONTHLY_USD", 5)),
        }

    effective = base_limit + extra_slots
    at_limit = current >= effective
    return {
        "success": True,
        "unlimited": False,
        "current": current,
        "base_limit": base_limit,
        "extra_slots": extra_slots,
        "effective_limit": effective,
        "at_limit": at_limit,
        "can_purchase_extra": bool(at_limit and is_owner),
        "is_billing_owner": is_owner,
        "extra_monthly_usd": float(getattr(settings, "EXTRA_CHANNEL_MONTHLY_USD", 5)),
    }


# ── Django view decorator ───────────────────────────────────────────────

def check_plan_limit(resource_type):
    """
    Decorator factory that returns a 403 JSON when the authenticated user's
    plan limit for *resource_type* is reached.

        @check_plan_limit("max_channels")
        def create_channel_api(request): ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            user = getattr(request, "user", None)
            if not user or not user.is_authenticated:
                return JsonResponse(
                    {"error": "Authentication required"},
                    status=401,
                )

            reached, limit, current = is_limit_reached(user, resource_type)
            if reached:
                label = _RESOURCE_LABELS.get(resource_type, resource_type)
                logger.info(
                    "Plan limit reached: user=%s resource=%s current=%s limit=%s",
                    user.pk, resource_type, current, limit,
                )
                return JsonResponse(
                    {
                        "success": False,
                        "error": "Plan limit reached",
                        "resource": resource_type,
                        "current": current,
                        "limit": limit,
                        "message": (
                            f"You've reached your plan limit of {limit} {label}. "
                            "Upgrade your plan to add more."
                        ),
                    },
                    status=403,
                )
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator
