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
    DIGITAL_PRODUCT_PERSONA,
    IPTV_PRODUCT_PERSONA,
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

    The real database primary key is injected as [DB_PRODUCT_ID: X] so the LLM can pass the
    correct product_id when calling submit_customer_order — preventing hallucinated sequential IDs.
    """
    if not product:
        return ""
    db_product_id = getattr(product, "id", None) or getattr(product, "pk", None)
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
        # ── CRITICAL: real DB primary key ──────────────────────────────────────
        # The LLM MUST use this exact integer when calling submit_customer_order.
        # NEVER invent, guess, or use a sequential counter (1, 2, 3…) as product_id.
        f"[DB_PRODUCT_ID: {db_product_id}]  ← USE THIS EXACT NUMBER for product_id in submit_customer_order",
        f"Currency: **{currency}** (all prices and negotiation amounts below are in this currency).",
        f"Title: {title}",
        f"Description: {description}",
        f"Official price (quote this first): {price_str}",
    ]
    try:
        from discount.services.pricing_prompt import build_product_pricing_context_lines

        lines.extend(build_product_pricing_context_lines(product))
    except Exception as e:
        logger.warning("build_product_pricing_context_lines: %s", e)
        if backup_price is not None:
            lines.append(f"Backup price (legacy): {backup_price} {currency}")
    if coupon_code:
        lines.append(f"ONLY valid coupon for apply_discount (do not invent other codes): {coupon_code}")
    else:
        lines.append("Coupon codes: NONE configured — do not offer or invent any code (no WELCOME10, etc.).")
    if delivery and not getattr(product, "is_digital", False):
        lines.append(f"Delivery / shipping: {delivery}")
    if not getattr(product, "is_digital", False):
        _rp = (getattr(product, "return_policy", None) or "").strip()
        if _rp:
            lines.append(f"Return/Warranty Policy (authoritative): {_rp}")
        else:
            lines.append(
                "Return/Warranty Policy: Standard delivery — inspection before payment is "
                "NOT allowed unless courier permits."
            )
    if getattr(product, "is_digital", False):
        dtype = (getattr(product, "digital_product_type", None) or "").strip().lower()
        stock_fmt = (getattr(product, "stock_format", None) or "").strip().lower()
        if stock_fmt == "iptv" or dtype == "iptv":
            lines.append("Digital product type: IPTV subscription (Xtream / M3U delivery after payment).")
            lines.append(
                "Stock format: IPTV — deliver each sold line as Xtream credentials or an M3U link "
                "(one subscription per order)."
            )
        elif dtype == "key":
            lines.append("Digital product type: Activation key / licence code.")
        elif dtype:
            lines.append(f"Digital product type: {dtype}.")
    try:
        from ai_assistant.services import format_product_offer_tiers_block

        offer_txt = format_product_offer_tiers_block(product)
        if offer_txt:
            lines.append("")
            lines.append(offer_txt)
    except Exception as e:
        logger.warning("build_product_context_for_prompt: offer tiers: %s", e)
    return "\n".join(lines)


def _normalize_physical_category(raw_category):
    """Map stored category / aliases to a canonical physical persona key."""
    category = (raw_category or "").strip().lower()
    if category in CATEGORY_ALIASES:
        category = CATEGORY_ALIASES[category]
    if category == "general":
        category = "general_retail"
    if category not in VALID_CATEGORIES:
        category = "general_retail"
    return category


def detect_physical_product_persona(product):
    """
    Resolve the sales persona for a physical product.

    Uses the stored category when it is already specific; otherwise runs the
    lightweight AI classifier on name + description (Beauty, Electronics, etc.).
    """
    if not product:
        return "general_retail"
    stored = _normalize_physical_category(getattr(product, "category", None))
    if stored and stored != "general_retail":
        return stored
    name = (getattr(product, "name", None) or "").strip()
    description = (getattr(product, "description", None) or "").strip()
    try:
        from ai_assistant.product_classifier import classify_product, should_classify_product

        if should_classify_product(name, description):
            return _normalize_physical_category(classify_product(name, description))
    except Exception as e:
        logger.warning("detect_physical_product_persona: classification failed: %s", e)
    return stored or "general_retail"


def resolve_active_sales_persona(product):
    """
    Persona router: digital products bypass category AI entirely.

    Returns ``"iptv"`` for IPTV digital goods, ``"digital"`` for other digital,
    otherwise a canonical physical category key.
    """
    if not product:
        return "general_retail"
    if getattr(product, "is_digital", False):
        dtype = (getattr(product, "digital_product_type", None) or "").strip().lower()
        stock_fmt = (getattr(product, "stock_format", None) or "").strip().lower()
        if stock_fmt == "iptv" or dtype == "iptv":
            return "iptv"
        return "digital"
    return detect_physical_product_persona(product)


def build_persona_instruction_block(product) -> str:
    """Build the persona section injected into the sales system prompt."""
    if not product:
        return ""
    active_persona = resolve_active_sales_persona(product)
    if active_persona == "iptv":
        persona_text = IPTV_PRODUCT_PERSONA
    elif active_persona == "digital":
        persona_text = DIGITAL_PRODUCT_PERSONA
    else:
        persona_text = CATEGORY_PERSONAS.get(active_persona) or DEFAULT_PERSONA
    parts = [
        "## Persona",
        "CRITICAL: This persona MUST take over the conversation. Use it for every message; "
        "do not fall back to a generic sales tone.\n\n",
        persona_text,
    ]
    custom = (getattr(product, "seller_custom_persona", None) or "").strip()
    if custom:
        parts.extend(["\n\n## Seller instructions\n", custom])
    return "".join(parts)


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

    return build_persona_instruction_block(product)


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
    active = resolve_active_sales_persona(product)
    return PERSONA_CATEGORY_LABELS.get(active, "Store Manager")
