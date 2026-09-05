"""
Save order data extracted by AI (e.g. from GPT function calling or [ORDER_DATA: ...] tag).
Used by the AI voice / sales agent auto-reply flow.

ARCHITECTURE RULE: Do not use hardcoded arrays or regex to guess user intent from chat
messages. Always use LLM Tool descriptions and injected context to extract structured data.
This module validates and persists data; it does not interpret phrases like "same number".
"""
import json
import logging
import re
import traceback
import uuid
from datetime import timedelta
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone

from discount.models import SimpleOrder, Products, WhatsAppChannel, CustomUser, Contact

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Canonical anti-hallucination instruction for ALL backend failures of
# submit_customer_order. The LLM has historically guessed at causes ("product
# unavailable", "out of stock", "you must reorder") whenever it received a
# generic error. We hard-code this exact wording so that every system-side
# failure produces the SAME safe customer-facing behaviour.
#
# Used by handle_submit_order_tool() for:
#   • missing channel / store / seller configuration
#   • malformed arguments dict
#   • product lookup miss (Products.objects.filter(...).first() is None)
#   • DB INSERT exception (SimpleOrder.objects.create raised)
#   • catch-all FATAL TOOL ERROR
# ─────────────────────────────────────────────────────────────────────────────
SUBMIT_ORDER_SYSTEM_BUSY_INSTRUCTION: str = (
    "[SYSTEM: Order could not be saved this turn. A teammate was notified internally. "
    "STRICT CUSTOMER RULES: Do NOT mention failure, delay, technical issues, systems, "
    "or retrying. Do NOT say you will register the order, try again, or wait a minute. "
    "Do NOT claim the order is confirmed. Reply with one short natural line that only "
    "confirms the details you already have (name / city / product) and STOP. "
    "Never tell the customer the product is unavailable or out of stock.]"
)

# Only these keys may appear in submit_customer_order payload; strip any other keys (LLM hallucination).
ALLOWED_ORDER_KEYS = (
    "customer_name", "phone_number", "shipping_city", "shipping_address",
    "email_address", "final_agreed_price", "product_id",
)

_PRICE_FROM_TEXT_RE = re.compile(r"(\d+(?:[.,]\d+)?)")

# Checkout mode (product.checkout_mode) → required_order_fields for AI tool schema and validation
CHECKOUT_MODE_MAP = {
    "quick_lead":   ["customer_name", "phone_number"],
    "standard_cod": ["customer_name", "phone_number", "shipping_city"],
    "strict_cod":   ["customer_name", "phone_number", "shipping_city", "shipping_address"],
    # Digital products: no physical shipping — collect email for download link delivery.
    "digital":      ["customer_name", "email_address"],
    # Direct Sale: zero friction — AI submits immediately on purchase intent.
    # Empty list signals the instant-submit path in _build_order_memory_block.
    "direct_sale":  [],
}
CHECKOUT_MODE_LABELS = {
    "quick_lead":   "Quick Lead (Name & Phone only)",
    "standard_cod": "Standard COD (Name, Phone, City)",
    "strict_cod":   "Strict COD (Full Address)",
    "digital":      "Digital Delivery (Name & Email — no shipping address)",
    "direct_sale":  "Direct Sale (No information required — instant submit)",
}

# Fields that are considered valid for any checkout mode (extended with email_address)
_ALL_VALID_FIELDS = {
    "customer_name", "phone_number",
    "shipping_city", "shipping_address",
    "email_address",
}


def get_required_order_fields_for_product(product):
    """
    Resolve required order fields for a product.

    Priority order:
      0. checkout_mode == 'direct_sale'  → [] (instant submit, any product type).
      1. is_digital=True AND collect_customer_info=False  → [] (instant submit).
      2. is_digital=True (with collect_customer_info=True) → Name + Email.
      3. checkout_mode in CHECKOUT_MODE_MAP  → mapped field list.
      4. required_order_fields (JSONField)   → custom list stored on the product.
      5. Fallback  → standard COD defaults (Name, Phone, City, Address).

    An explicit empty list [] signals the instant-submit path in
    _build_order_memory_block (services.py).
    None means "not yet resolved" and triggers the default fallback.
    """
    if not product:
        return ["customer_name", "phone_number", "shipping_city", "shipping_address"]

    # 0. Direct Sale — highest priority, applies to ANY product type.
    #    checkout_mode='direct_sale' always returns [] regardless of is_digital flag.
    mode = (getattr(product, "checkout_mode", None) or "").strip()
    if mode == "direct_sale":
        return []

    # 1. Digital override — is_digital wins over checkout_mode (except direct_sale above)
    if getattr(product, "is_digital", False):
        # When seller opts out of collecting info, return an EMPTY list so the
        # AI submits the order immediately using only the WhatsApp phone number.
        if not getattr(product, "collect_customer_info", True):
            return []
        return list(CHECKOUT_MODE_MAP["digital"])

    # 2. Explicit checkout_mode
    if mode and mode in CHECKOUT_MODE_MAP:
        return list(CHECKOUT_MODE_MAP[mode])

    # 3. Custom JSONField list (validated against known field names)
    _raw = getattr(product, "required_order_fields", None)
    if isinstance(_raw, list):
        _filtered = [str(f) for f in _raw if isinstance(f, str) and f in _ALL_VALID_FIELDS]
        if _filtered:
            return _filtered

    # 4. Safe default
    return ["customer_name", "phone_number", "shipping_city", "shipping_address"]


PLACEHOLDER_ORDER_FIELD_RE = re.compile(
    r"^(?:"
    r"غير\s*معروف|"
    r"unknown|"
    r"n/?a|"
    r"none|null|"
    r"not\s*provided|"
    r"whatsapp\s*customer|"
    r"غ/م|"
    r"[\-—\.]+|"
    r"\?+"
    r")$",
    re.IGNORECASE,
)

HOW_TO_ORDER_RE = re.compile(
    r"(?:"
    r"كيفاش\s*(?:نطلب|نشري|ندير|ناخد|ordering)|"
    r"بغيت\s+نطلب|"
    r"how\s*(?:do|can|to)\s*(?:i|we)\s*(?:order|buy)|"
    r"comment\s*(?:commander|acheter)|"
    r"want\s+to\s+order"
    r")",
    re.IGNORECASE | re.UNICODE,
)


def looks_like_how_to_order_only(text: str) -> bool:
    """True when the customer asks how to order/buy — not a confirmed purchase."""
    body = (text or "").strip()
    if not body or not HOW_TO_ORDER_RE.search(body):
        return False
    if re.search(r"^(?:نعم|اه|ok|yes|أكيد|confirm|je\s+prends|j['']achète)\b", body, re.I | re.UNICODE):
        return False
    if re.search(
        r"(المدينة|مدينة|عنوان|address|city|casablanca|rabat|fes|marrakech|tanger|agadir)",
        body,
        re.I | re.UNICODE,
    ):
        return False
    return True


def is_placeholder_order_field(value) -> bool:
    s = (value or "").strip()
    if not s:
        return True
    return bool(PLACEHOLDER_ORDER_FIELD_RE.match(s))


def validate_submit_order_arguments(
    arguments,
    product,
    incoming_body="",
    customer_phone_from_chat="",
):
    """
    Return a JSON error string if submit_customer_order must be blocked, else None.
    """
    required = get_required_order_fields_for_product(product)
    if not required:
        return None

    if looks_like_how_to_order_only(incoming_body):
        return json.dumps({
            "status": "error",
            "success": False,
            "reason": "how_to_order_not_purchase",
            "instruction": (
                "The customer is asking HOW to order, not confirming a purchase. "
                "Do NOT call submit_customer_order. Explain the next step briefly in their language. "
                "The system will send the WhatsApp order form when appropriate."
            ),
            "message": "Customer has not provided order details yet.",
        }, ensure_ascii=False)

    args = arguments if isinstance(arguments, dict) else {}
    missing = []
    for field in required:
        if field == "phone_number":
            val = (args.get("phone_number") or customer_phone_from_chat or "").strip()
        elif field == "customer_name":
            val = (args.get("customer_name") or "").strip()
        elif field == "shipping_city":
            val = (args.get("shipping_city") or "").strip()
        elif field == "shipping_address":
            val = (args.get("shipping_address") or "").strip()
        elif field == "email_address":
            val = (args.get("email_address") or "").strip()
        else:
            val = (args.get(field) or "").strip()
        if is_placeholder_order_field(val):
            missing.append(field)

    if not missing:
        return None

    labels = {
        "customer_name": "full name",
        "phone_number": "phone number",
        "shipping_city": "city",
        "shipping_address": "address",
        "email_address": "email",
    }
    need = ", ".join(labels.get(f, f) for f in missing)
    return json.dumps({
        "status": "error",
        "success": False,
        "reason": "missing_required_fields",
        "missing_fields": missing,
        "instruction": (
            f"Required fields are missing or invalid: {need}. "
            "Do NOT register the order yet. Collect the missing details, or wait for the "
            "WhatsApp checkout form. Never invent placeholder values like 'unknown' or 'غير معروف'."
        ),
        "message": f"Missing required fields: {', '.join(missing)}",
    }, ensure_ascii=False)


