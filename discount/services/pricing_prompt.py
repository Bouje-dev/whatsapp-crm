"""
Dynamic pricing / negotiation prompt blocks for the AI sales agent.

Centralizes backup_price validation so prompts never treat 0, null, or
price >= official as a negotiable floor (which caused free-product hallucinations).
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Optional

STANDARD_DIGITS_RULE = (
    "ALWAYS write numbers using standard Western digits (0-9), e.g. 199, 170 — "
    "NEVER Eastern Arabic-Indic numerals (١٩٩, ١٧٠)."
)


def _to_decimal(value: Any) -> Optional[Decimal]:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        s = str(value).strip()
        if not s:
            return None
        return Decimal(s)
    except (InvalidOperation, ValueError, TypeError):
        return None


def negotiation_floor_is_valid(product) -> bool:
    """
    True when backup_price exists, is > 0, and is strictly below official price.
    """
    if not product:
        return False
    official = _to_decimal(getattr(product, "price", None))
    backup = _to_decimal(getattr(product, "backup_price", None))
    if official is None or backup is None:
        return False
    if backup <= 0:
        return False
    return backup < official


def _official_and_floor(product) -> tuple[Optional[Decimal], Optional[Decimal], str]:
    """Return (official, floor, currency) for prompt interpolation."""
    currency = (getattr(product, "currency", None) or "MAD").strip() or "MAD"
    official = _to_decimal(getattr(product, "price", None))
    backup = _to_decimal(getattr(product, "backup_price", None)) if product else None
    return official, backup, currency


def build_context_isolation_rule(product) -> str:
    """Hard override so chat history cannot bleed pricing from a previous product."""
    if not product:
        return ""
    name = (getattr(product, "name", None) or "this product").strip()
    _, backup, currency = _official_and_floor(product)
    if negotiation_floor_is_valid(product) and backup is not None:
        floor_line = f"Your CURRENT floor price is {backup} {currency}."
    else:
        official, _, _ = _official_and_floor(product)
        floor_line = (
            f"Your CURRENT price is {official} {currency} (fixed — no backup floor)."
            if official is not None
            else "Use ONLY the official price from PRODUCT CONTEXT below."
        )
    return (
        "[CONTEXT ISOLATION RULE]: You are CURRENTLY selling the product: "
        f"{name}. {floor_line} "
        "CRITICAL: Completely IGNORE any other prices, floor prices, or backup limits "
        "mentioned earlier in the chat history. The past chat history might contain rules "
        "for different products. ONLY the limits of the CURRENT active product apply right now. "
        "Do not apply past product restrictions to this current transaction."
    )


def build_dynamic_pricing_protocol(product) -> str:
    """
    Per-product pricing protocol — natural conversational tone with hard boundaries.
    """
    if not product:
        return (
            "[VALUE-BASED PRICING]: Use only prices from PRODUCT CONTEXT. "
            "Never invent discounts or coupon codes. "
            + STANDARD_DIGITS_RULE
        )

    official, backup, currency = _official_and_floor(product)
    official_display = f"{official} {currency}" if official is not None else f"— {currency}"
    coupon_code = (getattr(product, "coupon_code", None) or "").strip().upper()
    coupon_hint = (
        f"If you use apply_discount, only the configured code '{coupon_code}' is valid. "
        if coupon_code
        else "Do not invent coupon codes (e.g. WELCOME10). "
    )

    if negotiation_floor_is_valid(product):
        floor_display = f"{backup} {currency}"
        protocol = f"""
[NEGOTIATION CAPABILITY]: The official price is {official_display}. Your absolute bottom line is {floor_display}.
- Act as a friendly, flexible Moroccan seller.
- If the user proposes a specific price (e.g. 170 {currency}) and it is GREATER THAN OR EQUAL to your bottom line ({backup}), ACCEPT IT enthusiastically and proceed to close the deal!
- If they ask for a general discount, offer a small, natural reduction — vary your wording; sound human, not scripted.
- NEVER reveal your bottom line. NEVER use fake coupon codes. {coupon_hint}
- {STANDARD_DIGITS_RULE}
""".strip()
    else:
        protocol = f"""
[VALUE-BASED PRICING]: The price is fixed at {official_display}. There is no backup price.
- If the user asks for a discount, gently and politely decline, but DO NOT sound like a robot.
- Explain the value (e.g. premium quality, instant delivery, full warranty) — use fresh phrasing each time.
- EXTREMELY IMPORTANT: NEVER repeat the exact same rejection phrase twice. If they insist, show empathy, use light humor, or pivot the conversation gracefully.
- Do NOT offer a lower amount, free product, or percentage off. {coupon_hint}
- {STANDARD_DIGITS_RULE}
""".strip()

    isolation = build_context_isolation_rule(product)
    if isolation:
        protocol = protocol + "\n\n" + isolation
    return protocol


def build_product_pricing_context_lines(product) -> list[str]:
    """Extra PRODUCT CONTEXT lines after official price (mode + internal floor + digits)."""
    if not product:
        return []
    _, backup, currency = _official_and_floor(product)
    lines = [STANDARD_DIGITS_RULE]
    if negotiation_floor_is_valid(product):
        lines.insert(0, "Pricing mode: FLEXIBLE (negotiation capability — see [NEGOTIATION CAPABILITY] block).")
        lines.append(
            f"Internal bottom line (never reveal to customer): {backup} {currency}"
        )
    else:
        lines.insert(0, "Pricing mode: VALUE-BASED (fixed price — see [VALUE-BASED PRICING] block).")
        lines.append("No backup price — listed official price is final.")
    return lines
