"""
Localized default fulfillment thank-you messages for digital product delivery.

Used when the merchant has not set ``Products.fulfillment_message``.
Language is resolved from the active AI flow node, channel Voice Studio
settings, or the customer phone prefix — never hardcoded to one dialect.
"""

from __future__ import annotations

from typing import Optional

# (language_code, has_asset) → professional thank-you text
_FULFILLMENT_MESSAGES: dict[tuple[str, bool], str] = {
    ("en", True): "Thank you for your trust! 🎉\n\nHere are your product details:",
    ("en", False): "Thank you for your trust! 🎉 Your order has been confirmed.",
    ("fr", True): "Merci de votre confiance ! 🎉\n\nVoici les détails de votre produit :",
    ("fr", False): "Merci de votre confiance ! 🎉 Votre commande a été confirmée.",
    ("ar", True): "شكراً لثقتك بنا! 🎉\n\nإليك تفاصيل طلبك:",
    ("ar", False): "شكراً لثقتك بنا! 🎉 تم تأكيد طلبك بنجاح.",
    ("ar-MA", True): "شكراً على ثقتك فينا! 🎉\n\nتفضل تفاصيل المنتج ديالك:",
    ("ar-MA", False): "شكراً على ثقتك فينا! 🎉 تم تأكيد الطلبية ديالك.",
    ("ar-SA", True): "شكراً لثقتك بنا! 🎉\n\nتفضل تفاصيل منتجك:",
    ("ar-SA", False): "شكراً لثقتك بنا! 🎉 تم تأكيد طلبك بنجاح.",
}

_DEFAULT_LANGUAGE = "ar"


def normalize_fulfillment_language_code(raw) -> Optional[str]:
    """
    Map channel / node / phone hints to a supported fulfillment language code.

    Supported codes: ``en``, ``fr``, ``ar``, ``ar-MA``, ``ar-SA``.
    Returns ``None`` when the hint is empty or ``AUTO`` (caller should
    try the next source in the resolution chain).
    """
    if raw is None:
        return None
    s = str(raw).strip().lower().replace("_", "-")
    if not s or s in ("auto", "multilingual", "other"):
        return None
    if s in ("en", "en-us"):
        return "en"
    if s.startswith("fr"):
        return "fr"
    if s in ("ar-ma", "ma", "ma-darija"):
        return "ar-MA"
    if s in (
        "ar-sa", "sa",
        "ar-gcc", "ar-ae", "ar-qa", "ar-kw", "ar-bh", "ar-om",
        "gcc", "gulf",
    ):
        return "ar-SA"
    if s in ("ar", "ar-msa", "msa"):
        return "ar"
    if s.startswith("ar-"):
        return "ar"
    return None


def _from_customer_phone(phone) -> Optional[str]:
    try:
        from ai_assistant.services import infer_market_from_phone

        market = infer_market_from_phone(phone or "")
    except Exception:
        return None
    if market == "MA":
        return "ar-MA"
    if market in ("SA", "GCC"):
        return "ar-SA"
    return None


def resolve_fulfillment_language_code(
    order=None,
    channel=None,
    customer_phone=None,
) -> str:
    """
    Resolve the standardized language code for fulfillment fallbacks.

    Priority:
      1. Active ``ChatSession`` → ``Node.node_language`` (agent language)
      2. ``WhatsAppChannel.voice_language`` (store Voice Studio setting)
      3. Customer phone country prefix
      4. Default: Standard Arabic (``ar``)
    """
    phone = customer_phone
    if order is not None:
        phone = phone or getattr(order, "customer_phone", None)
        channel = channel or getattr(order, "channel", None)

    # 1) Active AI flow node language for this customer chat
    if channel and phone:
        try:
            from discount.models import ChatSession

            session = (
                ChatSession.objects
                .filter(channel=channel, customer_phone=phone)
                .select_related("active_node")
                .first()
            )
            if session and session.active_node:
                node_lang = getattr(session.active_node, "node_language", None)
                resolved = normalize_fulfillment_language_code(node_lang)
                if resolved:
                    return resolved
        except Exception:
            pass

    # 2) Channel store / agent voice language
    if channel:
        vl = (getattr(channel, "voice_language", None) or "").strip()
        if vl and vl.upper() != "AUTO":
            resolved = normalize_fulfillment_language_code(vl)
            if resolved:
                return resolved

    # 3) Customer phone market
    resolved = _from_customer_phone(phone)
    if resolved:
        return resolved

    return _DEFAULT_LANGUAGE


