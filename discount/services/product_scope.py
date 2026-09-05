"""
Tenant + WhatsApp-channel isolation for catalog products.

Dashboard products are stored with:
  - ``admin_id`` = store owner (never another account)
  - ``project``  = str(channel.id) (never another channel of the same account)

The AI catalog, search, media, and order tools MUST use the same scope.
"""
from __future__ import annotations

import logging

from django.db.models import Q

logger = logging.getLogger(__name__)


def _owner_id_from_channel(channel):
    if not channel:
        return None
    return getattr(channel, "owner_id", None) or getattr(getattr(channel, "owner", None), "id", None)


def _owner_channel_keys(owner_id) -> set[str]:
    from discount.models import WhatsAppChannel

    ids = WhatsAppChannel.objects.filter(owner_id=owner_id).values_list("id", flat=True)
    return {str(i) for i in ids}


def channel_catalog_queryset(channel):
    """
    Products this WhatsApp channel is allowed to sell.

    - Always scoped to ``channel.owner``.
    - If the owner has any products tagged to a channel id (dashboard style),
      only this channel's tagged products are returned.
    - Legacy stores whose products still use a free-text ``project`` name keep
      owner-wide visibility so a single-channel shop does not go empty.
    """
    from discount.models import Products

    if not channel:
        return Products.objects.none()
    owner_id = _owner_id_from_channel(channel)
    if not owner_id:
        return Products.objects.none()
    qs = Products.objects.filter(admin_id=owner_id)
    channel_key = str(getattr(channel, "id", "") or "")
    if not channel_key:
        return Products.objects.none()
    try:
        keys = _owner_channel_keys(owner_id)
        if keys and qs.filter(project__in=keys).exists():
            return qs.filter(project=channel_key)
    except Exception as exc:
        logger.warning("channel_catalog_queryset channel-tag check failed: %s", exc)
        return qs.filter(Q(project=channel_key) | Q(project__isnull=True) | Q(project=""))
    return qs


def product_belongs_to_channel(product, channel) -> bool:
    if not product or not channel:
        return False
    pk = getattr(product, "pk", None) or getattr(product, "id", None)
    if pk is None:
        return False
    return channel_catalog_queryset(channel).filter(pk=pk).exists()


def get_channel_product(channel, *, product_id=None, sku=None, name=None):
    """Resolve one product inside this channel's catalog, or None."""
    qs = channel_catalog_queryset(channel)
    if product_id is not None:
        try:
            return qs.filter(id=int(product_id)).first()
        except (TypeError, ValueError):
            return None
    if sku and str(sku).strip():
        hit = qs.filter(sku=str(sku).strip()).first()
        if hit:
            return hit
    if name and str(name).strip():
        return qs.filter(name__iexact=str(name).strip()).first()
    return None


def get_channel_product_for_order(channel, product_id):
    """
    Resolve a product for order creation.

    Tagged catalog hits win. Owner products that are *not* tagged to a
    different WhatsApp channel are also accepted so legacy ``project``
    names / empty tags still convert (the previous strict catalog miss
    was aborting real sales).
    """
    if not channel or product_id is None:
        return None
    hit = get_channel_product(channel, product_id=product_id)
    if hit:
        return hit
    owner_id = _owner_id_from_channel(channel)
    if not owner_id:
        return None
    from discount.models import Products
    from django.db.models import Q

    try:
        pid = int(product_id)
    except (TypeError, ValueError):
        return None
    row = Products.objects.filter(id=pid).filter(
        Q(admin_id=owner_id) | Q(admin__team_admin_id=owner_id)
    ).first()
    if not row:
        return None
    keys = _owner_channel_keys(owner_id)
    channel_key = str(getattr(channel, "id", "") or "")
    proj = str(getattr(row, "project", None) or "").strip()
    if proj and keys and proj in keys and proj != channel_key:
        logger.warning(
            "get_channel_product_for_order: product %s tagged to channel %s, not %s",
            pid, proj, channel_key,
        )
        return None
    logger.info(
        "get_channel_product_for_order: accepted owner product %s for channel %s (project=%r)",
        pid, channel_key, proj,
    )
    return row


def resolve_session_product(channel, *, product_id=None, session=None):
    """Prefer an explicit product_id, else the session active product — both channel-scoped."""
    prod = None
    if product_id is not None:
        prod = get_channel_product(channel, product_id=product_id)
    if prod is not None:
        return prod
    if session is None:
        return None
    active = getattr(session, "active_product", None)
    if active is not None and product_belongs_to_channel(active, channel):
        return active
    sid = getattr(session, "active_product_id", None)
    if sid:
        return get_channel_product(channel, product_id=sid)
    return None
