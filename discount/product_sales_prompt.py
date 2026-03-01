"""
Dynamic sales system prompt assembly (Intent Router).
Builds the final system message for the AI Sales Agent by concatenating:
  a) Rules (SALES_BASE_RULES from product_prompt_config)
  b) Product context (title, description, price)
  c) Persona instruction (category-based persona + optional seller_custom_persona via get_dynamic_persona_instruction)
"""
import logging

from discount.product_prompt_config import (
    CATEGORY_PERSONAS,
    DEFAULT_PERSONA,
    SALES_BASE_RULES,
    VALID_CATEGORIES,
)

logger = logging.getLogger(__name__)


def build_sales_system_prompt(product_id):
    """
    Generate the final system message for the AI Sales Agent when talking to a buyer.
    Layers: rules (SALES_BASE_RULES) + product context + persona_instruction (category persona + seller instructions).

    :param product_id: Primary key of the product (discount.models.Products).
    :return: Assembled prompt string. Returns rules only if product not found.
    """
    from discount.models import Products

    parts = [SALES_BASE_RULES]

    try:
        product = Products.objects.filter(pk=product_id).first()
    except Exception as e:
        logger.warning("build_sales_system_prompt: could not load product_id=%s: %s", product_id, e)
        return "\n\n".join(parts)

    if not product:
        return "\n\n".join(parts)

    # Layer b: Product context
    title = (getattr(product, "name", None) or "").strip() or "Product"
    description = (getattr(product, "description", None) or "").strip() or ""
    price = getattr(product, "price", None)
    currency = (getattr(product, "currency", None) or "MAD").strip() or "MAD"
    price_str = f"{price} {currency}" if price is not None else "—"
    product_context = (
        f"## Product context\n"
        f"Title: {title}\n"
        f"Description: {description}\n"
        f"Price: {price_str}"
    ) 
    parts.append(product_context)

    # Layer c + d: Persona and seller instructions (from get_dynamic_persona_instruction)
    persona_instruction = get_dynamic_persona_instruction(product_id)
    if persona_instruction:
        parts.append(persona_instruction)

    return "\n\n".join(parts)


def get_dynamic_persona_instruction(product_id):
    """
    Return only the category-based persona and seller instructions for a product.
    Use this when the main prompt already has product context (e.g. from flow node)
    and you only want to inject the dynamic persona layers (c + d).
    :param product_id: Primary key of the product (discount.models.Products).
    :return: Persona + seller instructions text, or empty string if product not found.
    """
    from discount.models import Products

    try:
        product = Products.objects.filter(pk=product_id).first()
    except Exception as e:
        logger.warning("get_dynamic_persona_instruction: could not load product_id=%s: %s", product_id, e)
        return ""

    if not product:
        return ""

    parts = []
    category = (getattr(product, "category", None) or "").strip().lower()
    if category not in VALID_CATEGORIES:
        category = "general_retail"
    if category == "general":
        category = "general_retail"
    persona_text = CATEGORY_PERSONAS.get(category) or DEFAULT_PERSONA
    parts.append(f"## Persona\n{persona_text}")

    custom = (getattr(product, "seller_custom_persona", None) or "").strip()
    if custom:
        parts.append(f"## Seller instructions\n{custom}")

    return "\n\n".join(parts) if parts else ""
