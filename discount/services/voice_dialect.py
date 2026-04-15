"""
Resolve the spoken dialect label for the merchant's effective ElevenLabs voice so the LLM
can match Text-to-Speech pronunciation (voice–dialect coupling).

Dialect hierarchy for prompts:
  1) ElevenLabs / channel voice selected (gallery, clone, channel.voice_dialect) — ignore phone.
  2) No voice id: infer from customer phone country code.
  3) Else channel.voice_dialect, then platform default.
"""

from django.conf import settings

from discount.models import VOICE_DIALECT_DEFAULT, VoiceGalleryEntry, VoicePersona, dialect_key_to_display


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

    P1: Voice / clone selected → resolve from gallery, persona, then channel.voice_dialect / default
        (phone country is ignored).
    P2: No voice id → phone country dialect.
    P3: channel.voice_dialect, then platform default.
    """
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
    Conditional prompt routing: when True, LLM uses AUDIO SCRIPT MODE; when False, TEXT MESSAGING MODE.

    Maps to product docs ``merchant.voice_settings.is_active`` — stored as ``WhatsAppChannel.ai_voice_enabled``.
    """
    return bool(channel and getattr(channel, "ai_voice_enabled", False))


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
    if node is None:
        return False
    rm = (getattr(node, "response_mode", None) or "").strip()
    if rm == "TEXT_ONLY":
        return False
    if rm in ("AUDIO_ONLY", "AUTO_SMART"):
        return True
    if getattr(node, "voice_enabled", False):
        return True
    return False
