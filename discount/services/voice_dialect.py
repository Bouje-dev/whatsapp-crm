"""
Resolve the spoken dialect label for the merchant's effective ElevenLabs voice so the LLM
can match Text-to-Speech pronunciation (voice–dialect coupling).

Dialect hierarchy for prompts:
  1) ElevenLabs / channel voice selected (gallery, clone, channel.voice_dialect) — ignore phone.
  2) No voice id: infer from customer phone country code.
  3) Else channel.voice_dialect, then platform default.
"""

from django.conf import settings

from typing import Optional

from discount.models import VOICE_DIALECT_DEFAULT, VoiceGalleryEntry, VoicePersona, dialect_key_to_display


def dialect_label_from_node_language(node) -> Optional[str]:
    """
    Priority 1 for LLM/TTS alignment: explicit flow node_language (e.g. AR_MA → Moroccan Darija).
    Returns None when the node does not specify an Arabic regional dialect we map (voice hierarchy applies).
    """
    if not node:
        return None
    raw = (getattr(node, "node_language", None) or "").strip()
    if not raw:
        return None
    s = raw.upper().replace("-", "_")
    key = None
    if s.startswith("AR_MA") or s in ("MA",):
        key = "MA_DARIJA"
    elif s.startswith("AR_SA") or s == "SA":
        key = "SA_ARABIC"
    elif s.startswith("AR_EG") or s.startswith("EG_"):
        key = "EG_ARABIC"
    elif "GULF" in s or s.startswith("AR_GCC") or s.startswith("AR_AE") or s.startswith("AR_QA"):
        key = "GULF_ARABIC"
    elif s.startswith("AR_LB") or s.startswith("AR_SY") or "LEV" in s:
        key = "LEV_ARABIC"
    elif s == "MSA" or s.startswith("AR_MSA"):
        key = "MSA"
    elif s.startswith("OTHER") or s == "MULTILINGUAL":
        key = "OTHER"
    else:
        return None
    return dialect_key_to_display(key)


def channel_has_selected_tts_voice(channel, node=None) -> bool:
    """True if merchant picked a concrete voice (gallery id or cloned ElevenLabs id)."""
    from discount.whatssapAPI.process_messages import _voice_settings_for_node

    if not channel:
        return False
    vc = _voice_settings_for_node(channel, node)
    sid = (getattr(vc, "selected_voice_id", None) or "").strip()
    cloned = (getattr(vc, "cloned_voice_id", None) or "").strip()
    return bool(sid or cloned)


def dialect_from_customer_phone(customer_phone) -> str | None:
    """
    Map customer WhatsApp number to a dialect display label (Priority 2 when no TTS voice id).
    """
    from ai_assistant.services import infer_market_from_phone

    m = infer_market_from_phone(customer_phone or "")
    if m == "MA":
        return dialect_key_to_display("MA_DARIJA")
    if m == "SA":
        return dialect_key_to_display("SA_ARABIC")
    if m == "GCC":
        return dialect_key_to_display("GULF_ARABIC")
    return None


def resolve_dialect_for_llm_hierarchy(channel, node=None, customer_phone=None) -> str:
    """
    Human-readable dialect for LLM + TTS alignment.

    P1 (highest): Active flow node ``node_language`` → regional dialect label for prompts.
    P2: Voice / clone selected → gallery / persona / channel.voice_dialect (phone ignored when voice id set).
    P3: Phone country dialect when no voice id.
    P4: channel.voice_dialect, settings, platform default.
    """
    node_label = dialect_label_from_node_language(node)
    if node_label:
        return node_label

    if channel and channel_has_selected_tts_voice(channel, node):
        return resolve_voice_dialect_for_prompt(channel, node)

    if channel:
        phone_d = dialect_from_customer_phone(customer_phone)
        if phone_d:
            return phone_d
        ch_d = getattr(channel, "voice_dialect", None)
        if ch_d:
            return dialect_key_to_display(ch_d)

    dk = getattr(settings, "DEFAULT_VOICE_DIALECT", None) or VOICE_DIALECT_DEFAULT
    return dialect_key_to_display(dk)


def resolve_voice_dialect_for_prompt(channel, node=None) -> str:
    """
    Human-readable dialect name for system prompt injection.
    Resolution: gallery entry by voice_id → merchant clone persona → channel.voice_dialect → settings → platform default.
    """
    from discount.whatssapAPI.process_messages import _voice_settings_for_node

    if not channel:
        dk = getattr(settings, "DEFAULT_VOICE_DIALECT", None) or VOICE_DIALECT_DEFAULT
        return dialect_key_to_display(dk)

    vc = _voice_settings_for_node(channel, node)
    voice_id = (getattr(vc, "selected_voice_id", None) or "").strip()
    merchant = getattr(channel, "owner", None)

    if voice_id:
        row = VoiceGalleryEntry.objects.filter(elevenlabs_voice_id=voice_id).only("dialect").first()
        if row:
            return dialect_key_to_display(getattr(row, "dialect", None) or VOICE_DIALECT_DEFAULT)

    if voice_id and merchant:
        p = (
            VoicePersona.objects.filter(owner=merchant, voice_id=voice_id)
            .only("dialect")
            .first()
        )
        if p:
            return dialect_key_to_display(getattr(p, "dialect", None) or VOICE_DIALECT_DEFAULT)

    ch_d = getattr(channel, "voice_dialect", None)
    if ch_d:
        return dialect_key_to_display(ch_d)

    dk = getattr(settings, "DEFAULT_VOICE_DIALECT", None) or VOICE_DIALECT_DEFAULT
    return dialect_key_to_display(dk)