def get_localized_fulfillment_message(language_code, has_asset: bool = True) -> str:
    """
    Return a professional thank-you fallback for digital fulfillment.

    Args:
        language_code: e.g. ``en``, ``fr``, ``ar``, ``ar-MA``, ``ar-SA``
        has_asset: ``True`` when credentials or a download link follow the message.

    Falls back to Standard Arabic (``ar``), then English (``en``), for
    missing or unsupported codes.
    """
    key = normalize_fulfillment_language_code(language_code) or _DEFAULT_LANGUAGE
    msg = _FULFILLMENT_MESSAGES.get((key, has_asset))
    if msg:
        return msg
    if key.startswith("ar-"):
        msg = _FULFILLMENT_MESSAGES.get(("ar", has_asset))
        if msg:
            return msg
    msg = _FULFILLMENT_MESSAGES.get((_DEFAULT_LANGUAGE, has_asset))
    if msg:
        return msg
    return _FULFILLMENT_MESSAGES.get(("en", has_asset), _FULFILLMENT_MESSAGES[("en", True)])


# Post-sale replacement delivery (after merchant approves a support ticket)
_SUPPORT_REPLACEMENT_MESSAGES: dict[tuple[str, bool], str] = {
    ("en", True): "We reviewed your case and approved a replacement. 🔄\n\nHere are your new product details:",
    ("en", False): "We reviewed your case. Your replacement request has been processed.",
    ("fr", True): "Nous avons examiné votre demande et approuvé un remplacement. 🔄\n\nVoici vos nouvelles informations :",
    ("fr", False): "Nous avons examiné votre demande. Votre remplacement a été traité.",
    ("ar", True): "تمت مراجعة طلبك واعتماد استبدال جديد. 🔄\n\nإليك تفاصيل منتجك الجديد:",
    ("ar", False): "تمت مراجعة طلبك ومعالجة طلب الاستبدال.",
    ("ar-MA", True): "تمت مراجعة الطلب ديالك واعتماد استبدال جديد. 🔄\n\nهاكوم التفاصيل الجديدة ديال المنتج:",
    ("ar-MA", False): "تمت مراجعة الطلب ديالك ومعالجة الاستبدال.",
    ("ar-SA", True): "تمت مراجعة طلبك واعتماد استبدال جديد. 🔄\n\nتفضل تفاصيل منتجك الجديد:",
    ("ar-SA", False): "تمت مراجعة طلبك ومعالجة طلب الاستبدال.",
}

_SUPPORT_REJECTION_MESSAGES: dict[str, str] = {
    "en": (
        "We reviewed the proof you provided. Unfortunately we cannot approve a replacement "
        "because the evidence is insufficient or the warranty terms do not apply. "
        "Please contact us if you have additional questions."
    ),
    "fr": (
        "Nous avons examiné la preuve fournie. Malheureusement, nous ne pouvons pas approuver "
        "un remplacement car les éléments sont insuffisants ou la garantie ne s'applique pas."
    ),
    "ar": (
        "تمت مراجعة الإثبات الذي أرسلته. للأسف لا يمكننا اعتماد استبدال لأن الدليل غير كافٍ "
        "أو أن شروط الضمان لا تنطبق على هذه الحالة."
    ),
    "ar-MA": (
        "تمت مراجعة الدليل اللي صيفطيتي. للأسف ما نقدروش نعطيو استبدال حيت الإثبات ما كافيش "
        "أو الضمان ما كيشملش هاد الحالة."
    ),
    "ar-SA": (
        "تمت مراجعة الإثبات الذي أرسلته. للأسف لا يمكننا اعتماد استبدال لأن الدليل غير كافٍ "
        "أو أن شروط الضمان لا تنطبق."
    ),
}


def get_localized_support_replacement_message(language_code, has_asset: bool = True) -> str:
    """Thank-you / intro line before replacement credentials are sent."""
    key = normalize_fulfillment_language_code(language_code) or _DEFAULT_LANGUAGE
    msg = _SUPPORT_REPLACEMENT_MESSAGES.get((key, has_asset))
    if msg:
        return msg
    if key.startswith("ar-"):
        msg = _SUPPORT_REPLACEMENT_MESSAGES.get(("ar", has_asset))
        if msg:
            return msg
    return _SUPPORT_REPLACEMENT_MESSAGES.get(
        (_DEFAULT_LANGUAGE, has_asset),
        _SUPPORT_REPLACEMENT_MESSAGES[("en", has_asset)],
    )


def get_localized_support_rejection_message(language_code) -> str:
    """WhatsApp message when the merchant rejects a support complaint."""
    key = normalize_fulfillment_language_code(language_code) or _DEFAULT_LANGUAGE
    msg = _SUPPORT_REJECTION_MESSAGES.get(key)
    if msg:
        return msg
    if key.startswith("ar-"):
        return _SUPPORT_REJECTION_MESSAGES.get("ar", _SUPPORT_REJECTION_MESSAGES["en"])
    return _SUPPORT_REJECTION_MESSAGES.get(_DEFAULT_LANGUAGE, _SUPPORT_REJECTION_MESSAGES["en"])