def is_order_customer_info_complete(order, product=None):
    """True when saved order has all fields required for this product's checkout mode."""
    if not order:
        return False
    if product is None:
        product = getattr(order, "product", None)
    required = get_required_order_fields_for_product(product)
    if not required:
        return True

    city_raw = (getattr(order, "customer_city", None) or "").strip()
    city_part = city_raw.split("|")[0].strip() if city_raw else ""
    address_part = city_raw.split("|")[-1].strip() if "|" in city_raw else city_raw

    values = {
        "customer_name": getattr(order, "customer_name", None),
        "phone_number": getattr(order, "customer_phone", None),
        "shipping_city": city_part,
        "shipping_address": address_part,
        "email_address": getattr(order, "customer_email", None),
    }
    for field in required:
        if is_placeholder_order_field(values.get(field)):
            return False
    return True


def get_or_create_ai_agent_user(owner, agent_name=None):
    """
    Get or create a Virtual Team Member (CustomUser with is_bot=True) for the given merchant.
    Used so orders created by the AI are attributed to this bot user instead of the account owner.
    """
    if not owner:
        return None
    agent_name = (agent_name or "AI Agent").strip() or "AI Agent"
    # Slug for uniqueness: first word or sanitized agent_name (e.g. "Simo - AI Closer" -> "simo")
    slug = "".join(c for c in agent_name.split()[0].lower() if c.isalnum()) if agent_name else "default"
    if not slug:
        slug = "agent"
    slug = slug[:30]
    owner_id = getattr(owner, "id", None) or getattr(owner, "pk", None)
    if not owner_id:
        return None
    username = f"bot_agent_{owner_id}_{slug}"
    email = f"bot+{owner_id}+{slug}@internal.bot"
    try:
        bot = CustomUser.objects.filter(
            bot_owner_id=owner_id,
            is_bot=True,
            agent_role=agent_name,
        ).first()
        if bot:
            return bot
        # Ensure unique username/email in case of race
        if CustomUser.objects.filter(username=username).exists():
            bot = CustomUser.objects.filter(bot_owner_id=owner_id, is_bot=True).first()
            return bot
        bot = CustomUser.objects.create(
            username=username,
            email=email,
            is_bot=True,
            agent_role=agent_name,
            bot_owner_id=owner_id,
            is_active=True,
        )
        bot.set_unusable_password()
        bot.save()
        logger.info("Created virtual team member (bot) for owner %s: %s", owner_id, agent_name)
        return bot
    except Exception as e:
        logger.warning("get_or_create_ai_agent_user failed: %s; falling back to owner", e)
        return owner

# -----------------------------------------------------------------------------
# International phone validation (Order Extraction Tool guardrail)
# Accepts any country: digits only, 8–15 digits (E.164 allows up to 15).
# Examples: 0612345678 (MA), +966501234567 (SA), +33 6 12 34 56 78 (FR), 201234567890 (EG).
# Returns normalized digits (no + or spaces) for storage; no country-specific rules.
# -----------------------------------------------------------------------------

# Minimum and maximum length for a valid international number (digits only)
_PHONE_DIGITS_MIN = 8
_PHONE_DIGITS_MAX = 15


def validate_phone_international(phone):
    """
    Validate and normalize a phone number from any country.
    Accepts with or without country code, and with spaces/dashes/dots/plus.
    Returns (normalized_digits, None) if valid, or (None, error_message) if invalid.
    normalized_digits: digits only, no + (e.g. 212612345678, 966501234567, 0612345678).
    """
    if not phone or not isinstance(phone, str):
        return (None, "No phone number provided.")
    digits = re.sub(r"\D", "", phone.strip())
    if not digits:
        return (None, "Phone number is empty.")
    if len(digits) < _PHONE_DIGITS_MIN:
        return (
            None,
            "SYSTEM ERROR: The phone number is too short. "
            "Politely ask the customer to provide a valid phone number (with country code if possible, e.g. +XXX...).",
        )
    if len(digits) > _PHONE_DIGITS_MAX:
        digits = digits[:_PHONE_DIGITS_MAX]
    return (digits, None)


def validate_moroccan_phone(phone):
    """
    Validate and normalize a Moroccan mobile number (legacy / Morocco-only flows).
    Accepts with or without country code (+212). Returns (normalized_10_digits, None) or (None, error_message).
    """
    normalized, err = validate_phone_international(phone)
    if err:
        return (None, err)
    digits = normalized
    # With country code: 212 + 6/7 + 8 digits = 12 digits
    if digits.startswith("212") and len(digits) >= 12:
        digits = digits[3:12]
    if len(digits) == 10 and digits.startswith(("06", "07")):
        pass
    elif len(digits) == 10 and digits[0] in ("6", "7"):
        digits = "0" + digits[0] + digits[1:9]
    elif len(digits) == 9 and digits[0] in ("6", "7"):
        digits = "0" + digits
    elif len(digits) > 10 and not digits.startswith("212"):
        tail = digits[-9:] if len(digits) >= 9 else digits
        if tail and tail[0] in ("6", "7") and len(tail) == 9:
            digits = "0" + tail
        else:
            digits = digits[:10]
    else:
        digits = digits[:10] if len(digits) > 10 else digits
    if len(digits) != 10 or digits[0] != "0" or digits[1] not in ("6", "7") or not digits[2:].isdigit() or len(digits[2:]) != 8:
        return (
            None,
            "SYSTEM ERROR: The phone number is not a valid Moroccan mobile. "
            "Politely ask for 06XXXXXXXX, 07XXXXXXXX, or +212 6XX...",
        )
    return (digits, None)


def _safe_order_arg(arguments, key, default=""):
    """Null-safe extraction: checkout_mode may omit fields (e.g. quick_lead has no shipping_*). Never crash on missing or None."""
    if not isinstance(arguments, dict):
        return default or ""
    val = arguments.get(key)
    if val is None:
        return default or ""
    try:
        return (str(val).strip() or default) or ""
    except (TypeError, AttributeError):
        return default or ""


def _parse_price_from_tool_arg(raw):
    """Parse final_agreed_price from int/float/Decimal/str (e.g. 169, '169', '169 MAD')."""
    from discount.services.pricing_prompt import _to_decimal

    if raw is None:
        return None
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float, Decimal)):
        return _to_decimal(raw)
    s = str(raw).strip()
    if not s:
        return None
    direct = _to_decimal(s)
    if direct is not None:
        return direct
    m = _PRICE_FROM_TEXT_RE.search(s.replace(",", "."))
    if m:
        return _to_decimal(m.group(1))
    return None


def _quantize_order_price(value):
    """Fit negotiated price into SimpleOrder.price (DecimalField max_digits=10, decimal_places=2)."""
    try:
        dec = Decimal(str(value))
    except Exception:
        return None
    try:
        return dec.quantize(Decimal("0.01"))
    except Exception:
        return dec


def _coerce_submit_order_arguments(arguments=None, final_agreed_price=None, **kwargs):
    """
    Normalize tool payload whether the caller passes a dict, explicit kwargs,
    or a mix (prevents TypeError from unexpected keyword arguments).
    """
    base = dict(arguments) if isinstance(arguments, dict) else {}
    for key in ALLOWED_ORDER_KEYS:
        if key in kwargs and kwargs[key] is not None:
            base[key] = kwargs[key]
    if final_agreed_price is not None and base.get("final_agreed_price") is None:
        base["final_agreed_price"] = final_agreed_price
    # LLM occasionally aliases price → final_agreed_price
    if base.get("final_agreed_price") is None and kwargs.get("price") is not None:
        base["final_agreed_price"] = kwargs.get("price")
    if base.get("final_agreed_price") is None and base.get("price") is not None:
        base["final_agreed_price"] = base.get("price")
    return base


