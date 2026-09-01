"""
Dynamic order-checkout orchestration for the WhatsApp AI sales agent.

- Product-scoped OpenAI tool schemas (no hardcoded required fields)
- GATHERING_INFO guardrails (batch field collection)
- can_read + send_whatsapp_flow routing
- submit_customer_order validation interceptor
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from ai_assistant.services import SUBMIT_ORDER_FIELD_PROPERTIES

logger = logging.getLogger(__name__)

FIELD_LABELS = {
    "customer_name": "Full name",
    "phone_number": "Phone number",
    "shipping_city": "City",
    "shipping_address": "Full address",
    "email_address": "Email address",
}

# Purchase / checkout intent (Darija, MSA, FR, EN) — broader than how-to-order-only.
CHECKOUT_INTENT_RE = re.compile(
    r"(?:"
    r"بغيت\s+(?:ن(?:شري|طلب|اخد|اخذ)|اشري)|"
    r"بغيت\s+\S+\s*(?:كيفاش|كيف)?|"
    r"كيفاش\s*(?:ن(?:طلب|شري|اخد|اخذ)|ندير|نشري)|"
    r"(?:واش\s+)?ن(?:طلب|شري|اخد)\s|"
    r"(?:i|we)\s+want\s+to\s+(?:buy|order|get)|"
    r"how\s*(?:do|can|to)\s*(?:i|we)\s*(?:order|buy)|"
    r"comment\s*(?:commander|acheter)|"
    r"je\s+(?:veux|prends|commande)"
    r")",
    re.IGNORECASE | re.UNICODE,
)

# Customer explicitly asks to receive the WhatsApp order form again.
RESEND_FORM_RE = re.compile(
    r"(?:"
    r"(?:عاود|مر(?:ة\s*)?أخرى|again|renvoy|resend|re-send)"
    r".{0,48}?(?:ن(?:م|mo)ودج|form(?:ulaire)?|flow|فورم|است(?:m|م)ارة|bouton|button)"
    r"|(?:ن(?:م|mo)ودج|form(?:ulaire)?|flow|فورم|است(?:m|م)ارة).{0,48}?"
    r"(?:عاود|again|resend|renvoy|مر(?:ة\s*)?أخرى|another\s*time)"
    r"|(?:[تس](?:يف|y)ف(?:ط|t)|send|envoy|ب(?:عت|عث)|ر(?:س|s)ل).{0,48}?"
    r"(?:ن(?:م|mo)ودج|form|flow|فورم|است(?:m|m)ارة)"
    r"|whatsapp\s*flow"
    r")",
    re.IGNORECASE | re.UNICODE,
)

# OpenAI tool: send WhatsApp Flow form (hybrid checkout)
SEND_WHATSAPP_FLOW_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "send_whatsapp_flow",
        "description": (
            "Send (or resend) the merchant's WhatsApp order form to collect checkout details. "
            "Call when the customer agreed to buy, can_read is True, OR they explicitly ask "
            "to receive/resend the form again — never ask for name/address/city manually instead."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Brief internal reason (e.g. customer_ready_to_order).",
                },
            },
            "required": [],
        },
    },
}


def _format_missing_field_labels(field_keys: list[str]) -> str:
    labels = [FIELD_LABELS.get(k, k.replace("_", " ").title()) for k in field_keys or []]
    if not labels:
        return "required order details"
    if len(labels) == 1:
        return labels[0]
    return ", ".join(labels[:-1]) + " and " + labels[-1]


def generate_order_tool_schema(product_id, seller_id=None) -> Optional[dict[str, Any]]:
    """
    Build the OpenAI `submit_customer_order` tool schema from the product's
    configured checkout fields in the database.
    """
    from discount.models import Products
    from discount.orders_ai import get_required_order_fields_for_product

    try:
        pid = int(product_id)
    except (TypeError, ValueError):
        return None

    qs = Products.objects.filter(id=pid)
    if seller_id is not None:
        try:
            qs = qs.filter(admin_id=int(seller_id))
        except (TypeError, ValueError):
            return None
    product = qs.first()
    if not product:
        return None

    merchant_fields = get_required_order_fields_for_product(product)

    properties: dict[str, Any] = {
        "product_id": SUBMIT_ORDER_FIELD_PROPERTIES["product_id"],
        "final_agreed_price": SUBMIT_ORDER_FIELD_PROPERTIES["final_agreed_price"],
    }
    required: list[str] = ["product_id", "final_agreed_price"]

    optional_props = (
        "customer_name",
        "phone_number",
        "shipping_city",
        "shipping_address",
        "email_address",
    )
    for key in optional_props:
        if key in SUBMIT_ORDER_FIELD_PROPERTIES:
            properties[key] = SUBMIT_ORDER_FIELD_PROPERTIES[key]

    for key in merchant_fields:
        if key in properties and key not in required:
            required.append(key)

    if not merchant_fields:
        desc = (
            "Instant checkout product: submit when the customer confirms purchase intent. "
            "Only product_id and final_agreed_price are required; phone may come from WhatsApp context."
        )
    else:
        need = _format_missing_field_labels(merchant_fields)
        desc = (
            f"Submit the order ONLY after the customer provided: {need}. "
            "Never use placeholder values. product_id must match [DB_PRODUCT_ID: X]."
        )

    return {
        "type": "function",
        "function": {
            "name": "submit_customer_order",
            "description": desc,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }


def build_sales_tools_for_product(
    product_id,
    seller_id=None,
    *,
    include_whatsapp_flow: bool = False,
) -> list[dict[str, Any]]:
    """Replace static submit tool with product schema; optionally add send_whatsapp_flow."""
    from ai_assistant.services import SALES_AGENT_TOOLS

    tools = list(SALES_AGENT_TOOLS)
    dynamic = generate_order_tool_schema(product_id, seller_id=seller_id)
    if dynamic:
        tools = [t for t in tools if (t.get("function") or {}).get("name") != "submit_customer_order"]
        tools.append(dynamic)
    if include_whatsapp_flow:
        if not any((t.get("function") or {}).get("name") == "send_whatsapp_flow" for t in tools):
            tools.append(SEND_WHATSAPP_FLOW_TOOL)
    return tools


def get_collected_order_fields(session_context: Optional[dict]) -> dict[str, str]:
    ctx = session_context if isinstance(session_context, dict) else {}
    raw = ctx.get("collected_order_fields") or {}
    if not isinstance(raw, dict):
        return {}
    return {str(k): str(v).strip() for k, v in raw.items() if v is not None and str(v).strip()}


def compute_missing_order_fields(
    product,
    collected: Optional[dict] = None,
    customer_phone: str = "",
) -> list[str]:
    """Return DB-required field keys still missing or placeholder."""
    from discount.orders_ai import get_required_order_fields_for_product, is_placeholder_order_field

    if not product:
        return []
    required = get_required_order_fields_for_product(product)
    if not required:
        return []

    collected = collected or {}
    missing = []
    for field in required:
        if field == "phone_number":
            val = (collected.get("phone_number") or customer_phone or "").strip()
        else:
            val = (collected.get(field) or "").strip()
        if is_placeholder_order_field(val):
            missing.append(field)
    return missing


def merge_collected_from_tool_args(collected: dict, arguments: dict, customer_phone: str = "") -> dict:
    """Persist partial field values from a blocked submit attempt."""
    out = dict(collected or {})
    args = arguments if isinstance(arguments, dict) else {}
    mapping = {
        "customer_name": args.get("customer_name"),
        "phone_number": args.get("phone_number") or customer_phone,
        "shipping_city": args.get("shipping_city"),
        "shipping_address": args.get("shipping_address"),
        "email_address": args.get("email_address"),
    }
    from discount.orders_ai import is_placeholder_order_field

    for key, val in mapping.items():
        if val is not None and str(val).strip() and not is_placeholder_order_field(val):
            out[key] = str(val).strip()
    return out


def build_gathering_info_guardrail(missing_fields: list[str]) -> str:
    """Batch collection guardrail for GATHERING_INFO state."""
    labels = _format_missing_field_labels(missing_fields)
    return (
        f"You must collect the following missing fields: {labels}. "
        "Ask the user to provide ALL of them in a SINGLE, polite message. "
        "Do NOT ask for them one by one."
    )


def looks_like_checkout_intent(text: str) -> bool:
    """True when the customer wants to buy/order or asks how to proceed with checkout."""
    body = (text or "").strip()
    if not body:
        return False
    if CHECKOUT_INTENT_RE.search(body):
        return True
    try:
        from discount.orders_ai import looks_like_how_to_order_only
        return looks_like_how_to_order_only(body)
    except Exception:
        return False


def looks_like_resend_form_request(text: str) -> bool:
    """True when the customer explicitly asks to receive the WhatsApp form again."""
    body = (text or "").strip()
    if not body:
        return False
    return bool(RESEND_FORM_RE.search(body))


def should_resend_whatsapp_flow(
    *,
    incoming_body: str,
    hybrid_enabled: bool,
    needs_form: bool,
    mode: str,
) -> bool:
    """Resend is allowed while checkout is still open (order not yet finalized)."""
    from discount.whatssapAPI.checkout_capture import MODE_DONE, MODE_VOICE

    if not hybrid_enabled or not needs_form:
        return False
    if (mode or "") in (MODE_DONE, MODE_VOICE):
        return False
    return looks_like_resend_form_request(incoming_body)


def should_force_whatsapp_flow(
    *,
    can_read: bool,
    incoming_body: str,
    hybrid_enabled: bool,
    needs_form: bool,
    mode: str,
    form_already_sent: bool,
) -> bool:
    """
    Deterministic guard: text-comfortable customer + checkout intent → WhatsApp Flow,
    not manual slot-filling in chat. Resend requests bypass form_already_sent.
    """
    from discount.whatssapAPI.checkout_capture import MODE_DONE, MODE_VOICE

    if should_resend_whatsapp_flow(
        incoming_body=incoming_body,
        hybrid_enabled=hybrid_enabled,
        needs_form=needs_form,
        mode=mode,
    ):
        return True

    if not can_read or not hybrid_enabled or not needs_form:
        return False
    if form_already_sent:
        return False
    if (mode or "") in (MODE_VOICE, MODE_DONE):
        return False
    return looks_like_checkout_intent(incoming_body)


def build_can_read_flow_rule() -> str:
    return (
        "The user is comfortable with text. To collect order details, you MUST call the "
        "`send_whatsapp_flow` function immediately. Do NOT ask for name, city, address, or phone "
        "manually in the chat — the WhatsApp form collects those fields."
    )


def build_resend_flow_rule() -> str:
    return (
        "The customer explicitly asked to receive the WhatsApp order form again. "
        "You MUST call `send_whatsapp_flow` immediately. "
        "Do NOT say you cannot resend the form. Do NOT ask for name/city/address in chat."
    )


def build_gathering_info_state_banner(missing_fields: list[str]) -> str:
    guard = build_gathering_info_guardrail(missing_fields)
    return (
        "╔══════════════════════════════════════════════════╗\n"
        "║     [SYSTEM STATE: GATHERING_INFO]               ║\n"
        "╚══════════════════════════════════════════════════╝\n"
        f"{guard}\n"
        "Do NOT call submit_customer_order until every required field is present and valid.\n"
        "══════════════════════════════════════════════════"
    )


def intercept_submit_customer_order(
    arguments,
    product,
    *,
    incoming_body: str = "",
    customer_phone: str = "",
) -> tuple[bool, Optional[str]]:
    """
    Validation interceptor for submit_customer_order tool calls.
    Returns (allowed, error_json_string).
    """
    from discount.orders_ai import validate_submit_order_arguments

    blocked = validate_submit_order_arguments(
        arguments,
        product,
        incoming_body=incoming_body,
        customer_phone_from_chat=customer_phone,
    )
    if not blocked:
        return True, None

    try:
        payload = json.loads(blocked)
    except json.JSONDecodeError:
        return False, blocked

    missing = payload.get("missing_fields") or []
    if missing or payload.get("reason") == "missing_required_fields":
        labels = _format_missing_field_labels(missing or ["customer_name", "shipping_city"])
        payload["instruction"] = (
            f"Required data is missing: {labels}. "
            "Ask the customer for ALL missing items in ONE polite message — not one field at a time. "
            "Then call submit_customer_order again with complete valid data."
        )
    return False, json.dumps(payload, ensure_ascii=False)


def should_enter_gathering_info(
    product,
    missing_fields: list[str],
    *,
    sales_stage: Optional[str] = None,
    conversation_state: Optional[str] = None,
) -> bool:
    if not product or not missing_fields:
        return False
    state = (conversation_state or "").strip().upper()
    if state in ("AWAITING_PAYMENT_RECEIPT", "GATHERING_INFO"):
        return state == "GATHERING_INFO"
    stage = (sales_stage or "").strip().lower()
    if stage in ("order_capture", "stage_5_closing", "soft_close"):
        return True
    from discount.whatssapAPI.checkout_capture import CLOSING_STAGES

    if (sales_stage or "") in CLOSING_STAGES:
        return True
    return False


def execute_send_whatsapp_flow(
    channel,
    sender,
    current_node,
    product,
    required_order_fields,
    locale: str = "ar",
) -> tuple[Optional[dict], Optional[dict], str]:
    """
    Build outbound WhatsApp Flow message item + pending payload.
    Returns (output_item, pending_payload, error).
    """
    from discount.whatssapAPI.checkout_capture import try_build_checkout_form_item

    return try_build_checkout_form_item(
        channel,
        current_node,
        sender,
        product,
        required_order_fields,
        locale,
    )
