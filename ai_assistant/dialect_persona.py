"""
Dialect routing engine for clean prompt injection.
"""

from __future__ import annotations

from typing import Any


PHONE_PREFIX_TO_DIALECT = {
    "+966": "Saudi Arabic",
    "+212": "Moroccan Darija",
    "+971": "UAE Arabic",
}


def _normalize_node_language(node_language: str) -> str:
    return (node_language or "").strip().upper().replace("-", "_")


def _dialect_from_node_language(node_language: str) -> str | None:
    nl = _normalize_node_language(node_language)
    if not nl:
        return None
    if nl.startswith("AR_MA") or nl == "MA":
        return "Moroccan Darija"
    if nl.startswith("AR_SA") or nl == "SA":
        return "Saudi Arabic"
    if nl.startswith("AR_AE") or nl == "AE":
        return "UAE Arabic"
    if nl.startswith("AR_EG") or nl.startswith("EG_"):
        return "Egyptian Arabic"
    if nl.startswith("AR_GCC") or nl == "GCC":
        return "Gulf Arabic"
    return None


def _dialect_from_bot_settings(bot_settings: Any) -> str | None:
    if not bot_settings:
        return None
    if isinstance(bot_settings, dict):
        for key in ("target_dialect", "dialect", "voice_dialect", "bot_dialect"):
            value = bot_settings.get(key)
            if value and str(value).strip():
                return str(value).strip()
        value = bot_settings.get("voice_language")
    else:
        for key in ("target_dialect", "dialect", "voice_dialect", "bot_dialect"):
            value = getattr(bot_settings, key, None)
            if value and str(value).strip():
                return str(value).strip()
        value = getattr(bot_settings, "voice_language", None)
    if value and str(value).strip():
        code = _normalize_node_language(str(value))
        mapped = _dialect_from_node_language(code)
        if mapped:
            return mapped
    return None


def _dialect_from_phone_prefix(customer_phone: str) -> str:
    phone = (customer_phone or "").strip()
    for prefix, dialect in PHONE_PREFIX_TO_DIALECT.items():
        if phone.startswith(prefix):
            return dialect
    return "Arabic (local conversational)"


def determine_target_dialect(node, bot_settings, customer_phone):
    """
    Hierarchy:
    1) Node-level language/dialect
    2) Global bot settings
    3) Phone prefix fallback
    """
    if node:
        node_lang = getattr(node, "node_language", None)
        resolved = _dialect_from_node_language(node_lang or "")
        if resolved:
            return resolved

    from_global = _dialect_from_bot_settings(bot_settings)
    if from_global:
        return from_global

    return _dialect_from_phone_prefix(customer_phone or "")


def build_clean_language_rule(target_dialect: str) -> str:
    dialect = (target_dialect or "").strip() or "Arabic (local conversational)"
    return (
        "LANGUAGE RULE: You are a local sales assistant. Speak entirely in the native, natural dialect "
        f"of {dialect}. Do not use formal Standard Arabic (Fus'ha). Be conversational and brief."
    )