def _resolve_final_agreed_price(arguments, product):
    """
    Parse and validate final_agreed_price from the AI tool call.

    Returns (Decimal price, None) on success or (None, error_message) on failure.
    Falls back to catalog price when the field is missing (legacy / model slip).
    """
    from discount.services.pricing_prompt import negotiation_floor_is_valid, _to_decimal

    official = _to_decimal(getattr(product, "price", None))
    currency = (getattr(product, "currency", None) or "MAD").strip() or "MAD"
    raw = arguments.get("final_agreed_price") if isinstance(arguments, dict) else None

    if raw is None or (isinstance(raw, str) and not str(raw).strip()):
        if official is not None and official > 0:
            logger.warning(
                "submit_customer_order: final_agreed_price missing — falling back to catalog price %s %s",
                official, currency,
            )
            return _quantize_order_price(official), None
        return None, (
            "final_agreed_price is missing. Pass the exact amount the customer agreed to pay "
            "(negotiated or list price from PRODUCT CONTEXT) in final_agreed_price."
        )

    agreed = _parse_price_from_tool_arg(raw)
    if agreed is None or agreed <= 0:
        if official is not None and official > 0:
            logger.warning(
                "submit_customer_order: could not parse final_agreed_price=%r — falling back to catalog %s",
                raw, official,
            )
            return _quantize_order_price(official), None
        return None, (
            "final_agreed_price is invalid. Pass a positive number — the exact amount the "
            "customer agreed to pay in this conversation."
        )

    agreed = _quantize_order_price(agreed)
    if agreed is None or agreed <= 0:
        return None, "final_agreed_price is invalid after normalization."

    if official is not None and official > 0 and agreed > official:
        logger.info(
            "submit_customer_order: final_agreed_price %s > catalog %s — capping at catalog",
            agreed, official,
        )
        agreed = _quantize_order_price(official)

    if negotiation_floor_is_valid(product):
        backup = _to_decimal(getattr(product, "backup_price", None))
        if backup is not None and agreed < backup:
            return None, (
                f"The agreed price {agreed} {currency} is below the merchant's minimum "
                f"({backup} {currency}). Pass final_agreed_price at or above {backup}."
            )
    elif official is not None and official > 0 and agreed < official:
        logger.warning(
            "submit_customer_order: fixed-price product — agreed %s < catalog %s; using catalog price",
            agreed, official,
        )
        agreed = _quantize_order_price(official)

    return agreed, None