# Payment receipt rejection (digital order → back to pending_payment)
_PAYMENT_REJECTION_MESSAGES: dict[str, str] = {
    "en": (
        "⚠️ Sorry, we couldn't verify your payment receipt.\n\n"
        "📌 Reason: {reason}\n\n"
        "Please check the transaction and send a clear screenshot or PDF to proceed."
    ),
    "fr": (
        "⚠️ Désolé, nous n'avons pas pu vérifier votre reçu de paiement.\n\n"
        "📌 Motif : {reason}\n\n"
        "Veuillez vérifier la transaction et envoyer une capture ou un PDF clair pour continuer."
    ),
    "ar": (
        "⚠️ عذراً، لم نتمكن من التحقق من إيصال الدفع الخاص بك.\n\n"
        "📌 السبب: {reason}\n\n"
        "يرجى التحقق من المعاملة وإرسال صورة واضحة أو ملف PDF لإتمام طلبك."
    ),
    "ar-MA": (
        "⚠️ عذراً، ما قدرناش نأكدو وصل الدفع ديالك.\n\n"
        "📌 السبب: {reason}\n\n"
        "عفاك تأكد من العملية وصيفط لينا وصل واضح (تصويرة أو PDF) باش نقدرو نأكدو ليك الطلبية."
    ),
    "ar-SA": (
        "⚠️ عذراً، لم نتمكن من التحقق من إيصال الدفع.\n\n"
        "📌 السبب: {reason}\n\n"
        "يرجى التحقق من المعاملة وإرسال صورة واضحة أو ملف PDF لإكمال طلبك."
    ),
}


def get_localized_payment_rejection_message(language_code: str, reason: str) -> str:
    """
    WhatsApp message when the merchant rejects a payment receipt.
    ``reason`` is the seller-provided explanation (never omitted in the text).
    """
    reason_text = (reason or "").strip() or "—"
    key = normalize_fulfillment_language_code(language_code) or _DEFAULT_LANGUAGE
    template = _PAYMENT_REJECTION_MESSAGES.get(key)
    if not template and key.startswith("ar-"):
        template = _PAYMENT_REJECTION_MESSAGES.get("ar")
    if not template:
        template = _PAYMENT_REJECTION_MESSAGES.get(
            _DEFAULT_LANGUAGE, _PAYMENT_REJECTION_MESSAGES["en"]
        )
    return template.format(reason=reason_text)


def get_localized_rejection_message(language_code: str, reason: str) -> str:
    """Alias for proactive WhatsApp rejection notices (merchant dashboard API)."""
    return get_localized_payment_rejection_message(language_code, reason)


def save_payment_rejection_notice_from_outbound(channel, customer_phone, body: str) -> None:
    """
    After an outbound text is sent (merchant API or AI agent), persist the
    customer-facing rejection notice on the open pending_payment order when
    a merchant rejection reason is on file and no notice was saved yet.
    """
    text = (body or "").strip()
    if not channel or not (customer_phone or "").strip() or not text:
        return
    try:
        from discount.models import SimpleOrder

        order = (
            SimpleOrder.objects.filter(
                channel=channel,
                customer_phone=customer_phone,
                is_digital=True,
                status="pending_payment",
            )
            .exclude(payment_rejection_reason__isnull=True)
            .exclude(payment_rejection_reason="")
            .order_by("-created_at")
            .first()
        )
        if not order:
            return
        if (getattr(order, "payment_rejection_notice_text", None) or "").strip():
            return
        order.payment_rejection_notice_text = text[:4096]
        order.save(update_fields=["payment_rejection_notice_text"])
    except Exception as exc:
        logger.warning("save_payment_rejection_notice_from_outbound: %s", exc)


def resolve_active_digital_payment_order(channel, customer_phone, conversation_state=None):
    """
    Latest digital order in a payment-wait FSM for this chat.
    Returns the SimpleOrder row or None.
    """
    state = (conversation_state or "").strip().upper()
    if state != "AWAITING_PAYMENT_RECEIPT":
        return None
    if not channel or not (customer_phone or "").strip():
        return None
    try:
        from discount.models import SimpleOrder

        return (
            SimpleOrder.objects.filter(
                channel=channel,
                customer_phone=customer_phone,
                is_digital=True,
                status__in=("pending_payment", "pending_verification"),
            )
            .order_by("-created_at")
            .first()
        )
    except Exception:
        return None


def resolve_payment_rejection_context_for_chat(
    channel,
    customer_phone,
    conversation_state=None,
) -> Optional[dict[str, str]]:
    """
    Payment FSM context for AI prompts: merchant rejection reason + order status.
    """
    order = resolve_active_digital_payment_order(
        channel, customer_phone, conversation_state,
    )
    if not order:
        return None
    merchant_reason = (getattr(order, "payment_rejection_reason", None) or "").strip()
    return {
        "merchant_reason": merchant_reason,
        "order_status": (getattr(order, "status", None) or "").strip(),
    }


def resolve_payment_rejection_reason_for_chat(
    channel,
    customer_phone,
    conversation_state=None,
) -> Optional[str]:
    """
    Merchant rejection reason only (not the proactive notice text) for AI prompts.
    """
    ctx = resolve_payment_rejection_context_for_chat(
        channel, customer_phone, conversation_state,
    )
    if not ctx:
        return None
    reason = (ctx.get("merchant_reason") or "").strip()
    return reason or None
