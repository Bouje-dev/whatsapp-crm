"""
Outbound WhatsApp message normalization (applied before API send).
"""

from __future__ import annotations

# Eastern Arabic-Indic + Persian digits → Western Arabic numerals
_EASTERN_TO_WESTERN = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def normalize_outbound_text(text: str) -> str:
    """Force Western digits and strip problematic Unicode digit variants."""
    if not text:
        return text or ""
    return str(text).translate(_EASTERN_TO_WESTERN)