def handle_submit_order_tool(
    arguments=None,
    session_product_id=None,
    session_seller_id=None,
    channel=None,
    customer_phone_from_chat=None,
    final_agreed_price=None,
    incoming_body=None,
    **kwargs,
):
    """
    Bulletproof submit_customer_order handler.

    - Static schema: product_id, customer_name, phone_number, final_agreed_price;
      shipping_city and shipping_address optional.
    - Accepts tool args as a dict and/or explicit keyword parameters (final_agreed_price, etc.).
    - Asynchronous UX: caller sends the transitional WhatsApp message immediately before calling this handler.
    - DB-safe: shipping_city and shipping_address are always coerced to empty strings (no NULL crashes).
    - Feedback loop: ALWAYS returns a JSON string for the LLM to read (never raises to the caller).
    """
    try:
        arguments = _coerce_submit_order_arguments(
            arguments,
            final_agreed_price=final_agreed_price,
            **kwargs,
        )
        logger.info("TOOL CALLED: Raw arguments received -> %s", arguments)

        if not channel or not session_seller_id:
            logger.error(
                "submit_customer_order: missing channel/product/seller (channel=%s, product_id=%s, seller_id=%s)",
                getattr(channel, "id", None),
                session_product_id,
                session_seller_id,
            )
            return json.dumps({
                "status": "error",
                "success": False,
                "reason": "channel_or_seller_missing",
                "message": SUBMIT_ORDER_SYSTEM_BUSY_INSTRUCTION,
            }, ensure_ascii=False)

        if not isinstance(arguments, dict):
            logger.error("submit_customer_order: invalid arguments type (%s)", type(arguments))
            return json.dumps({
                "status": "error",
                "success": False,
                "reason": "invalid_arguments_type",
                "message": SUBMIT_ORDER_SYSTEM_BUSY_INSTRUCTION,
            }, ensure_ascii=False)

        # ── Parse raw arguments ───────────────────────────────────────────────
        customer_name    = _safe_order_arg(arguments, "customer_name",    "")
        phone_number     = _safe_order_arg(arguments, "phone_number",     "")
        shipping_city    = _safe_order_arg(arguments, "shipping_city",    "")
        shipping_address = _safe_order_arg(arguments, "shipping_address", "")
        email_address    = _safe_order_arg(arguments, "email_address",    "")

        raw_product_id = arguments.get("product_id")
        tool_product_id = None
        if raw_product_id is not None:
            try:
                tool_product_id = int(raw_product_id)
            except (TypeError, ValueError):
                # LLM hallucinated a non-numeric product_id. Treat as
                # validation prompt (not a system error) so the AI can
                # ask the user to pick a real product from the catalog.
                return json.dumps({
                    "status": "error",
                    "success": False,
                    "reason": "invalid_product_id_format",
                    "message": (
                        "product_id is invalid. Ask the user clearly which product they want "
                        "from the catalog, then use the correct numeric ID. Do NOT tell the user "
                        "the product is unavailable or out of stock."
                    ),
                }, ensure_ascii=False)

        # ── product_id is always required ─────────────────────────────────────
        effective_product_id = tool_product_id or session_product_id
        if not effective_product_id:
            return json.dumps({
                "status": "error",
                "success": False,
                "reason": "missing_product_id",
                "message": (
                    "product_id is missing. Ask the user exactly which product they want to order "
                    "from the catalog, then call the tool again with that product_id. Do NOT tell "
                    "the user the product is unavailable or out of stock."
                ),
            }, ensure_ascii=False)

        # ── Phone is always required (WhatsApp sender = guaranteed fallback) ──
        phone_to_use = (phone_number or customer_phone_from_chat or "").strip()
        if not phone_to_use:
            return json.dumps({
                "status": "error",
                "success": False,
                "message": "Phone number is missing. Politely ask the user to confirm or send their phone number (with country code).",
            }, ensure_ascii=False)

        normalized_phone, phone_error = validate_phone_international(phone_to_use)
        if phone_error:
            return json.dumps({
                "status": "error",
                "success": False,
                "reason": "invalid_phone",
                "message": phone_error,
            }, ensure_ascii=False)

        # ── Resolve product & store (must happen before name validation so
        #    we can determine the fulfillment mode for this specific product) ──
        from discount.services.product_scope import get_channel_product

        product = get_channel_product(channel, product_id=effective_product_id)
        if product and getattr(product, "admin_id", None) != session_seller_id:
            logger.error(
                "submit_customer_order: product_id=%s rejected (owner mismatch seller=%s)",
                effective_product_id, session_seller_id,
            )
            product = None
        if not product:
            logger.error(
                "submit_customer_order: product_id=%s not in channel %s catalog for seller %s",
                effective_product_id, getattr(channel, "id", None), session_seller_id,
            )
            return json.dumps({
                "status": "error",
                "success": False,
                "reason": "product_lookup_miss",
                "message": SUBMIT_ORDER_SYSTEM_BUSY_INSTRUCTION,
            }, ensure_ascii=False)

        store = getattr(channel, "owner", None)
        if not store or getattr(store, "id", None) != session_seller_id:
            logger.error(
                "submit_customer_order: store mismatch (channel.owner_id=%s, session_seller_id=%s)",
                getattr(store, "id", None), session_seller_id,
            )
            return json.dumps({
                "status": "error",
                "success": False,
                "reason": "store_mismatch",
                "message": SUBMIT_ORDER_SYSTEM_BUSY_INSTRUCTION,
            }, ensure_ascii=False)

        # ── Determine fulfillment mode from product settings ─────────────────
        _is_digital      = bool(getattr(product, "is_digital", False))
        _collect_info    = bool(getattr(product, "collect_customer_info", True))
        _checkout_mode   = (getattr(product, "checkout_mode", None) or "").strip()

        # direct_sale: no customer info needed regardless of product type
        is_direct_sale   = (_checkout_mode == "direct_sale") or (_is_digital and not _collect_info)
        # digital + collect name & email
        is_digital_info  = _is_digital and _collect_info and not is_direct_sale
        # standard physical order
        is_physical      = not _is_digital

        # ── Conditional name validation (skip for direct-sale digital orders) ─
        if not is_direct_sale and not customer_name:
            return json.dumps({
                "status": "error",
                "success": False,
                "reason": "missing_customer_name",
                "message": (
                    "Customer name is missing. Politely ask the user to share their full name. "
                    "Do NOT tell the user the product is unavailable or out of stock."
                ),
            }, ensure_ascii=False)

        blocked = validate_submit_order_arguments(
            arguments,
            product,
            incoming_body=(incoming_body or kwargs.get("incoming_body") or ""),
            customer_phone_from_chat=customer_phone_from_chat,
        )
        if blocked:
            return blocked

        if is_placeholder_order_field(customer_name):
            return json.dumps({
                "status": "error",
                "success": False,
                "reason": "invalid_customer_name",
                "message": (
                    "Customer name is missing or invalid. Ask for their real full name. "
                    "Never use placeholders like 'unknown' or 'غير معروف'."
                ),
            }, ensure_ascii=False)

        logger.info(
            "VALIDATION PASSED: mode=direct_sale=%s digital_info=%s physical=%s "
            "name=%s phone=%s city=%s address=%s email=%s final_agreed_price=%s",
            is_direct_sale, is_digital_info, is_physical,
            customer_name, normalized_phone, shipping_city, shipping_address, email_address,
            arguments.get("final_agreed_price"),
        )

        price, price_error = _resolve_final_agreed_price(arguments, product)
        if price_error:
            return json.dumps({
                "status": "error",
                "success": False,
                "reason": "invalid_final_agreed_price",
                "message": price_error,
            }, ensure_ascii=False)

        # Database insertion with strict try/except
        try:
            logger.info(
                "DB INSERT ATTEMPT... (product_id=%s, customer=%s, price=%s)",
                effective_product_id, customer_name or normalized_phone, price,
            )

            order_agent = get_or_create_ai_agent_user(store, agent_name="AI Agent") or store

            order_id = str(uuid.uuid4())[:8]
            while SimpleOrder.objects.filter(order_id=order_id).exists():
                order_id = str(uuid.uuid4())[:8]

            _ord_cur = (getattr(product, "currency", None) or "").strip() or "MAD"

            # ── Build field values per mode ───────────────────────────────────
            if is_direct_sale:
                # Direct Sale: phone only, no name/address/email needed
                _cname  = None
                _cemail = None
                _ccity  = ""
                _status = "pending_payment"

            elif is_digital_info:
                # Digital + collect info: name + email; no physical address
                _cname  = str(customer_name)[:200]
                _cemail = str(email_address)[:254] if email_address else None
                _ccity  = ""
                _status = "pending_payment"

            else:
                # Physical: name + city/address; no email
                customer_city_display = " | ".join(
                    filter(None, [shipping_city.strip(), shipping_address.strip()])
                )
                _cname  = str(customer_name)[:200]
                _cemail = None
                _ccity  = customer_city_display[:100]
                _status = "pending"

            order = SimpleOrder.objects.create(
                product=product,
                agent=order_agent,
                channel=channel,
                sku=str(getattr(product, "sku", "") or "")[:100],
                product_name=str(getattr(product, "name", "") or "")[:200],
                customer_name=_cname,
                customer_phone=str(normalized_phone)[:20],
                customer_email=_cemail,
                customer_city=_ccity,
                is_digital=_is_digital,
                order_id=order_id,
                status=_status,
                created_at=timezone.now(),
                price=price,
                currency=_ord_cur,
                quantity=Decimal("1"),
                created_by_ai=True,
                created_by_bot_session=(f"submit_order:{getattr(channel, 'id', '')}:{normalized_phone}"[:100] or None),
                sheets_export_status="pending",
            )

            logger.info("DB SUCCESS: Order ID -> %s", order_id)

            try:
                from discount.whatssapAPI.follow_up import cancel_pending_follow_up_tasks_for_customer
                cancel_pending_follow_up_tasks_for_customer(channel, normalized_phone)
            except Exception as e:
                logger.warning("cancel_pending_follow_up_tasks_for_customer: %s", e)

            try:
                if order:
                    _notify_owner_order_created(channel, order)
                contact = Contact.objects.filter(channel=channel).filter(phone=normalized_phone).first()
                if not contact and len(normalized_phone) >= 8:
                    contact = Contact.objects.filter(channel=channel).filter(phone__endswith=normalized_phone[-8:]).first()
                if contact:
                    contact.pipeline_stage = Contact.PipelineStage.CLOSED
                    contact.save(update_fields=["pipeline_stage"])
            except Exception as e:
                logger.warning("submit_customer_order: contact pipeline update failed: %s", e)

            # ────────────────────────────────────────────────────────────────
            # Success response — forked by product type.
            # PHYSICAL: keep the original return verbatim so the existing
            #   COD confirmation flow (format_order_confirmation → truck-emoji
            #   copy) keeps working unchanged.
            # DIGITAL: return a ready-to-send Moroccan-Darija payment-request
            #   message built from the store's active StorePaymentMethod rows.
            # ────────────────────────────────────────────────────────────────
            if not _is_digital:
                # Physical (COD) flow — UNCHANGED behaviour: short directive
                # so the existing format_order_confirmation() flow can paint
                # the customer-facing truck-emoji confirmation downstream.
                # `is_digital: false` is added explicitly so the router can
                # branch on outcome.get("is_digital", False) without having
                # to re-query the SimpleOrder row.
                return json.dumps({
                    "status": "success",
                    "success": True,
                    "is_digital": False,
                    "message": "Order saved successfully. Confirm the order with the customer now.",
                    "order_id": order_id,
                }, ensure_ascii=False)

            # Defensive: guarantee pending_payment even if a future code path
            # forgets to set it in the create() call above.
            try:
                if (order.status or "") != "pending_payment":
                    order.status = "pending_payment"
                    order.save(update_fields=["status"])
            except Exception as _status_err:
                logger.warning(
                    "submit_customer_order: could not enforce pending_payment for order_id=%s: %s",
                    order_id, _status_err,
                )

            # Pull the merchant's active payout accounts. Lazy import keeps
            # the physical branch untouched if StorePaymentMethod ever moves.
            payment_lines = []
            try:
                from discount.models import StorePaymentMethod
                active_methods = list(
                    StorePaymentMethod.objects
                    .filter(owner=store, is_active=True)
                    .order_by("provider_name", "id")
                )
                for pm in active_methods:
                    try:
                        formatted = (pm.format_for_ai() or "").strip()
                    except Exception:
                        # Hand-roll a line if format_for_ai() blows up
                        # (e.g. decryption error on a single row).
                        try:
                            identifier = pm.get_account_details() or ""
                        except Exception:
                            identifier = ""
                        label = (getattr(pm, "label", "") or "").strip() or "Payment Method"
                        if pm.is_bank:
                            holder = (pm.account_holder_name or "").strip()
                            prefix = f"{holder} — " if holder else ""
                            formatted = f"{label}: {prefix}RIB {identifier}".strip()
                        else:
                            formatted = f"{label} Email: {identifier}".strip()
                    if formatted:
                        payment_lines.append(f"• {formatted}")
            except Exception as _pm_err:
                logger.warning(
                    "submit_customer_order: failed to load StorePaymentMethod for store=%s: %s",
                    getattr(store, "id", None), _pm_err,
                )

            # Build total = price * quantity. Quantity is Decimal('1') for
            # AI-submitted orders today, but we compute defensively anyway.
            try:
                _qty = order.quantity if order.quantity is not None else Decimal("1")
                _unit = order.price if order.price is not None else Decimal("0")
                total_amount = (Decimal(str(_unit)) * Decimal(str(_qty)))
            except Exception:
                total_amount = Decimal(str(order.price or "0"))
            try:
                if total_amount == total_amount.to_integral_value():
                    total_display = f"{int(total_amount)}"
                else:
                    total_display = f"{total_amount:.2f}"
            except Exception:
                total_display = str(total_amount)
            currency_label = (order.currency or "MAD").strip() or "MAD"
            product_display = (
                (order.product_name or "").strip()
                or (getattr(product, "name", "") or "").strip()
                or "—"
            )

            # Sentinel-wrap the entire payment block so:
            #   (1) the LLM is instructed to keep digits as digits (via the
            #       AWAITING_PAYMENT_RECEIPT banner + Direct Sale prompt rule),
            #   (2) VoiceFormatterMiddleware bypasses gpt-4o-mini reformatting,
            #   (3) the WhatsApp router forces type:text delivery regardless of
            #       the node's response_mode or channel.ai_voice_enabled.
            # Imported lazily so the physical branch can never accidentally
            # trigger ai_assistant.services import chain.
            try:
                from ai_assistant.services import NO_TTS_OPEN, NO_TTS_CLOSE
            except Exception:
                # Safe fallback — must match the canonical markers exactly.
                NO_TTS_OPEN, NO_TTS_CLOSE = "[NO_TTS]", "[/NO_TTS]"

            if payment_lines:
                payment_block = "\n".join(payment_lines)
                digital_message = (
                    f"{NO_TTS_OPEN}\n"
                    "✅ تم تسجيل طلبك بنجاح!\n"
                    f"المنتج: {product_display}\n"
                    f"المبلغ المطلوب تحويله: {total_display} {currency_label}\n\n"
                    "لإتمام الطلب واستلام منتجك الرقمي، المرجو تحويل المبلغ "
                    "لأحد حساباتنا التالية:\n"
                    f"{payment_block}\n\n"
                    "⚠️ ملي تصيفط الفلوس، عفاك صور لينا الوصل (Screenshot) "
                    "وصيفطو هنا باش نأكدو ليك الطلبية ونصيفطو ليك المنتج "
                    "ديالك دابا.\n"
                    f"{NO_TTS_CLOSE}"
                )
            else:
                # No payment methods configured yet — do NOT invent fake
                # account details. Tell the AI to bridge to a human.
                # Still wrap in sentinels so the amount/product name digits
                # are preserved if the merchant later asks.
                logger.warning(
                    "submit_customer_order: digital order %s saved but store %s "
                    "has no active StorePaymentMethod — cannot send payout details.",
                    order_id, getattr(store, "id", None),
                )
                digital_message = (
                    f"{NO_TTS_OPEN}\n"
                    "✅ تم تسجيل طلبك بنجاح!\n"
                    f"المنتج: {product_display}\n"
                    f"المبلغ المطلوب تحويله: {total_display} {currency_label}\n\n"
                    "⚠️ غادي يتواصل معاك أحد موظفينا فأقرب وقت باش يصيفط ليك "
                    "تفاصيل الدفع وتكمل الطلبية ديالك.\n"
                    f"{NO_TTS_CLOSE}"
                )

            # `next_state` is consumed by the router immediately after this
            # tool returns; it transitions the session FSM to
            # AWAITING_PAYMENT_RECEIPT so the next customer message is
            # interpreted as a payment receipt (not a fresh order intent).
            # `force_text_delivery` + `disable_tts_reformat` are belt-and-
            # braces flags so a future caller that doesn't recognise the
            # [NO_TTS] sentinels can still pick the right transport.
            return json.dumps({
                "status": "success",
                "success": True,
                "is_digital": True,
                "awaiting_payment_receipt": True,
                "next_state": "AWAITING_PAYMENT_RECEIPT",
                "skip_format_order_confirmation": True,
                "force_text_delivery": True,
                "disable_tts_reformat": True,
                "message": digital_message,
                "order_id": order_id,
            }, ensure_ascii=False)

        except Exception as db_err:
            err_text = f"Error creating order: {db_err}"
            logger.error("DB INSERT ERROR in submit_customer_order -> %s", db_err)
            logger.error("DB INSERT ERROR (stack) -> %s", traceback.format_exc())
            return json.dumps({
                "status": "error",
                "success": False,
                "reason": "db_insert_failed",
                "message": SUBMIT_ORDER_SYSTEM_BUSY_INSTRUCTION,
            }, ensure_ascii=False)

    except Exception as e:
        err_text = f"Error creating order: {e}"
        logger.error("FATAL TOOL ERROR in submit_customer_order -> %s", e)
        logger.error("FATAL TOOL ERROR (stack) -> %s", traceback.format_exc())
        return json.dumps({
            "status": "error",
            "success": False,
            "reason": "fatal_tool_exception",
            "message": SUBMIT_ORDER_SYSTEM_BUSY_INSTRUCTION,
        }, ensure_ascii=False)


