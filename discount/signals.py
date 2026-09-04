"""
Django signals for discount app.
"""
import logging
import threading

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


def _product_embed_source(instance) -> str:
    from ai_assistant.embeddings import product_embedding_text

    return product_embedding_text(instance)


@receiver(pre_save)
def stash_product_text_for_embedding(sender, instance, **kwargs):
    """Remember title+description before save so post_save can detect changes."""
    if sender.__name__ != "Products":
        return
    instance._embedding_source_before = None
    pk = getattr(instance, "pk", None)
    if not pk:
        return
    try:
        old = sender.objects.filter(pk=pk).only("name", "description").first()
        instance._embedding_source_before = _product_embed_source(old) if old else None
    except Exception:
        instance._embedding_source_before = None


@receiver(post_save)
def generate_product_embedding_on_text_change(sender, instance, created, **kwargs):
    """
    When a product is saved, if title + description changed (or this is a new
    product), generate an OpenAI embedding in a background thread.
    """
    if sender.__name__ != "Products":
        return
    update_fields = kwargs.get("update_fields")
    if update_fields is not None:
        fields = set(update_fields)
        if fields <= {"embedding"}:
            return
        if not created and not (fields & {"name", "description"}):
            # Text did not change on this save; still retry if embedding is missing.
            if getattr(instance, "embedding", None) is not None:
                return

    new_text = _product_embed_source(instance)
    if not new_text:
        return
    if not created:
        old_text = getattr(instance, "_embedding_source_before", None)
        if old_text == new_text and getattr(instance, "embedding", None) is not None:
            return

    product_id = getattr(instance, "pk", None)
    if not product_id:
        return

    def _run_embed():
        from django.db import close_old_connections

        close_old_connections()
        try:
            from ai_assistant.embeddings import refresh_product_embedding

            refresh_product_embedding(product_id)
        except Exception as exc:
            logger.warning("Background product embedding failed product_id=%s: %s", product_id, exc)
        finally:
            close_old_connections()

    threading.Thread(target=_run_embed, daemon=True).start()


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
    try:
        from discount.services.google_sheets_service import (
            should_auto_sync_order_to_google_sheets,
            sync_order_to_google_sheets,
        )
        if not should_auto_sync_order_to_google_sheets(instance):
            return
    except ImportError:
        return
    order_id = getattr(instance, "pk", None) or getattr(instance, "id", None)
    if not order_id:
        return

    def _run_sync():
        try:
            sync_order_to_google_sheets(order_id)
        except Exception as e:
            logger.exception("Background sync_order_to_google_sheets order_id=%s failed: %s", order_id, e)

    t = threading.Thread(target=_run_sync, daemon=True)
    t.start()
