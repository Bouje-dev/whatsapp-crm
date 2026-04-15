from decimal import Decimal
import logging

from django.core.mail import send_mail
from django.db import transaction
from django.conf import settings


logger = logging.getLogger(__name__)


TOKEN_COST_PER_1K = Decimal("0.005")
LOW_BALANCE_THRESHOLD = Decimal("0.50")


def sendLowBalanceEmail(email):
    """
    Mock low-balance notifier.
    """
    if not email:
        return
    try:
        send_mail(
            subject="Low wallet balance alert",
            message="Your AI wallet balance is below $0.50. Please top up to keep AI replies running.",
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
            recipient_list=[email],
            fail_silently=True,
        )
    except Exception:
        logger.exception("sendLowBalanceEmail failed for %s", email)


def chargeUserForAiUsage(userId, inputTokens, outputTokens):
    """
    Deduct wallet by token usage and update accounting counters.
    Cost model: $0.005 per 1000 total tokens.
    """
    from discount.models import CustomUser

    in_tokens = max(0, int(inputTokens or 0))
    out_tokens = max(0, int(outputTokens or 0))
    total_tokens = in_tokens + out_tokens
    if total_tokens <= 0:
        return {"ok": True, "charged": "0", "balance": None}

    cost = (Decimal(total_tokens) / Decimal(1000)) * TOKEN_COST_PER_1K

    with transaction.atomic():
        user = CustomUser.objects.select_for_update().filter(pk=userId).first()
        if not user:
            return {"ok": False, "error": "user_not_found"}

        before = Decimal(user.wallet_balance or 0)
        after = before - cost
        user.wallet_balance = after
        user.total_tokens_used = int(user.total_tokens_used or 0) + total_tokens
        user.save(update_fields=["wallet_balance", "total_tokens_used"])

        if (
            before >= LOW_BALANCE_THRESHOLD
            and after < LOW_BALANCE_THRESHOLD
            and bool(getattr(user, "low_balance_alert_enabled", True))
        ):
            sendLowBalanceEmail(user.email)

    return {
        "ok": True,
        "charged": str(cost),
        "balance": str(after),
        "tokens": total_tokens,
    }
