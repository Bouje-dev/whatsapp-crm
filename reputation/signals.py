"""
post_save signal on Order -> recalculate reputation from DB.
Registered in ReputationConfig.ready().
"""
import logging
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


def register_signals():
    """Called once from apps.py ready()."""
    from orders.models import Order
    from reputation.services import recalculate_reputation

    @receiver(post_save, sender=Order)
    def order_post_save(sender, instance, **kwargs):
        phone = getattr(instance, "phone", None)
        if not phone:
            return
        # Run AFTER the current transaction commits so the new status is visible
        transaction.on_commit(lambda: recalculate_reputation(phone))
