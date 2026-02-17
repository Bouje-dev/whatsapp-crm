"""
Stateless Aggregation: recalculate reputation from Order table on every save.
No incremental counters. Always query DB = always correct.
"""
import logging
from django.db import transaction
from django.utils import timezone

from reputation.models import GlobalCustomerProfile
from reputation.utils import normalize_phone_for_reputation

logger = logging.getLogger(__name__)


def recalculate_reputation(phone_number):
    """
    Count all orders for this phone, compute score, overwrite profile.
    This is the ONLY function that writes to GlobalCustomerProfile.
    """
    phone_key = normalize_phone_for_reputation(phone_number)
    if not phone_key:
        logger.warning("recalculate_reputation: empty phone_key for %r", phone_number)
        return None

    try:
        from orders.models import Order

        with transaction.atomic():
            qs = Order.objects.filter(phone=phone_number)

            delivered = qs.filter(status="DELIVERED").count()
            returned = qs.filter(status="RETURNED").count()
            canceled = qs.filter(status="CANCELED").count()
            no_answer = qs.filter(status="NO_ANSWER").count()
            total = delivered + returned + canceled + no_answer

            # Score: base 50 + adjustments, clamped 0-100
            score = 50 + (delivered * 10) - (returned * 10) - (no_answer * 5) - (canceled * 2)
            score = max(0, min(100, score))

            # Risk level from score
            if score >= 80:
                risk_level = "ELITE"
            elif score >= 60:
                risk_level = "GOOD"
            elif score >= 40:
                risk_level = "NEUTRAL"
            elif score >= 20:
                risk_level = "RISKY"
            else:
                risk_level = "BLACKLIST"

            # Last order date
            last = qs.order_by("-updated_at").values_list("updated_at", flat=True).first()

            profile, created = GlobalCustomerProfile.objects.update_or_create(
                phone_number=phone_key,
                defaults={
                    "total_orders": total,
                    "delivered_count": delivered,
                    "returned_count": returned,
                    "canceled_count": canceled,
                    "no_answer_count": no_answer,
                    "trust_score": score,
                    "risk_level": risk_level,
                    "last_order_date": last or timezone.now(),
                },
            )

            logger.info(
                "reputation: %s phone=%s d=%s r=%s c=%s na=%s score=%s level=%s",
                "created" if created else "updated",
                phone_key[:12], delivered, returned, canceled, no_answer, score, risk_level,
            )
            return profile

    except Exception:
        logger.exception("recalculate_reputation failed phone=%s", phone_number)
        return None


def recalculate_all_reputations():
    """Recalculate every unique phone in the Order table. Returns count processed."""
    try:
        from orders.models import Order

        phones = (
            Order.objects
            .exclude(phone="")
            .exclude(phone__isnull=True)
            .values_list("phone", flat=True)
            .distinct()
        )
        count = 0
        for phone in phones:
            if recalculate_reputation(phone):
                count += 1
        logger.info("recalculate_all: processed %d phones", count)
        return count
    except Exception:
        logger.exception("recalculate_all_reputations failed")
        return 0
