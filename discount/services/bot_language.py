"""
Resolve LLM output language lock from channel Voice Studio language.

Uses WhatsAppChannel.voice_language:
  FR_FR → French (formal corporate prompt, no Arabic dialect coupling)
  AR_MA / AR_SA → Arabic alignment
  EN_US → English
  AUTO → detect from customer messages (last turns), then phone/voice fallback
"""

from __future__ import annotations

import re
from typing import Literal, Optional

OutputLang = Optional[Literal["fr", "ar", "en"]]

_ARABIC_SCRIPT_RE = re.compile(r"[\u0600-\u06FF]")
_LATIN_WORD_RE = re.compile(r"[a-zA-ZÀ-ÿ]{2,}")

# Vision / STT / payment classifiers stored as customer body — never use for language detect.
_SYSTEM_CONTEXT_BODY_RE = re.compile(
    r"^\s*\[SYSTEM(?:\s+(?:IMAGE|VISION|PAYMENT|STT)[^\]]*)?\]",
    re.IGNORECASE,
)
# Legacy vision bodies written before the [SYSTEM …] prefix.
_LEGACY_VISION_BODY_RE = re.compile(
    r"^\s*The customer sent an image\b",
    re.IGNORECASE,
)

# Latin-script Moroccan Franco / Arabizi markers (customer wrote Darija in Latin letters).
_FRANCO_DARIJA_RE = re.compile(
    r"(?i)(?:"
    r"\b(?:wach|wash|bghit|bghiti|bghina|mafiha|mafihach|mafihech|chhal|bzaf|bzff|"
    r"wakha|waxa|waxha|labas|mzyan|mezian|meziane|ach|achnu|chno|chnoua|fin|kayn|kayna|"
    r"sahbi|khoya|khouya|kifash|kifach|3andi|3ndk|3lik|7aja|9al|drwi|drari|"
    r"wachi|walo|machi|ghadi|ghan|bgha|bghat|safi|wakhaa|ouiwa|iwa)\b|"
    r"[379]\w{2,}"
    r")"
)

_FRENCH_HINTS = re.compile(
    r"\b(je|tu|vous|nous|est|sont|bonjour|merci|français|francais|parle|parler|parlez|"
    r"seulement|uniquement|oui|non|comment|prix|livraison|commander|produit|svp|s'il|"
    r"avec|pour|dans|c'est|quoi|combien|bonsoir|salut|madame|monsieur|chez|votre|"
    r"une|des|les|pas|ne|que|le|la|du|de|au|aux)\b",
    re.IGNORECASE,
)
_ENGLISH_HINTS = re.compile(
    r"\b(the|you|your|hello|hi|please|thank|thanks|english|speak|speaks|speaking|"
    r"only|how|much|price|delivery|order|product|want|need|can|could|would|"
    r"what|when|where|why|buy|shipping|help|sir|madam)\b",
    re.IGNORECASE,
)
_FRENCH_ONLY_PHRASES = re.compile(
    r"(parle\s+(seulement|uniquement)\s+fran|"
    r"je\s+(ne\s+)?parle\s+(que\s+)?(le\s+)?fran|"
    r"uniquement\s+en\s+fran|"
    r"seulement\s+en\s+fran|"
    r"je\s+ne\s+comprends\s+pas\s+l'arabe|"
    r"i\s+only\s+speak\s+french|"
    r"only\s+french|"
    r"speak\s+only\s+french)",
    re.IGNORECASE,
)
_ENGLISH_ONLY_PHRASES = re.compile(
    r"(i\s+only\s+speak\s+english|"
    r"only\s+english|"
    r"speak\s+only\s+english|"
    r"don't\s+speak\s+arabic|"
    r"do\s+not\s+speak\s+arabic)",
    re.IGNORECASE,
)
_FRENCH_ACCENTS_RE = re.compile(r"[àâäéèêëïîôùûüçœæ]", re.IGNORECASE)


def is_system_context_body(body: str) -> bool:
    """True for injected vision/STT system notes stored on the customer turn."""
    raw = body or ""
    return bool(_SYSTEM_CONTEXT_BODY_RE.match(raw) or _LEGACY_VISION_BODY_RE.match(raw))


def looks_like_franco_darija(text: str) -> bool:
    """
    Latin letters with Moroccan Franco / Arabizi cues.
    These customers expect Arabic-script replies, not Latin Franco mirroring.
    """
    raw = (text or "").strip()
    if not raw or _ARABIC_SCRIPT_RE.search(raw):
        return False
    if not _LATIN_WORD_RE.search(raw):
        return False
    if _FRENCH_ONLY_PHRASES.search(raw) or _ENGLISH_ONLY_PHRASES.search(raw):
        return False
    return bool(_FRANCO_DARIJA_RE.search(raw))


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

    None means AUTO — detect from customer messages (see resolve_customer_language_for_turn).
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