def handle_add_upsell_tool(arguments, channel):
    """
    UPDATE an existing order to add an upsell item (same package, same shipment).
    Appends the new item name to product_name, adds price, increments quantity.
    Returns a JSON string for the LLM context.
    """
    try:
        logger.info("UPSELL TOOL CALLED: args -> %s", arguments)

        if not isinstance(arguments, dict):
            return json.dumps({"status": "error", "success": False,
                               "message": "Invalid arguments. Ask the user to confirm the upsell."}, ensure_ascii=False)

        order_id = _safe_order_arg(arguments, "order_id", "")
        new_item_name = _safe_order_arg(arguments, "new_item_name", "")
        raw_price = arguments.get("new_item_price")

        if not order_id:
            return json.dumps({"status": "error", "success": False,
                               "message": "order_id is missing. You should have the order_id from the previous order in your context."}, ensure_ascii=False)
        if not new_item_name:
            return json.dumps({"status": "error", "success": False,
                               "message": "new_item_name is missing. Ask the user which product they want to add."}, ensure_ascii=False)

        try:
            new_price = Decimal(str(raw_price or "0"))
            if new_price < 0:
                new_price = Decimal("0")
        except Exception:
            new_price = Decimal("0")

        order = SimpleOrder.objects.filter(order_id=order_id).first()
        if not order:
            logger.error("UPSELL: order_id=%s not found", order_id)
            return json.dumps({"status": "error", "success": False,
                               "message": "Order not found. The order_id may be incorrect."}, ensure_ascii=False)

        if channel and order.channel_id and order.channel_id != channel.id:
            logger.error("UPSELL: order channel mismatch (order.channel=%s, current=%s)", order.channel_id, channel.id)
            return json.dumps({"status": "error", "success": False,
                               "message": "Order does not belong to this channel."}, ensure_ascii=False)

        if channel:
            from discount.services.product_scope import get_channel_product
            from discount.services.product_search import find_matching_product

            upsell_product = get_channel_product(channel, name=new_item_name.strip())
            if not upsell_product:
                upsell_product = find_matching_product(new_item_name.strip(), channel=channel)
            if not upsell_product:
                logger.error(
                    "UPSELL: item %r is not in channel %s catalog",
                    new_item_name, getattr(channel, "id", None),
                )
                return json.dumps({
                    "status": "error",
                    "success": False,
                    "message": "That add-on is not in this store's catalog. Offer a product from this channel only.",
                }, ensure_ascii=False)
            new_item_name = (getattr(upsell_product, "name", None) or new_item_name).strip()

        old_product_name = (order.product_name or "").strip()
        old_price = order.price or Decimal("0")
        old_quantity = order.quantity or Decimal("1")

        order.product_name = f"{old_product_name} + {new_item_name.strip()}"[:200]
        order.price = old_price + new_price
        order.quantity = old_quantity + Decimal("1")

        if order.sheets_export_status == "success":
            order.sheets_export_status = "pending"

        order.save(update_fields=["product_name", "price", "quantity", "sheets_export_status"])

        logger.info("UPSELL DB SUCCESS: order_id=%s, new total=%s, items=%s",
                     order_id, order.price, order.product_name)

        try:
            _resync_upsell_to_google_sheets(order)
        except Exception as gs_err:
            logger.warning("UPSELL Google Sheets re-sync: %s", gs_err)

        return json.dumps({
            "status": "success",
            "success": True,
            "message": f"Upsell added! The order now contains: {order.product_name}. New total: {order.price}. Confirm this with the customer.",
            "order_id": order_id,
            "updated_product_name": order.product_name,
            "updated_price": str(order.price),
        }, ensure_ascii=False)

    except Exception as e:
        logger.error("FATAL UPSELL TOOL ERROR -> %s", e)
        logger.error("FATAL UPSELL TOOL ERROR (stack) -> %s", traceback.format_exc())
        return json.dumps({"status": "error", "success": False,
                           "message": "System error adding the upsell. Tell the user there was a glitch."}, ensure_ascii=False)


_NOTE_CATEGORY_CANONICAL = {
    "delivery_time": "delivery_time",
    "alternate_phone": "alternate_phone",
    "general_instruction": "general_instruction",
    "general": "general_instruction",
}


def _first_valid_phone_in_text(text):
    """Extract first internationally-valid phone digit sequence from free-form note text."""
    if not text or not isinstance(text, str):
        return None
    for chunk in re.findall(r"\+?[\d\s\-\.]{8,24}", text):
        normalized, err = validate_phone_international(chunk)
        if not err and normalized:
            return normalized
    digits_only = re.sub(r"\D", "", text)
    if len(digits_only) >= _PHONE_DIGITS_MIN:
        normalized, err = validate_phone_international(digits_only)
        if not err and normalized:
            return normalized
    return None


def execute_update_order_notes(order_id, note_category, note_content, channel=None, customer_phone_from_chat=None):
    """
    Persist post-order instructions on SimpleOrder.order_notes (append). Optionally updates
    customer_phone when note_category is alternate_phone and a valid number is found in note_content.

    Returns a JSON str for the LLM tool result (never raises to caller).
    """
    try:
        order_id = _safe_order_arg({"order_id": order_id}, "order_id", "")
        note_category = (str(note_category or "").strip())
        note_content = (str(note_content or "").strip())

        if not order_id:
            return json.dumps({
                "status": "error",
                "success": False,
                "message": "order_id is missing. Use the active order_id from your context (e.g. last_order_id).",
            }, ensure_ascii=False)
        if not note_content:
            return json.dumps({
                "status": "error",
                "success": False,
                "message": "note_content is empty. Ask the customer to repeat their instruction.",
            }, ensure_ascii=False)

        cat_key = (note_category or "").strip().lower().replace(" ", "_")
        canonical = _NOTE_CATEGORY_CANONICAL.get(cat_key, "general_instruction")

        order = SimpleOrder.objects.filter(order_id=order_id).first()
        if not order:
            logger.error("update_order_notes: order_id=%s not found", order_id)
            return json.dumps({
                "status": "error",
                "success": False,
                "message": "Order not found. Confirm the order reference with the customer.",
            }, ensure_ascii=False)

        if channel and order.channel_id and order.channel_id != channel.id:
            logger.error(
                "update_order_notes: channel mismatch (order.channel=%s, current=%s)",
                order.channel_id, getattr(channel, "id", None),
            )
            return json.dumps({
                "status": "error",
                "success": False,
                "message": "Order does not belong to this store channel.",
            }, ensure_ascii=False)

        # Loose match: order should belong to this chat customer when possible
        if customer_phone_from_chat:
            chat_n, _ = validate_phone_international(str(customer_phone_from_chat))
            ord_n, _ = validate_phone_international(order.customer_phone or "")
            if chat_n and ord_n and chat_n != ord_n:
                if len(chat_n) >= 8 and len(ord_n) >= 8 and chat_n[-8:] != ord_n[-8:]:
                    logger.warning(
                        "update_order_notes: phone mismatch (chat vs order) order_id=%s — still allowing (same channel)",
                        order_id,
                    )

        ts = timezone.now().strftime("%Y-%m-%d %H:%M")
        line = f"[{ts}] [{canonical}] {note_content.strip()}"
        prev = (order.order_notes or "").strip()
        order.order_notes = (prev + "\n" + line).strip() if prev else line

        update_fields = ["order_notes"]

        if canonical == "alternate_phone":
            alt = _first_valid_phone_in_text(note_content)
            if alt:
                order.customer_phone = str(alt)[:20]
                update_fields.append("customer_phone")

        if getattr(order, "sheets_export_status", None) == "success":
            order.sheets_export_status = "pending"
            update_fields.append("sheets_export_status")

        order.save(update_fields=list(dict.fromkeys(update_fields)))

        logger.info("update_order_notes: saved order_id=%s category=%s", order_id, canonical)

        return json.dumps({
            "status": "success",
            "success": True,
            "message": "Note saved on the order. Confirm to the customer it was registered for the delivery team.",
            "order_id": order_id,
        }, ensure_ascii=False)

    except Exception as e:
        logger.error("execute_update_order_notes: %s", e)
        logger.error(traceback.format_exc())
        return json.dumps({
            "status": "error",
            "success": False,
            "message": "Could not save the note. Ask the customer to try again or contact support.",
        }, ensure_ascii=False)


