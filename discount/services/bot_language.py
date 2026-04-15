"""
Resolve LLM output language lock from channel Voice Studio language only.

Uses WhatsAppChannel.voice_language:
  FR_FR → French (formal corporate prompt, no Arabic dialect coupling)
  AR_MA / AR_SA → Arabic alignment
  EN_US → English
  AUTO → None (follow conversation / dialect / TTS rules as before)
"""

from __future__ import annotations

from typing import Literal, Optional

OutputLang = Optional[Literal["fr", "ar", "en"]]


def effective_bot_language(channel) -> OutputLang:
    """
    Return 'fr', 'ar', 'en', or None.

    None means: no fixed output language — follow voice gallery dialect and existing TTS rules.
    """
    if not channel:
        return None
    vl = (getattr(channel, "voice_language", None) or "AUTO").strip().upper()
    if vl == "FR_FR":
        return "fr"
    if vl in ("AR_MA", "AR_SA"):
        return "ar"
    if vl == "EN_US":
        return "en"
    return None
