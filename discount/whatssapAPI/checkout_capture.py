"""Hybrid checkout: WhatsApp Flow first, voice collection if the customer cannot fill it."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)

MODE_NONE = ""
MODE_FORM = "form_pending"
MODE_VOICE = "voice"
MODE_CHAT = "chat_fallback"
MODE_DONE = "done"

CTX_MODE = "checkout_capture_mode"
CTX_FORM_SENT = "checkout_form_sent"
CTX_VOICE_PENDING = "checkout_voice_pending_order"

# Form is sent only when the sales agent is already closing, or it tried to
# submit an order. Language-specific buy phrases are NOT used as triggers.
CLOSING_STAGES = {"STAGE_5_CLOSING", "order_capture"}

_FIELD_ASK_RE = re.compile(
    r"(اسمك|سميتك|العنوان|عنوانك|المدينة|مدينتك|رقم\s*الهاتف|رقم\s*تلفون|"
    r"your\s*name|full\s*name|address|city\b|phone\s*number|"
    r"ton\s*nom|votre\s*nom|adresse|ville|téléphone|telephone)",
    re.IGNORECASE,
)


def is_hybrid_checkout_enabled(node) -> bool:
    cfg = getattr(node, "ai_model_config", None) or {}
    if not isinstance(cfg, dict):
        return True
    if "hybrid_checkout" not in cfg:
        return True
    return bool(cfg.get("hybrid_checkout"))


def product_needs_checkout_form(product) -> bool:
    if not product or getattr(product, "is_digital", False):
        return False
    try:
        from discount.orders_ai import get_required_order_fields_for_product
        fields = get_required_order_fields_for_product(product)
    except Exception:
        fields = ["customer_name", "phone_number", "shipping_city", "shipping_address"]
    return bool(fields)


def is_inbound_audio(message_type) -> bool:
    return str(message_type or "").strip().lower() in ("audio", "voice")


def looks_like_typed_details(text: str) -> bool:
    body = (text or "").strip()
    if len(body) < 12:
        return False
    tokens = [t for t in re.split(r"\s+", body) if t]
    return len(tokens) >= 3


def looks_like_asking_for_fields(text: str) -> bool:
    return bool(text and _FIELD_ASK_RE.search(text))


def detect_voice_first(channel, sender) -> bool:
    if not channel or not sender:
        return False
    try:
        from discount.models import Message
        rows = list(
            Message.objects.filter(
                channel=channel,
                sender=sender,
                is_from_me=False,
                is_internal=False,
            )
            .order_by("-timestamp")
            .values_list("media_type", "type")[:6]
        )
    except Exception as exc:
        logger.debug("detect_voice_first failed: %s", exc)
        return False
    if not rows:
        return False

    def _is_audio(media_type, msg_type):
        mt = (media_type or "").lower()
        tp = (msg_type or "").lower()
        return mt in ("audio", "voice") or tp in ("audio", "voice")

    flags = [_is_audio(mt, tp) for mt, tp in rows]
    inbound = flags
    if len(inbound) >= 3 and all(inbound[:3]):
        return True
    if len(inbound) >= 2 and all(inbound):
        return True
    if len(inbound) >= 4 and sum(inbound[:4]) >= 3:
        return True
    return False


def checkout_locale(node, market=None) -> str:
    lang = (getattr(node, "node_language", None) or "").strip().upper()
    if lang.startswith("FR"):
        return "fr"
    if lang.startswith("EN"):
        return "en"
    market_key = (market or "").strip().upper()
    if market_key in ("FR",):
        return "fr"
    return "ar"


def form_copy(locale: str, field_keys=None) -> dict:
    keys = [k for k in (field_keys or []) if k != "phone_number"]
    phrase = _fields_phrase(locale, keys)
    
    if locale == "fr":
        return {
            "text": (
                f"C'est noté ! 🎉 Cliquez ci-dessous pour remplir vos informations ({phrase}) "
                "et valider votre commande.\n\n"
                "💡 Vous préférez parler ? Envoyez-nous un simple message vocal 🎤"
            ),
            "header": "Validation de commande 📦",
            "footer": "Ou envoyez un vocal 🎤",
            "cta": "📝 Remplir le formulaire",
            "screen_title": "Vos informations",
            "submit_label": "Confirmer la commande",
            "intro": "Super ! Voici le formulaire pour finaliser votre commande 👇",
        }
        
    if locale == "en":
        return {
            "text": (
                f"Got it! 🎉 Please tap below to provide your details ({phrase}) "
                "so we can process your order.\n\n"
                "💡 Prefer speaking? Just send us a quick voice note 🎤"
            ),
            "header": "Order Confirmation 📦",
            "footer": "Or send a voice note 🎤",
            "cta": "📝 Fill Details",
            "screen_title": "Your Information",
            "submit_label": "Confirm Order",
            "intro": "Awesome! Here is the form to complete your order 👇",
        }
        
    # الدارجة المغربية (Moroccan Darija)
    return {
        "text": (
            f"مرحبا، بكل فرح! 🎉 كليكي لتحت باش تدخل المعلومات ديالك ({phrase}) "
            "ونأكدو ليك الطلب في الحين.\n\n"
            "💡 (إلا جاك الكلاڤي طويل، تقدر تصيفطهم لينا غير فـ أوديو 🎤)"
        ),
        "header": "تأكيد الطلب 📦",
        "footer": "أو صيفط أوديو 🎤",
        "cta": "📝 إدخال المعلومات",
        "screen_title": "معلومات التوصيل",
        "submit_label": "تأكيد الطلب",
        "intro": "على الراس والعين! هاهي الاستمارة باش نأكدو ليك الطلب 👇",
    }



def voice_intro_reply(locale: str) -> str:
    if locale == "fr":
        return "Pas de souci. Envoie-moi ton nom en vocal, un seul renseignement à la fois."
    if locale == "en":
        return "No problem. Send me your name as a voice note — one detail at a time."
    return "ماكاين حتى مشكل. صيفط ليا سميتك بمقطع صوتي، معلومة واحدة في كل مرة."


def form_thank_you(locale: str) -> str:
    if locale == "fr":
        return "Merci, on a bien reçu tes infos. La commande est enregistrée, on te contacte pour confirmer."
    if locale == "en":
        return "Thanks, we received your details. The order is placed and we will contact you to confirm."
    return "توصلنا بالمعلومات. الطلب تسجّل، غادي نتواصلو معاك للتأكيد."


def _fields_phrase(locale: str, keys) -> str:
    labels = _field_labels(locale)
    names = [labels[k][0] for k in keys if k in labels]
    if not names:
        names = [labels["customer_name"][0]]
    if len(names) == 1:
        return names[0]
    if locale == "fr":
        return ", ".join(names[:-1]) + " et " + names[-1]
    if locale == "en":
        return ", ".join(names[:-1]) + " and " + names[-1]
    return " و".join(names)


def _field_labels(locale: str) -> dict:
    if locale == "fr":
        return {
            "customer_name": ("Nom complet", "text", "name"),
            "shipping_city": ("Ville", "text", "city"),
            "shipping_address": ("Adresse", "textarea", "address"),
            "phone_number": ("Téléphone", "phone", "phone"),
            "email_address": ("Email", "email", "email"),
        }
    if locale == "en":
        return {
            "customer_name": ("Full name", "text", "name"),
            "shipping_city": ("City", "text", "city"),
            "shipping_address": ("Address", "textarea", "address"),
            "phone_number": ("Phone", "phone", "phone"),
            "email_address": ("Email", "email", "email"),
        }
    return {
        "customer_name": ("الاسم الكامل", "text", "name"),
        "shipping_city": ("المدينة", "text", "city"),
        "shipping_address": ("العنوان", "textarea", "address"),
        "phone_number": ("رقم الهاتف", "phone", "phone"),
        "email_address": ("الإيميل", "email", "email"),
    }


def build_order_form_content(product, required_fields, locale: str) -> dict:
    from discount.whatssapAPI.whatsapp_flows import PURPOSE_ORDER

    # Phone is already the WhatsApp number — do not ask again in the form.
    # Empty required_fields (direct_sale) stays empty; do not invent extra inputs.
    if required_fields is None:
        form_keys = ["customer_name"]
    else:
        form_keys = [k for k in required_fields if k != "phone_number"]
    copy = form_copy(locale, form_keys)
    labels = _field_labels(locale)
    fields = []
    for key in form_keys:
        spec = labels.get(key)
        if not spec:
            continue
        label, ftype, maps_to = spec
        fields.append({
            "key": maps_to if maps_to != "custom" else key,
            "label": label,
            "field_type": ftype,
            "required": True,
            "maps_to": maps_to,
            "options": "",
        })
    product_id = getattr(product, "id", None)
    product_name = (getattr(product, "name", None) or "").strip()
    return {
        "purpose": PURPOSE_ORDER,
        "text": copy["text"],
        "header_text": copy["header"],
        "footer_text": copy["footer"],
        "cta_label": copy["cta"],
        "screen_title": copy["screen_title"],
        "submit_label": copy["submit_label"],
        "helper_text": (product_name or "")[:80],
        "fields": fields,
        "product_id": int(product_id) if product_id else None,
        "product_name": product_name,
    }


def form_preview_for_product(product, locale: str = "ar") -> dict:
    """Inbox/builder preview of the order form that checkout_mode will send."""
    from discount.orders_ai import CHECKOUT_MODE_LABELS, get_required_order_fields_for_product

    mode = (getattr(product, "checkout_mode", None) or "standard_cod").strip() or "standard_cod"
    try:
        required = get_required_order_fields_for_product(product)
    except Exception:
        required = ["customer_name", "phone_number", "shipping_city"]
    content = build_order_form_content(product, required, locale)
    fields = content.get("fields") or []
    return {
        "checkout_mode": mode,
        "checkout_mode_label": CHECKOUT_MODE_LABELS.get(mode) or mode,
        "can_send_form": bool(fields),
        "fields": [
            {
                "label": f.get("label") or "",
                "field_type": f.get("field_type") or "text",
                "required": True,
            }
            for f in fields
        ],
        "cta": content.get("cta_label") or "",
        "header": content.get("header_text") or "",
        "body": content.get("text") or "",
        "footer": content.get("footer_text") or "",
        "submit_label": content.get("submit_label") or "",
        "screen_title": content.get("screen_title") or "",
        "product_name": content.get("product_name") or (getattr(product, "name", None) or ""),
        "defaults": {
            "header": content.get("header_text") or "",
            "body": content.get("text") or "",
            "footer": content.get("footer_text") or "",
            "cta": content.get("cta_label") or "",
        },
        "saved": None,
    }


def clip_form_copy_fields(payload) -> dict:
    data = payload if isinstance(payload, dict) else {}
    return {
        "header": str(data.get("header_text") or data.get("header") or "").strip()[:60],
        "body": str(data.get("text") or data.get("body") or "").strip()[:1024],
        "footer": str(data.get("footer_text") or data.get("footer") or "").strip()[:60],
        "cta": str(data.get("cta_label") or data.get("cta") or "").strip()[:20],
    }


def copy_row_to_dict(row) -> dict:
    if not row:
        return {}
    return {
        "header": row.header_text or "",
        "body": row.body_text or "",
        "footer": row.footer_text or "",
        "cta": row.cta_label or "",
    }


def merge_preview_with_user_copy(preview, row) -> dict:
    if not isinstance(preview, dict):
        return preview
    if "defaults" not in preview:
        preview["defaults"] = {
            "header": preview.get("header") or "",
            "body": preview.get("body") or "",
            "footer": preview.get("footer") or "",
            "cta": preview.get("cta") or "",
        }
    if not row:
        preview["saved"] = None
        return preview
    saved = copy_row_to_dict(row)
    preview["saved"] = saved
    preview["header"] = saved["header"]
    preview["body"] = saved["body"]
    preview["footer"] = saved["footer"]
    preview["cta"] = saved["cta"]
    return preview


def apply_copy_dict_to_content(content: dict, copy: dict) -> dict:
    if not isinstance(content, dict) or not isinstance(copy, dict):
        return content
    if copy.get("body"):
        content["text"] = copy["body"]
    if copy.get("header"):
        content["header_text"] = copy["header"]
    if copy.get("footer"):
        content["footer_text"] = copy["footer"]
    if copy.get("cta"):
        content["cta_label"] = copy["cta"]
    return content


def find_linked_order_flow_node(ai_node):
    if not ai_node:
        return None
    try:
        from discount.models import Connection
        from discount.whatssapAPI.whatsapp_flows import PURPOSE_ORDER, parse_flow_node_content
        for conn in Connection.objects.filter(from_node=ai_node).select_related("to_node"):
            data = conn.data if isinstance(conn.data, dict) else {}
            if data.get("source_port") == "on_order_success":
                continue
            to_node = conn.to_node
            if not to_node or to_node.node_type != "whatsapp-flows":
                continue
            parsed = parse_flow_node_content(to_node.content_text)
            if parsed.get("purpose") == PURPOSE_ORDER:
                return to_node
    except Exception as exc:
        logger.debug("find_linked_order_flow_node: %s", exc)
    return None


def get_mode(ctx: Optional[dict]) -> str:
    if not isinstance(ctx, dict):
        return MODE_NONE
    return str(ctx.get(CTX_MODE) or MODE_NONE).strip()


def set_checkout_context(channel, sender, patch: dict):
    if not channel or not sender or not patch:
        return
    try:
        from discount.whatssapAPI.session_state import update_session_context_data
        update_session_context_data(channel, sender, patch)
    except Exception as exc:
        logger.warning("set_checkout_context failed: %s", exc)


def build_prompt(mode: str, required_fields=None) -> str:
    fields = [f for f in (required_fields or []) if f != "phone_number"]
    field_label = ", ".join(fields) if fields else "name, city, address"
    if mode == MODE_FORM:
        return (
            "[CHECKOUT CAPTURE — FORM ALREADY SENT]\n"
            "A WhatsApp order form was already sent. Do NOT ask the customer to type name, address, or phone.\n"
            "If they EXPLICITLY ask to resend / receive the form again (e.g. 'عاود سيفط ليا النمودج', "
            "'resend the form', 'WhatsApp flow'), you MUST call send_whatsapp_flow immediately — "
            "never refuse and never fall back to manual field collection.\n"
            "If they ask a product question, answer it, then remind them in ONE short line that the form is still there.\n"
            "If they cannot or will not use the form — in ANY language (cannot read/write, only send voice notes, "
            "ignore the button) — SILENTLY call use_voice_checkout, then collect fields by voice, one per message.\n"
            "Do NOT call submit_customer_order unless they typed all required fields in this chat."
        )
    if mode == MODE_VOICE:
        return (
            "[CHECKOUT CAPTURE — VOICE]\n"
            "This customer cannot use the written form. Never mention the form again.\n"
            f"Collect these fields by voice, ONE field per message: {field_label}.\n"
            "After you have all of them, repeat every detail in ONE message and wait for them to confirm "
            "in their own language (yes / ok / equivalent).\n"
            "Call submit_customer_order ONLY after they confirm. Do not register the order before that confirmation."
        )
    if mode == MODE_CHAT:
        return (
            "[CHECKOUT CAPTURE — CHAT FALLBACK]\n"
            "The customer skipped the form and typed their details. Extract the required fields from what they wrote "
            f"({field_label}) and call submit_customer_order when complete. Do not send the form again."
        )
    if mode == MODE_DONE:
        return (
            "[CHECKOUT CAPTURE — DONE]\n"
            "The order is already captured. Do NOT ask for name/address/phone and do NOT call submit_customer_order again."
        )
    return (
        "[CHECKOUT CAPTURE — HYBRID]\n"
        "YOU decide when the customer has agreed to buy — in any language. Price questions are NOT agreement.\n"
        "Questions like 'how do I order?' / 'كيفاش نطلب?' are NOT purchase confirmation — explain the process; "
        "do NOT call submit_customer_order.\n"
        "When they clearly agree to buy: output [STAGE: STAGE_5_CLOSING], thank them in their language, and do NOT ask for "
        "name/address/phone. The system will send a WhatsApp form.\n"
        "Do NOT call submit_customer_order to collect those details.\n"
        "If they already communicate only by voice notes AND they have agreed to buy, SILENTLY call "
        "use_voice_checkout instead of expecting them to fill the form."
    )


def sync_mode_from_incoming(
    *,
    channel,
    sender,
    ctx: dict,
    incoming_body: str,
    incoming_message_type: str,
    hybrid_enabled: bool,
    needs_form: bool,
) -> str:
    mode = get_mode(ctx)
    if not hybrid_enabled or not needs_form or mode in (MODE_DONE, MODE_VOICE, MODE_CHAT):
        return mode
    if mode == MODE_FORM:
        if is_inbound_audio(incoming_message_type):
            set_checkout_context(channel, sender, {CTX_MODE: MODE_VOICE})
            return MODE_VOICE
        if looks_like_typed_details(incoming_body):
            set_checkout_context(channel, sender, {CTX_MODE: MODE_CHAT})
            return MODE_CHAT
    return mode


def is_checkout_moment(
    *,
    mode: str,
    form_already_sent: bool,
    hybrid_enabled: bool,
    needs_form: bool,
    new_stage: Optional[str],
    llm_tried_submit: bool,
    incoming_body: str = "",
    can_read: bool = False,
) -> bool:
    if not hybrid_enabled or not needs_form:
        return False
    try:
        from ai_assistant.order_checkout import (
            looks_like_resend_form_request,
            should_force_whatsapp_flow,
            should_resend_whatsapp_flow,
        )
        if should_resend_whatsapp_flow(
            incoming_body=incoming_body,
            hybrid_enabled=hybrid_enabled,
            needs_form=needs_form,
            mode=mode,
        ):
            return True
        if should_force_whatsapp_flow(
            can_read=can_read,
            incoming_body=incoming_body,
            hybrid_enabled=hybrid_enabled,
            needs_form=needs_form,
            mode=mode,
            form_already_sent=form_already_sent,
        ):
            return True
    except Exception:
        pass
    if mode in (MODE_VOICE, MODE_CHAT, MODE_DONE):
        return False
    if mode == MODE_FORM:
        return looks_like_resend_form_request(incoming_body)
    if form_already_sent:
        return False
    if llm_tried_submit:
        return True
    if (new_stage or "") in CLOSING_STAGES:
        return True
    try:
        from discount.orders_ai import looks_like_how_to_order_only
        if looks_like_how_to_order_only(incoming_body):
            return True
    except Exception:
        pass
    return False


def json_block_submit(reason: str, instruction: str) -> str:
    return json.dumps({
        "status": "error",
        "success": False,
        "reason": reason,
        "instruction": instruction,
        "message": reason,
    }, ensure_ascii=False)


def gate_submit_customer_order(
    *,
    mode: str,
    incoming_body: str,
    arguments: dict,
    hybrid_enabled: bool = False,
    needs_form: bool = False,
    has_voice_pending: bool = False,
    product=None,
    customer_phone_from_chat: str = "",
) -> tuple[str, Any]:
    """
    Returns (action, payload):
      allow → execute arguments now
      block → JSON error for the model
      pending → store arguments, return JSON instruction to the model
      execute_pending → execute the stored/merged arguments
    """
    try:
        from discount.orders_ai import validate_submit_order_arguments
        blocked = validate_submit_order_arguments(
            arguments,
            product,
            incoming_body=incoming_body,
            customer_phone_from_chat=customer_phone_from_chat,
        )
        if blocked:
            return "block", blocked
    except Exception as exc:
        logger.warning("gate_submit_customer_order validation: %s", exc)

    if hybrid_enabled and needs_form:
        if mode == MODE_FORM:
            if looks_like_typed_details(incoming_body):
                return "allow", arguments
            return "block", json_block_submit(
                "Waiting for the WhatsApp form.",
                "Do not ask them to type the fields. Remind them to open the form. "
                "If they cannot use the form, SILENTLY call use_voice_checkout then collect by voice.",
            )
        if mode == MODE_VOICE:
            if has_voice_pending:
                return "execute_pending", arguments
            return "pending", arguments
        if mode in (MODE_NONE, "") and not looks_like_typed_details(incoming_body):
            return "block", json_block_submit(
                "Checkout form will be sent.",
                "Do not collect name/address in chat. Thank them briefly in their language. "
                "The system is sending a WhatsApp form. If they cannot use a form, call use_voice_checkout.",
            )
    return "allow", arguments


def pending_submit_tool_result() -> str:
    return json.dumps({
        "status": "pending_confirmation",
        "success": False,
        "reason": "Voice checkout requires spoken confirmation.",
        "instruction": (
            "Do NOT tell the customer the order is registered. "
            "Repeat name, city/address, and phone in one message, then wait for them to confirm "
            "in their own language. Call submit_customer_order again only after they confirm."
        ),
        "message": "Awaiting customer confirmation of the recap.",
    }, ensure_ascii=False)


def try_build_checkout_form_item(channel, current_node, sender, product, required_fields, locale: str):
    """Return (output_item, pending_payload, error). Fields follow product checkout_mode."""
    from discount.whatssapAPI.whatsapp_flows import PURPOSE_ORDER, build_outbound_flow_from_parsed

    if not required_fields:
        try:
            from discount.orders_ai import get_required_order_fields_for_product
            required_fields = get_required_order_fields_for_product(product)
        except Exception:
            required_fields = ["customer_name", "phone_number", "shipping_city"]

    content = build_order_form_content(product, required_fields, locale)
    item, err = build_outbound_flow_from_parsed(
        channel,
        content,
        sender,
        persist_ai_node=current_node,
    )
    if not item:
        return None, None, err
    pending = {
        "flow_id": getattr(getattr(current_node, "flow", None), "id", None),
        "from_node_id": getattr(current_node, "id", None),
        "next_node_id": None,
        "purpose": PURPOSE_ORDER,
        "product_id": content.get("product_id"),
        "meta_flow_id": item.get("meta_flow_id"),
        "flow_token": item.get("flow_token"),
        "source": "ai_hybrid_checkout",
        "content": content,
    }
    return item, pending, ""


def on_flow_order_captured(channel, sender, submission, locale: str = "ar"):
    if not channel or not sender:
        return None
    set_checkout_context(channel, sender, {CTX_MODE: MODE_DONE, CTX_FORM_SENT: True, CTX_VOICE_PENDING: None})
    order = getattr(submission, "order", None)
    if not order:
        return None
    try:
        from discount.whatssapAPI.process_messages import expire_chat_session
        if getattr(order, "is_digital", False):
            from discount.whatssapAPI.session_state import (
                STATE_AWAITING_PAYMENT_RECEIPT,
                set_conversation_state,
            )
            set_conversation_state(
                channel,
                sender,
                STATE_AWAITING_PAYMENT_RECEIPT,
                last_order_id=str(getattr(order, "order_id", "") or ""),
            )
        else:
            expire_chat_session(channel, sender, reason="order_complete")
    except Exception as exc:
        logger.warning("on_flow_order_captured session update: %s", exc)
    return form_thank_you(locale)