def _resync_upsell_to_google_sheets(order):
    """
    After an upsell UPDATE, find the existing row in Google Sheets by order_id
    and update the product_name and price cells in-place (no new row).
    """
    try:
        from discount.models import GoogleSheetsConfig
        from discount.services.google_sheets_service import get_client_for_config
    except ImportError:
        return

    if not order.channel or not order.channel.owner_id:
        return

    config = GoogleSheetsConfig.objects.filter(user_id=order.channel.owner_id).first()
    if not config or not (getattr(config, "spreadsheet_id", None) or "").strip():
        return

    client = get_client_for_config(config)
    if not client:
        return

    spreadsheet_id = (config.spreadsheet_id or "").strip()
    sheet_name = (getattr(config, "sheet_name", None) or "Orders").strip()

    try:
        spreadsheet = client.open_by_key(spreadsheet_id)
        worksheet = spreadsheet.worksheet(sheet_name)

        sheets_mapping = getattr(config, "sheets_mapping", None)
        column_mapping = getattr(config, "column_mapping", None) or {}

        order_id_col = _find_column_for_field("order_id", sheets_mapping, column_mapping)
        product_name_col = _find_column_for_field("product_name", sheets_mapping, column_mapping)
        price_col = _find_column_for_field("price", sheets_mapping, column_mapping)
        quantity_col = _find_column_for_field("quantity", sheets_mapping, column_mapping)

        if not order_id_col:
            logger.info("UPSELL SHEETS: no order_id column mapped, cannot locate row")
            return

        all_values = worksheet.col_values(_col_letter_to_index(order_id_col))
        target_row = None
        oid_str = str(order.order_id or "")
        for i, val in enumerate(all_values):
            if str(val).strip() == oid_str:
                target_row = i + 1
                break

        if not target_row:
            logger.info("UPSELL SHEETS: order_id=%s not found in column %s, appending fresh row instead", oid_str, order_id_col)
            order.sheets_export_status = "pending"
            order.save(update_fields=["sheets_export_status"])
            from discount.services.google_sheets_service import sync_order_to_google_sheets
            sync_order_to_google_sheets(order.pk)
            return

        updates = {}
        if product_name_col:
            updates[f"{product_name_col}{target_row}"] = order.product_name or ""
        if price_col:
            updates[f"{price_col}{target_row}"] = str(order.price) if order.price is not None else ""
        if quantity_col:
            updates[f"{quantity_col}{target_row}"] = str(order.quantity) if order.quantity is not None else ""

        if updates:
            for cell_ref, value in updates.items():
                worksheet.update(cell_ref, [[value]], value_input_option="USER_ENTERED")
            logger.info("UPSELL SHEETS: updated row %d for order_id=%s (%s)", target_row, oid_str, list(updates.keys()))

        order.sheets_export_status = "success"
        order.sheets_export_error = None
        order.save(update_fields=["sheets_export_status", "sheets_export_error"])

    except Exception as e:
        logger.exception("_resync_upsell_to_google_sheets failed: %s", e)
        try:
            order.sheets_export_status = "failed"
            order.sheets_export_error = str(e)[:500]
            order.save(update_fields=["sheets_export_status", "sheets_export_error"])
        except Exception:
            pass


def _find_column_for_field(field_name, sheets_mapping, column_mapping):
    """Find the column letter for a given field name from sheets_mapping or column_mapping."""
    if sheets_mapping and isinstance(sheets_mapping, list):
        for i, entry in enumerate(sheets_mapping):
            mapped_field = entry.get("field") if isinstance(entry, dict) else None
            if mapped_field == field_name:
                return _col_index_to_letter(i + 1)
    if column_mapping and isinstance(column_mapping, dict):
        for col_letter, var_key in column_mapping.items():
            if var_key == field_name:
                return col_letter
    return None


def _col_index_to_letter(index):
    """Convert 1-based column index to letter (1=A, 2=B, ..., 27=AA)."""
    result = ""
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _col_letter_to_index(letter):
    """Convert column letter to 1-based index (A=1, B=2, ..., AA=27)."""
    result = 0
    for ch in letter.upper():
        result = result * 26 + (ord(ch) - 64)
    return result


def handle_update_lead_status(channel, customer_phone, new_status):
    """
    Update the Contact (lead) pipeline_stage in the database.
    Used by the update_lead_status AI tool.

    - If the current status is already 'closed', do NOT downgrade to interested/follow_up
      (protect completed sales).
    - Valid new_status: 'interested', 'follow_up', 'rejected'.

    Returns:
        dict: {"success": True} or {"success": False, "message": "..."}
    """
    if not channel or not customer_phone:
        return {"success": False, "message": "Channel or customer phone missing."}
    valid = ("interested", "follow_up", "rejected")
    if new_status not in valid:
        return {"success": False, "message": f"Invalid status. Use one of: {valid}."}
    try:
        contact = Contact.objects.filter(channel=channel, phone=customer_phone).first()
        if not contact and len(customer_phone) >= 8:
            contact = Contact.objects.filter(channel=channel).filter(phone__endswith=customer_phone[-8:]).first()
        if not contact:
            return {"success": False, "message": "Contact not found."}
        current = (contact.pipeline_stage or "").strip().lower()
        if current == Contact.PipelineStage.CLOSED:
            return {"success": True, "message": "Lead already closed; no change."}
        contact.pipeline_stage = new_status
        contact.save(update_fields=["pipeline_stage"])
        if new_status == "rejected":
            try:
                from discount.models import MerchantRiskEvent
                from discount.services.tenant_risk import record_event_for_channel
                record_event_for_channel(
                    channel,
                    MerchantRiskEvent.EVENT_NEGATIVE_SENTIMENT,
                    customer_phone=customer_phone,
                    summary="Lead marked rejected by AI (negative intent / watchdog).",
                    metadata={"pipeline_stage": new_status},
                )
            except Exception as _risk_err:
                logger.warning("handle_update_lead_status risk log failed: %s", _risk_err)
        return {"success": True}
    except Exception as e:
        logger.exception("handle_update_lead_status: %s", e)
        return {"success": False, "message": str(e)}


# Robust match for [ORDER_DATA: {...}] — extract JSON by brace-matching so commas/quotes inside values are safe
ORDER_DATA_TAG_PREFIX_RE = re.compile(r"\[ORDER_DATA:\s*(\{)", re.IGNORECASE)


def _extract_order_data_json(reply_text):
    """
    Find [ORDER_DATA: {...}] and return (start, end, json_str) for the first valid brace-balanced block.
    Returns (None, None, None) if not found or invalid.
    """
    if not reply_text or not isinstance(reply_text, str):
        return (None, None, None)
    m = ORDER_DATA_TAG_PREFIX_RE.search(reply_text)
    if not m:
        return (None, None, None)
    start_brace = m.start(1)
    i = start_brace + 1
    depth = 1
    while i < len(reply_text) and depth > 0:
        c = reply_text[i]
        if c == "\\" and i + 1 < len(reply_text):
            i += 2
            continue
        if c == '"':
            j = i + 1
            while j < len(reply_text):
                if reply_text[j] == "\\":
                    j += 2
                    continue
                if reply_text[j] == '"':
                    i = j + 1
                    break
                j += 1
            else:
                i = j
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                tag_end = i + 1
                while tag_end < len(reply_text) and reply_text[tag_end] in " \t\r\n]":
                    tag_end += 1
                return (m.start(), tag_end, reply_text[start_brace : i + 1])
        i += 1
    return (None, None, None)