def merchant_voice_mode_enabled(channel) -> bool:
    """
    Store-level preference: Voice-enabled vs Text-only.

    Maps to product docs ``merchant.voice_settings.is_active`` — stored as ``WhatsAppChannel.ai_voice_enabled``.
    ``response_mode == voice_enabled`` also counts as voice-on.
    """
    if not channel:
        return False
    rm = (getattr(channel, "response_mode", None) or "").strip().lower()
    if rm == "voice_enabled":
        return True
    if rm in ("text_only", "auto"):
        return False
    return bool(getattr(channel, "ai_voice_enabled", False))


def resolve_sales_prompt_response_mode(channel, node=None) -> str:
    """
    Effective delivery mode for the sales-agent system prompt.

    Returns ``text_only``, ``voice_enabled``, or ``auto``.
    Node TEXT_ONLY / AUDIO_ONLY override the store. Node AUTO / AUTO_SMART
    select LLM-decided auto. Otherwise use ``WhatsAppChannel.response_mode``,
    falling back to ``ai_voice_enabled``.
    """
    if node is not None:
        rm = (getattr(node, "response_mode", None) or "").strip()
        ru = rm.upper()
        if ru == "TEXT_ONLY":
            return "text_only"
        if ru in ("AUTO", "AUTO_SMART") or rm.lower() == "auto":
            return "auto"
        if ru == "AUDIO_ONLY" or bool(getattr(node, "voice_enabled", False)):
            return "voice_enabled"
    ch = (getattr(channel, "response_mode", None) or "").strip().lower() if channel else ""
    if ch in ("text_only", "voice_enabled", "auto"):
        return ch
    return "voice_enabled" if merchant_voice_mode_enabled(channel) else "text_only"


def prompt_uses_voice_delivery_rules(channel, node=None) -> bool:
    """True when the LLM must write a spoken TTS script instead of a WhatsApp text."""
    return resolve_sales_prompt_response_mode(channel, node) == "voice_enabled"


def should_send_sales_reply_as_voice(
    channel, node, result=None, reply_text="", force_voice_mode=None, customer_phone=None
) -> bool:
    """
    Runtime router: whether this turn's customer-facing reply is TTS audio.

    ``auto`` uses the LLM ``reply_type`` from structured JSON. Missing/invalid
    JSON falls back to text (cheaper), unless accessibility ``force_voice_mode``
    is on — then every auto reply is voice.
    """
    if force_voice_mode is None and customer_phone:
        try:
            from discount.services.checkout_state import is_force_voice_mode

            force_voice_mode = is_force_voice_mode(channel, customer_phone)
        except Exception:
            force_voice_mode = False
    mode = resolve_sales_prompt_response_mode(channel, node)
    if mode == "text_only":
        return False
    if mode == "voice_enabled":
        return True
    if mode == "auto":
        if force_voice_mode:
            return True
        rtype = ""
        if isinstance(result, dict):
            rtype = str(result.get("reply_type") or "").strip().lower()
        if rtype == "voice":
            return True
        if rtype == "text":
            return False
        return False
    return False


def node_reply_prefers_tts(channel, node=None) -> bool:
    """
    True when the primary LLM should use AUDIO SCRIPT rules (including spelled-out
  numbers in the model output). False for TEXT_ONLY and AUTO_SMART nodes — those
  replies keep numerals in the LLM text; VoiceFormatterMiddleware spells numbers
  only when the send pipeline actually delivers a voice note.

    Do NOT key this off channel-level ``ai_voice_enabled`` alone: a merchant can
    have voice on the account while a flow node is TEXT_ONLY.
    """
    if node is not None:
        rm = (getattr(node, "response_mode", None) or "").strip()
        if rm == "TEXT_ONLY":
            return False
        if rm == "AUDIO_ONLY":
            return True
        if rm in ("AUTO_SMART", "AUTO"):
            return False
        if getattr(node, "voice_enabled", False):
            return True
        return False
    return False


def should_inject_tts_dialect_prompt(channel, node=None) -> bool:
    """
    True when assistant replies may be converted to speech — inject strict dialect
    alignment so LLM output matches the selected ElevenLabs/OpenAI voice.

    - Channel \"Audio / Voice notes\" (ai_voice_enabled): always.
    - AI agent node set to AUDIO_ONLY, AUTO_SMART, or legacy voice_enabled (not TEXT_ONLY).
    """
    if not channel:
        return False
    if getattr(channel, "ai_voice_enabled", False):
        return True
    if (getattr(channel, "response_mode", None) or "").strip().lower() in ("voice_enabled", "auto"):
        return True
    if node is None:
        return False
    rm = (getattr(node, "response_mode", None) or "").strip()
    if rm == "TEXT_ONLY":
        return False
    if rm in ("AUDIO_ONLY", "AUTO_SMART", "AUTO"):
        return True
    if getattr(node, "voice_enabled", False):
        return True
    return False