def channel_language_is_auto(channel) -> bool:
    if not channel:
        return True
    vl = (getattr(channel, "voice_language", None) or "AUTO").strip().upper()
    return vl == "AUTO"


def _customer_message_bodies(conversation, max_messages: int = 4) -> list[str]:
    bodies: list[str] = []
    if not conversation:
        return bodies
    for msg in reversed(conversation):
        if msg.get("role") != "customer":
            continue
        body = (msg.get("body") or "").strip()
        if not body or body == "[media]":
            continue
        # Skip vision / payment classifier notes — they are English system context,
        # not the customer's spoken language.
        if is_system_context_body(body):
            continue
        bodies.append(body)
        if len(bodies) >= max_messages:
            break
    bodies.reverse()
    return bodies


def detect_customer_language(conversation) -> OutputLang:
    """
    Infer fr / en / ar from recent customer messages (weighted toward latest).
    Returns None when unclear — caller should fall back to phone/voice hierarchy.

    Notes:
    - System image/vision notes are ignored (must not flip the chat to English).
    - Latin Moroccan Franco (Wach / bghit / …) counts as Arabic intent → reply in Arabic script.
    """
    bodies = _customer_message_bodies(conversation, max_messages=4)
    if not bodies:
        return None

    french_score = 0.0
    english_score = 0.0
    arabic_score = 0.0

    weights = [1.0, 1.25, 1.5, 2.0]
    for idx, body in enumerate(bodies):
        w = weights[min(idx, len(weights) - 1)]
        lower = body.lower()

        if _FRENCH_ONLY_PHRASES.search(body):
            return "fr"
        if _ENGLISH_ONLY_PHRASES.search(body):
            return "en"

        # Franco Darija in Latin letters → Arabic output language (not EN/FR mirror).
        if looks_like_franco_darija(body):
            arabic_score += w * 3.0
            continue

        arabic_chars = len(_ARABIC_SCRIPT_RE.findall(body))
        latin_words = len(_LATIN_WORD_RE.findall(body))

        if arabic_chars >= 3 and arabic_chars >= latin_words:
            arabic_score += w * (1.0 + min(arabic_chars, 40) / 40.0)
            continue

        fr_hits = len(_FRENCH_HINTS.findall(lower))
        en_hits = len(_ENGLISH_HINTS.findall(lower))
        if _FRENCH_ACCENTS_RE.search(body):
            fr_hits += 3

        french_score += w * fr_hits
        english_score += w * en_hits

        if latin_words >= 2 and arabic_chars == 0:
            if fr_hits > en_hits:
                french_score += w * 0.5
            elif en_hits > fr_hits:
                english_score += w * 0.5

        if len(bodies) == 1 and arabic_chars == 0 and fr_hits >= 1 and en_hits == 0:
            french_score += 1.5
        if len(bodies) == 1 and arabic_chars == 0 and en_hits >= 1 and fr_hits == 0:
            english_score += 1.5

    if arabic_score >= max(french_score, english_score) and arabic_score >= 1.0:
        return "ar"
    if french_score >= english_score and french_score >= 2.0:
        return "fr"
    if english_score > french_score and english_score >= 2.0:
        return "en"
    if french_score >= 1.0 and english_score == 0 and arabic_score == 0:
        return "fr"
    if english_score >= 1.0 and french_score == 0 and arabic_score == 0:
        return "en"
    return None


def _market_to_dialect(market: str | None) -> str:
    m = (market or "").strip().upper()
    if m == "MA":
        return "Moroccan Darija"
    if m == "SA":
        return "Saudi Arabic"
    if m == "GCC":
        return "Gulf Arabic"
    return "Arabic (local conversational)"


def resolve_customer_language_for_turn(channel, node, conversation, customer_phone):
    """
    Resolve output language + dialect for one sales turn.

    Priority:
      1) Flow node language (fixed)
      2) Channel voice_language (fixed, not AUTO)
      3) AUTO: detect from customer messages
      4) None / fallback — caller keeps phone + voice hierarchy

    Returns:
      (output_language, target_dialect_override, market_override, source)
      target_dialect_override is set when AUTO detection locks fr/en/ar explicitly.
    """
    node_lang = effective_output_language_for_node(node)
    if node_lang is not None:
        return node_lang, None, None, "node"

    channel_lang = effective_bot_language(channel)
    if channel_lang is not None:
        return channel_lang, None, None, "channel"

    if not channel_language_is_auto(channel):
        return None, None, None, "default"

    detected = detect_customer_language(conversation)
    if detected == "fr":
        return "fr", "French", None, "auto_customer"
    if detected == "en":
        return "en", "English", None, "auto_customer"
    if detected == "ar":
        from ai_assistant.services import infer_market_from_conversation, infer_market_from_phone

        market = infer_market_from_conversation(conversation) or infer_market_from_phone(
            customer_phone or ""
        )
        return "ar", _market_to_dialect(market), market, "auto_customer"

    return None, None, None, "default"