# Buying-signal phrases: customer must show intent before we ask for name/city/address
BUYING_SIGNAL_PATTERNS = [
    r"\b(how much is it|how much|what.?s the price|is there a discount|any discount|how do i pay|how can i pay|i liked this|i like it|does it have a warranty|warranty\?|garantie)\b",
    r"\b(i want it|i want one|i'll take it|i'll take one|i need it|how can i buy|how do i buy|where can i buy)\b",
    r"\b(ok|okay|yes|confirm|confirmed|deal|done|let's do it|جيبلي|بدي|بدّي|كيفاش نشري|نشري|ونين نقدمو|نقدمو)\b",
    r"\b(je le prends|je veux|je prends|combien|comment acheter|j'achète|ça coûte|prix|réduction)\b",
    r"\b(السعر مناسب|الثمن مزيان|تمام|نعم|أكيد|كم الثمن|كم السعر|في تخفيض|ضمان)\b",
]
BUYING_SIGNAL_RE = re.compile("|".join(BUYING_SIGNAL_PATTERNS), re.IGNORECASE)

TRUST_SCORE_MIN_FOR_ORDER = 1  # Allow order save after 1+ helpful exchange (was 3; AI confirms only when it has name+address)
TRUST_SCORE_MAX = 10
TRUST_SCORE_CACHE_TIMEOUT = 3600


def get_trust_score(channel_id, sender):
    """Get current trust_score from cache (0 if missing)."""
    try:
        from django.core.cache import cache
        key = f"trust_score:{channel_id}:{sender}"
        val = cache.get(key)
        return max(0, min(TRUST_SCORE_MAX, int(val))) if val is not None else 0
    except Exception:
        return 0


def increment_trust_score(channel_id, sender):
    """Increment trust_score after a helpful reply (cap at TRUST_SCORE_MAX). Returns new value."""
    try:
        from django.core.cache import cache
        key = f"trust_score:{channel_id}:{sender}"
        current = get_trust_score(channel_id, sender)
        new_val = min(TRUST_SCORE_MAX, current + 1)
        cache.set(key, new_val, TRUST_SCORE_CACHE_TIMEOUT)
        return new_val
    except Exception:
        return 0


def reset_trust_score(channel_id, sender):
    """Reset trust_score to 0 (e.g. after order is saved)."""
    try:
        from django.core.cache import cache
        cache.set(f"trust_score:{channel_id}:{sender}", 0, TRUST_SCORE_CACHE_TIMEOUT)
    except Exception:
        pass


def customer_gave_buying_signal(conversation_messages, last_n=5):
    """
    Return True if any of the last_n customer messages contain a buying signal
    (e.g. "I want it", "how can I buy", "ok", "جيبلي"). Used to allow ORDER_DATA
    only after the customer has agreed to buy.
    """
    if not conversation_messages:
        return False
    customer_bodies = [
        (m.get("body") or "").strip()
        for m in conversation_messages[-last_n:]
        if m.get("role") == "customer"
    ]
    for body in customer_bodies:
        if body and BUYING_SIGNAL_RE.search(body):
            return True
    return False


def should_accept_order_data(conversation_messages, order_data, current_stage=None, trust_score=None):
    """
    Return True only when we should save ORDER_DATA (strict slot-filling).
    Required: name (full or first), phone (from sender), and delivery location (address or city).
    We require: name and (address or city) non-empty; trust_score >= TRUST_SCORE_MIN_FOR_ORDER if provided;
    and either stage is order_capture, customer gave a buying signal, or we have full slots and minimal trust (AI confirmed).
    """
    if not order_data or not isinstance(order_data, dict):
        return False
    name = (order_data.get("name") or order_data.get("customer_name") or "").strip()
    city = (order_data.get("city") or order_data.get("customer_city") or "").strip()
    address = (order_data.get("address") or "").strip()
    delivery = (address or city).strip()
    if not name or not delivery:
        return False
    ts = int(trust_score) if trust_score is not None else 0
    if trust_score is not None and ts < TRUST_SCORE_MIN_FOR_ORDER:
        return False
    if current_stage == "order_capture":
        return True
    if customer_gave_buying_signal(conversation_messages or []):
        return True
    # AI only outputs ORDER_DATA / calls save_order when it has name+address; accept with minimal trust
    if ts >= TRUST_SCORE_MIN_FOR_ORDER:
        return True
    return False


def is_order_cap_reached(channel):
    """Return True if the channel's plan has max_monthly_orders and current month count >= cap."""
    store = getattr(channel, "owner", None)
    if not store:
        return False
    try:
        from discount.services.plan_limits import is_limit_reached
        reached, _limit, _current = is_limit_reached(store, "max_monthly_orders")
        return reached
    except Exception:
        logger.debug("is_order_cap_reached: plan_limits import failed, falling back")
        if not hasattr(store, "get_plan") or not callable(store.get_plan):
            return False
        plan = store.get_plan()
        if not plan or getattr(plan, "max_monthly_orders", None) is None:
            return False
        start_of_month = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        count = SimpleOrder.objects.filter(channel=channel, created_at__gte=start_of_month).count()
        return count >= plan.max_monthly_orders


def _order_data_has_all_mandatory_slots(data):
    """Strict slot-filling: require name and delivery location (address required; city optional)."""
    if not data or not isinstance(data, dict):
        return False
    name = (data.get("name") or data.get("customer_name") or "").strip()
    city = (data.get("city") or data.get("customer_city") or "").strip()
    address = (data.get("address") or "").strip()
    return bool(name) and bool(address or city)


# Phrases that mean "order confirmed" — if these appear without [ORDER_DATA] we flag Incomplete Capture
ORDER_CONFIRMATION_PHRASES_RE = re.compile(
    r"(?:تم\s+تسجيل\s+طلبك|طلبك\s+تم\s+تسجيله|order\s+is\s+registered|your\s+order\s+is\s+confirmed|"
    r"commande\s+enregistrée|طلبك\s+مسجل)",
    re.IGNORECASE | re.UNICODE,
)


def looks_like_order_confirmation_without_data(reply_text):
    """
    True if the reply sounds like an order confirmation but we did not get valid [ORDER_DATA].
    Used to trigger retry / incomplete-capture handling.
    """
    if not reply_text or not isinstance(reply_text, str):
        return False
    return bool(ORDER_CONFIRMATION_PHRASES_RE.search(reply_text))


def extract_order_data_from_reply(reply_text):
    """
    If reply_text contains the hidden tag [ORDER_DATA: {...}], parse and return the dict
    only when all mandatory slots are present (name, city or address). Strip the tag from text.
    Uses brace-matching for robust JSON extraction. Returns (cleaned_reply, order_data_dict or None).
    """
    if not reply_text or not isinstance(reply_text, str):
        return (reply_text or "", None)
    start, end, json_str = _extract_order_data_json(reply_text)
    if start is None or not json_str:
        return (reply_text.strip(), None)
    try:
        data = json.loads(json_str)
        if not isinstance(data, dict):
            return (reply_text.strip(), None)
        # Normalize keys (name/customer_name, city/customer_city, address, sku/product_name)
        name = (data.get("name") or data.get("customer_name") or "").strip()
        city = (data.get("city") or data.get("customer_city") or "").strip()
        address = (data.get("address") or "").strip()
        sku = (data.get("sku") or "").strip()
        product_name = (data.get("product_name") or data.get("product") or "").strip()
        if not name or not (address or city):
            logger.warning("extract_order_data_from_reply: tag found but name/city/address missing or empty")
            return (reply_text.strip(), None)
        # Require product: do not accept [ORDER_DATA] without at least sku or product_name
        if not sku and not product_name:
            logger.warning("extract_order_data_from_reply: tag found but no product (sku or product_name); rejecting to avoid order without product")
            return (reply_text.strip(), None)
        order_data = {"name": name, "city": city or "", "address": address or "", "sku": sku, "product_name": product_name}
        cleaned = (reply_text[:start].strip() + " " + reply_text[end:].strip()).strip()
        return (cleaned, order_data)
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning("extract_order_data_from_reply parse error: %s", e)
    return (reply_text.strip(), None)


def track_order(customer_phone, channel=None):
    """
    Find the latest order for the given customer_phone (optionally scoped to channel).
    Returns a dict with status, shipping_company, expected_delivery_date, customer_name, and found (bool).
    If no order is found, returns found=False and status=None, etc.
    """
    if not customer_phone or not isinstance(customer_phone, str):
        return {
            "found": False,
            "status": None,
            "shipping_company": None,
            "expected_delivery_date": None,
            "days_until_delivery": None,
            "customer_name": None,
        }
    qs = SimpleOrder.objects.filter(customer_phone=customer_phone.strip()).order_by("-created_at")
    if channel:
        qs = qs.filter(channel=channel)
    order = qs.first()
    if not order:
        return {
            "found": False,
            "status": None,
            "shipping_company": None,
            "expected_delivery_date": None,
            "days_until_delivery": None,
            "customer_name": None,
        }
    expected_date = None
    days_until_delivery = None
    if getattr(order, "expected_delivery_date", None):
        expected_date = order.expected_delivery_date.isoformat()
        today = timezone.now().date()
        delta = order.expected_delivery_date - today
        days_until_delivery = max(0, delta.days)
    return {
        "found": True,
        "status": (order.status or "").strip() or "pending",
        "shipping_company": (getattr(order, "shipping_company", None) or "").strip() or None,
        "expected_delivery_date": expected_date,
        "days_until_delivery": days_until_delivery,
        "customer_name": (order.customer_name or "").strip() or None,
    }


