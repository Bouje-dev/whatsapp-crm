"""
Dynamic sales system prompt assembly (Intent Router).
Builds the final system message for the AI Sales Agent by concatenating:
  a) Rules (SALES_BASE_RULES from product_prompt_config)
  b) Product context (title, description, price)
  c) Persona instruction (category-based persona + optional seller_custom_persona via get_dynamic_persona_instruction)
"""
import logging

from discount.product_prompt_config import (
    CATEGORY_ALIASES,
    CATEGORY_PERSONAS,
    DEFAULT_PERSONA,
    PERSONA_CATEGORY_LABELS,
    SALES_BASE_RULES,
    VALID_CATEGORIES,
)

logger = logging.getLogger(__name__)


def _get_tenant_scoped_product(product_id, merchant=None):
    """Return product only when it belongs to the provided merchant."""
    from discount.models import Products

    if not product_id or not merchant:
        return None
    try:
        return Products.objects.filter(pk=int(product_id), admin=merchant).first()
    except Exception:
        return None


def build_product_context_for_prompt(product) -> str:
    """
    Authoritative PRODUCT CONTEXT block for the LLM: uses the product row's currency, price,
    backup price, delivery line, and offer tiers (same source as product creation / dashboard).
    """
    if not product:
        return ""
    title = (getattr(product, "name", None) or "").strip() or "Product"
    description = (getattr(product, "description", None) or "").strip() or ""
    price = getattr(product, "price", None)
    backup_price = getattr(product, "backup_price", None)
    coupon_code = (getattr(product, "coupon_code", None) or "").strip().upper()
    currency = (getattr(product, "currency", None) or "").strip() or "MAD"
    delivery = (getattr(product, "delivery_options", None) or "").strip()
    price_str = f"{price} {currency}" if price is not None else "—"
    lines = [
        "## PRODUCT CONTEXT (authoritative — use this currency and prices for all customer-facing quotes)",
        f"Currency: **{currency}** (all prices and negotiation amounts below are in this currency).",
        f"Title: {title}",
        f"Description: {description}",
        f"Price: {price_str}",
    ]
    if backup_price is not None:
        lines.append(f"Backup / negotiation floor price: {backup_price} {currency}")
    if coupon_code:
        lines.append(f"Preferred coupon code: {coupon_code}")
    if delivery:
        lines.append(f"Delivery / shipping: {delivery}")
    try:
        from ai_assistant.services import format_product_offer_tiers_block

        offer_txt = format_product_offer_tiers_block(product)
        if offer_txt:
            lines.append("")
            lines.append(offer_txt)
    except Exception as e:
        logger.warning("build_product_context_for_prompt: offer tiers: %s", e)
    return "\n".join(lines)


def build_sales_system_prompt(product_id, merchant=None):
    """
    Generate the final system message for the AI Sales Agent when talking to a buyer.
    Layers: rules (SALES_BASE_RULES) + product context + persona_instruction (category persona + seller instructions).

    :param product_id: Primary key of the product (discount.models.Products).
    :return: Assembled prompt string. Returns rules only if product not found.
    """
    parts = [SALES_BASE_RULES]

    try:
        product = _get_tenant_scoped_product(product_id, merchant=merchant)
    except Exception as e:
        logger.warning("build_sales_system_prompt: could not load product_id=%s: %s", product_id, e)
        return "\n\n".join(parts)

    if not product:
        return "\n\n".join(parts)

    # Layer b: Product context (currency + prices from Products row)
    product_context = build_product_context_for_prompt(product)
    if product_context:
        parts.append(product_context)

    # Layer c + d: Persona and seller instructions (from get_dynamic_persona_instruction)
    persona_instruction = get_dynamic_persona_instruction(product_id, merchant=merchant)
    if persona_instruction:
        parts.append(persona_instruction)

    return "\n\n".join(parts)


def get_dynamic_persona_instruction(product_id, merchant=None):
    """
    Return only the category-based persona and seller instructions for a product.
    Use this when the main prompt already has product context (e.g. from flow node)
    and you only want to inject the dynamic persona layers (c + d).
    :param product_id: Primary key of the product (discount.models.Products).
    :return: Persona + seller instructions text, or empty string if product not found.
    """
    try:
        product = _get_tenant_scoped_product(product_id, merchant=merchant)
    except Exception as e:
        logger.warning("get_dynamic_persona_instruction: could not load product_id=%s: %s", product_id, e)
        return ""

    if not product:
        return ""

    parts = []
    category = (getattr(product, "category", None) or "").strip().lower()
    if category in CATEGORY_ALIASES:
        category = CATEGORY_ALIASES[category]
    if category not in VALID_CATEGORIES:
        category = "general_retail"
    if category == "general":
        category = "general_retail"
    persona_text = CATEGORY_PERSONAS.get(category) or DEFAULT_PERSONA
    parts.append(
        "## Persona\n"
        "CRITICAL: This category persona MUST take over the conversation. Use it for every message; do not fall back to a generic sales tone.\n\n"
        f"{persona_text}"
    )

    custom = (getattr(product, "seller_custom_persona", None) or "").strip()
    if custom:
        parts.append(f"## Seller instructions\n{custom}")

    return "\n\n".join(parts) if parts else ""


def get_persona_category_label(product_id, merchant=None):
    """
    Return a short label for the persona category (e.g. "Beauty Consultant") for the given product.
    Used for internal notes like "AI agent {name} took over as {category}".
    """
    if not product_id:
        return "Sales Agent"
    try:
        product = _get_tenant_scoped_product(product_id, merchant=merchant)
    except Exception:
        return "Sales Agent"
    if not product:
        return "Sales Agent"
    category = (getattr(product, "category", None) or "").strip().lower()
    if category in CATEGORY_ALIASES:
        category = CATEGORY_ALIASES[category]
    if category not in VALID_CATEGORIES or category == "general":
        category = "general_retail"
    return PERSONA_CATEGORY_LABELS.get(category, "Store Manager")
