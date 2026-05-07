"""
Django signals for discount app.
"""
import logging
import threading

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_save)
def on_simpleorder_created_sync_google_sheets(sender, instance, created, **kwargs):
    """
    When a new SimpleOrder is created, trigger sync to Google Sheets in a background thread.
    """
    if sender.__name__ != "SimpleOrder":
        return
    if not created:
        return
    try:
        from discount.models import SimpleOrder
        if not isinstance(instance, SimpleOrder):
            return
    except ImportError:
        return
    order_id = getattr(instance, "pk", None) or getattr(instance, "id", None)
    if not order_id:
        return

    def _run_sync():
        try:
            from discount.services.google_sheets_service import sync_order_to_google_sheets
            sync_order_to_google_sheets(order_id)
        except Exception as e:
            logger.exception("Background sync_order_to_google_sheets order_id=%s failed: %s", order_id, e)

    t = threading.Thread(target=_run_sync, daemon=True)
    t.start()