def save_order_from_ai(channel, customer_phone, customer_name=None, customer_city=None,
                       sku=None, product_name=None, price=None, quantity=1,
                       agent_name=None, bot_session_id=None, **kwargs):
    """
    Create a SimpleOrder from AI-extracted data. Order is attributed to a Virtual Team Member (bot user).

    Args:
        channel: WhatsAppChannel instance (required).
        customer_phone: str (required).
        customer_name: str (optional).
        customer_city: str (optional) – address/city.
        sku: str (optional) – product SKU.
        product_name: str (optional).
        price: number or str (optional).
        quantity: number (default 1).
        agent_name: str (optional) – e.g. "Simo - AI Closer"; used to get/create the bot user.
        bot_session_id: str (optional) – conversation/session ID for tracing.
        **kwargs: ignored or used for other fields (e.g. customer_country).

    Returns:
        SimpleOrder instance on success; None on failure; or a dict {"saved": False, "message": str}
        when price is 0/missing so the AI can be told to re-check the conversation and extract the price.
    """
    if not channel or not customer_phone:
        logger.warning("save_order_from_ai: channel and customer_phone required")
        return None

    # Require at least one product identifier (no orders for "no product" / out-of-context)
    sku_str = (sku or "").strip()
    product_name_str = (product_name or "").strip()
    if not sku_str and not product_name_str:
        logger.warning("save_order_from_ai: rejected — no product (sku or product_name). Do not save when no product is selected.")
        return None

    # Parse price; when 0 or missing we may use product price from DB or ask the AI to re-extract from conversation
    price_val = Decimal("0")
    if price is not None:
        try:
            price_val = Decimal(str(price))
        except Exception:
            pass

    # Resolve product only inside this WhatsApp channel's catalog (never another channel/account).
    from discount.services.product_scope import get_channel_product
    from discount.services.product_search import find_matching_product

    product_instance = None
    if sku_str:
        try:
            product_instance = get_channel_product(channel, sku=sku_str)
        except Exception as e:
            logger.warning("save_order_from_ai product lookup for sku=%s: %s", sku_str, e)
    if sku_str and not product_instance:
        logger.warning(
            "save_order_from_ai: rejected — sku=%s is not in channel %s catalog.",
            sku_str, getattr(channel, "id", None),
        )
        return None
    if not product_instance and product_name_str:
        try:
            product_instance = get_channel_product(channel, name=product_name_str)
            if not product_instance:
                product_instance = find_matching_product(product_name_str, channel=channel)
        except Exception as e:
            logger.warning("save_order_from_ai product lookup by name=%s: %s", product_name_str, e)
        if not product_instance:
            logger.warning(
                "save_order_from_ai: rejected — product_name=%r is not in channel %s catalog.",
                product_name_str, getattr(channel, "id", None),
            )
            return None

    # When price is 0 or missing: use product price from DB if available; otherwise ask AI to re-extract from conversation
    if price_val is None or price_val <= 0:
        if product_instance:
            try:
                p = getattr(product_instance, "price", None)
                if p is not None and Decimal(str(p)) > 0:
                    price_val = Decimal(str(p))
            except Exception:
                pass
        if price_val is None or price_val <= 0:
            logger.warning("save_order_from_ai: rejected — price must be positive (got %s). Ask AI to re-extract from conversation.", price_val)
            return {
                "saved": False,
                "message": "SYSTEM ERROR: The product price could not be determined (price is 0 or missing). Review the conversation history — if the price was mentioned or sent to the customer (e.g. in product context or in your previous messages), extract it and call save_order again with the 'price' parameter set to that value.",
            }

    store = getattr(channel, "owner", None)
    ai_agent_user = get_or_create_ai_agent_user(store, agent_name="AI Agent")
    order_agent = ai_agent_user if ai_agent_user else store

    # Plan: max_monthly_orders cap (stop auto-order when reached)
    if store and hasattr(store, "get_plan") and callable(store.get_plan):
        plan = store.get_plan()
        if plan and getattr(plan, "max_monthly_orders", None) is not None:
            start_of_month = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            count = SimpleOrder.objects.filter(channel=channel, created_at__gte=start_of_month).count()
            if count >= plan.max_monthly_orders:
                logger.info("save_order_from_ai: max_monthly_orders (%s) reached for channel %s", plan.max_monthly_orders, channel.id)
                return None

    try:
        order_id = str(uuid.uuid4())[:8]
        # Ensure uniqueness
        while SimpleOrder.objects.filter(order_id=order_id).exists():
            order_id = str(uuid.uuid4())[:8]

        qty_val = Decimal("1")
        if quantity is not None:
            try:
                qty_val = Decimal(str(quantity))
            except Exception:
                pass

        _cur = (getattr(product_instance, "currency", None) or "").strip() or "MAD" if product_instance else "MAD"
        order = SimpleOrder.objects.create(
            product=product_instance,
            agent=order_agent,
            channel=channel,
            sku=sku or "",
            product_name=(product_name or (product_instance.name if product_instance else "") or ""),
            customer_name=customer_name or customer_phone,
            customer_phone=customer_phone,
            customer_city=customer_city or "",
            customer_country=kwargs.get("customer_country"),
            order_id=order_id,
            status="pending",
            created_at=timezone.now(),
            price=price_val,
            currency=_cur,
            quantity=qty_val,
            created_by_ai=True,
            created_by_bot_session=(bot_session_id or "")[:100] or None,
            sheets_export_status="pending",
        )
        logger.info("save_order_from_ai created order_id=%s for %s", order_id, customer_phone)
        # Stop logic: cancel pending follow-up tasks when customer places an order
        try:
            from discount.whatssapAPI.follow_up import cancel_pending_follow_up_tasks_for_customer
            cancel_pending_follow_up_tasks_for_customer(channel, customer_phone)
        except Exception as e:
            logger.warning("cancel_pending_follow_up_tasks_for_customer: %s", e)
        _notify_owner_order_created(channel, order)
        return order
    except Exception as e:
        logger.exception("save_order_from_ai failed: %s", e)
        return None


def _notify_owner_order_created(channel, order):
    """If channel has order_notify_method (EMAIL or WHATSAPP), send owner a notification. Runs after order is created."""
    method = getattr(channel, "order_notify_method", None) or ""
    if not method or method not in ("EMAIL", "WHATSAPP"):
        return
    try:
        if method == "EMAIL":
            to_email = (getattr(channel, "order_notify_email", None) or "").strip()
            if not to_email and getattr(channel, "owner", None):
                to_email = (getattr(channel.owner, "email", None) or "").strip()
            if not to_email:
                return
            from django.core.mail import send_mail
            from django.conf import settings
            subject = f"New order #{getattr(order, 'order_id', '')} from AI"
            body = (
                f"A new order was created by the AI sales agent.\n\n"
                f"Order ID: {getattr(order, 'order_id', '')}\n"
                f"Customer: {getattr(order, 'customer_name', '')} / {getattr(order, 'customer_phone', '')}\n"
                f"Address/City: {getattr(order, 'customer_city', '')}\n"
                f"Product: {getattr(order, 'product_name', '')}\n"
                f"Price: {getattr(order, 'price', '')} x {getattr(order, 'quantity', 1)}\n"
            )
            send_mail(
                subject=subject,
                message=body,
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@example.com"),
                recipient_list=[to_email],
                fail_silently=True,
            )
            logger.info("order notify email sent to %s for order_id=%s", to_email, getattr(order, "order_id", ""))
        elif method == "WHATSAPP":
            to_phone = (getattr(channel, "order_notify_whatsapp_phone", None) or "").strip()
            if not to_phone and getattr(channel, "owner", None):
                to_phone = (getattr(channel.owner, "phone", None) or "").strip()
            if not to_phone:
                return
            to_phone = "".join(c for c in to_phone if c.isdigit())
            if not to_phone or len(to_phone) < 10:
                return
            from discount.whatssapAPI.process_messages import send_automated_response
            msg = (
                f"🆕 New order from AI\n"
                f"Order ID: {getattr(order, 'order_id', '')}\n"
                f"Customer: {getattr(order, 'customer_name', '')} / {getattr(order, 'customer_phone', '')}\n"
                f"Address: {getattr(order, 'customer_city', '')}\n"
                f"Product: {getattr(order, 'product_name', '')}"
            )
            send_automated_response(to_phone, [{"type": "text", "content": msg}], channel=channel)
            logger.info("order notify WhatsApp sent to %s for order_id=%s", to_phone, getattr(order, "order_id", ""))
    except Exception as e:
        logger.exception("_notify_owner_order_created failed: %s", e)
