"""
Risk management signals — log auditable events for Founder HQ.
"""
import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_save)
def on_simpleorder_risk_signals(sender, instance, created, **kwargs):
    if sender.__name__ != "SimpleOrder":
        return
    try:
        from discount.models import SimpleOrder
        from discount.services.tenant_risk import record_event_for_channel

        if not isinstance(instance, SimpleOrder):
            return
        channel = getattr(instance, "channel", None)
        if not channel:
            return
        phone = (instance.customer_phone or "").strip()

        if not created and (instance.payment_rejection_reason or "").strip():
            from discount.models import MerchantRiskEvent

            if MerchantRiskEvent.objects.filter(
                order_id=instance.pk,
                event_type=MerchantRiskEvent.EVENT_PAYMENT_REJECTED,
            ).exists():
                return
            record_event_for_channel(
                channel,
                "payment_rejected",
                order=instance,
                customer_phone=phone,
                summary=(instance.payment_rejection_reason or "")[:500],
                metadata={"order_id": instance.order_id, "status": instance.status},
            )
    except Exception as exc:
        logger.exception("on_simpleorder_risk_signals: %s", exc)
