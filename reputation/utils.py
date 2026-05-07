"""
Canonical phone key for GlobalCustomerProfile lookup.
Must be used in both signals (when updating) and Order.get_reputation_badge() (when reading).
"""


def normalize_phone_for_reputation(phone):
    """
    Return a canonical string key for the same customer across stores.
    Uses the same normalizer as marketing/capture when available, else digits-only fallback.
    """
    if not phone:
        return ""
    raw = str(phone).strip()
    if not raw:
        return ""

    try:
        from discount.marketing.utils import normalize_phone

        normalized = normalize_phone(raw, "SA")
        if normalized:
            return normalized
    except Exception:
        pass

    digits = "".join(c for c in raw if c.isdigit())
    if not digits:
        return raw
    if len(digits) >= 9 and not digits.startswith("966") and not digits.startswith("965"):
        return "966" + digits[-9:] if len(digits) == 9 else digits
    return digits or raw
