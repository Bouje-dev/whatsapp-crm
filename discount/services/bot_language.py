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


def effective_output_language_for_node(node) -> OutputLang:
    """
    Priority over channel voice_language: when the active flow node sets node_language
    (e.g. AR_SA, FR_FR), lock LLM output language for that node.
    """
    if not node:
        return None
    nl = (getattr(node, "node_language", None) or "").strip().upper().replace("-", "_")
    if not nl:
        return None
    if nl.startswith("FR"):
        return "fr"
    if nl.startswith("EN"):
        return "en"
    if nl.startswith("AR"):
        return "ar"
    return None


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
