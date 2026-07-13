"""
Shared digital-product delivery (stock consume + WhatsApp text assembly).
Used by initial receipt approval and post-sale replacement approval.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


def consume_next_digital_stock(product, order) -> dict[str, Any]:
    """
    FIFO consume one unsold ``DigitalAssetStock`` row inside ``transaction.atomic``.

    Returns dict with keys: consumed_value, stock_format, stock_row_id (or empty).
    """
    if not product or not bool(getattr(product, 'is_digital', False)):
        return {}
    try:
        from discount.models import DigitalAssetStock
        with transaction.atomic():
            stock_row = (
                DigitalAssetStock.objects
                .select_for_update()
                .filter(product=product, is_sold=False)
                .order_by('id')
                .first()
            )
            if not stock_row:
                return {}
            plaintext = stock_row.get_asset_content()
            if not plaintext:
                logger.warning(
                    'consume_next_digital_stock: empty decrypt product=%s row=%s',
                    product.id, stock_row.id,
                )
                return {}
            stock_row.is_sold = True
            stock_row.order = order
            stock_row.sold_at = timezone.now()
            stock_row.save(update_fields=['is_sold', 'order', 'sold_at'])
            return {
                'consumed_value': plaintext,
                'stock_format': getattr(product, 'stock_format', None) or 'single',
                'stock_row_id': stock_row.id,
            }
    except Exception as exc:
        logger.warning(
            'consume_next_digital_stock failed order=%s product=%s: %s',
            getattr(order, 'order_id', None), getattr(product, 'id', None), exc,
        )
        return {}


def resolve_static_download_url(product, request=None) -> str:
    if not product:
        return ''
    if (getattr(product, 'digital_url', None) or '').strip():
        return product.digital_url.strip()
    if getattr(product, 'digital_file', None) and product.digital_file.name:
        try:
            if request:
                return request.build_absolute_uri(product.digital_file.url)
            return product.digital_file.url
        except Exception:
            return product.digital_file.url
    return ''


def build_fulfillment_text(
    public_body: str,
    consumed_value: str = '',
    stock_format: str = 'single',
    download_url: str = '',
) -> tuple[str, dict[str, str]]:
    """
    Build WhatsApp fulfilment text and encrypted asset field map.
    """
    asset_fields: dict[str, str] = {}
    fulfilment_text = public_body

    if consumed_value:
        if stock_format == 'combo':
            email_part, _, password_part = consumed_value.partition(':')
            email_part = email_part.strip()
            password_part = password_part.strip()
            asset_fields = {'email': email_part, 'password': password_part}
            fulfilment_text = (
                f'{public_body}\n\n'
                f'📧 {email_part}\n'
                f'🔑 {password_part}'
            )
        elif stock_format == 'iptv':
            val = consumed_value.strip()
            if val.lower().startswith('http'):
                asset_fields = {'link': val, 'iptv': val}
                fulfilment_text = f'{public_body}\n\n📺 IPTV\n🔗 {val}'
            else:
                asset_fields = {'iptv': val}
                fulfilment_text = f'{public_body}\n\n📺 IPTV\n{val}'
        else:
            asset_fields = {'license': consumed_value}
            fulfilment_text = f'{public_body}\n\n🔑 {consumed_value}'
    elif download_url:
        asset_fields = {'link': download_url}
        fulfilment_text = f'{public_body}\n\n🔗 {download_url}'

    return fulfilment_text, asset_fields


def build_public_body_for_delivery(
    order,
    channel,
    customer_phone,
    *,
    is_replacement: bool = False,
    product=None,
    consumed_value: str = '',
    download_url: str = '',
) -> str:
    from discount.services.fulfillment_messages import (
        get_localized_fulfillment_message,
        get_localized_support_replacement_message,
        resolve_fulfillment_language_code,
    )

    product = product or getattr(order, 'product', None)
    fulfillment_note = (getattr(product, 'fulfillment_message', None) or '').strip() if product else ''
    if fulfillment_note and not is_replacement:
        return fulfillment_note

    lang = resolve_fulfillment_language_code(
        order=order, channel=channel, customer_phone=customer_phone,
    )
    has_asset = bool(consumed_value or download_url)
    if is_replacement:
        return get_localized_support_replacement_message(lang, has_asset=has_asset)
    return get_localized_fulfillment_message(lang, has_asset=has_asset)
