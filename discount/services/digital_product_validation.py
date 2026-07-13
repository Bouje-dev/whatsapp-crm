"""
Validation helpers for digital product creation (IPTV legal shield, sub-types).
"""
from __future__ import annotations

from discount.models import Products

_VALID_DIGITAL_TYPES = frozenset({
    Products.DIGITAL_PRODUCT_TYPE_ACCOUNT,
    Products.DIGITAL_PRODUCT_TYPE_KEY,
    Products.DIGITAL_PRODUCT_TYPE_IPTV,
})


def _truthy_post(val) -> bool:
    return (val or "").strip().lower() in ("true", "1", "yes", "on")


def parse_digital_product_fields(post, *, is_digital: bool) -> tuple[str | None, bool, str | None]:
    """
    Parse POST fields for digital sub-type and IPTV consent.

    IPTV is selected via ``stock_format=iptv`` (dynamic stock radio), not the
    account/key subtype radios. Returns (digital_product_type, legal_consent_iptv, error_message).
    """
    if not is_digital:
        return None, False, None

    stock_fmt = (post.get("stock_format") or "").strip().lower()
    if stock_fmt == Products.STOCK_FORMAT_IPTV:
        consent = _truthy_post(post.get("legal_consent_iptv"))
        if not consent:
            return Products.DIGITAL_PRODUCT_TYPE_IPTV, False, (
                "IPTV products require legal consent. You must accept the liability declaration "
                "before creating this product."
            )
        return Products.DIGITAL_PRODUCT_TYPE_IPTV, True, None

    raw_type = (post.get("digital_product_type") or "").strip().lower()
    if not raw_type or raw_type == Products.DIGITAL_PRODUCT_TYPE_IPTV:
        raw_type = Products.DIGITAL_PRODUCT_TYPE_ACCOUNT
    if raw_type not in _VALID_DIGITAL_TYPES:
        return None, False, (
            "Invalid digital product type. Choose Account or Activation Key."
        )

    return raw_type, False, None
