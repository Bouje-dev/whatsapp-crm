"""
WhatsApp checkout state — durable slot memory for the AI sales agent.

Stops context amnesia during checkout by:
  1. Persisting extracted fields on ``WhatsAppCheckoutState``
  2. Extracting entities from the newest user message (LLM JSON)
  3. Fuzzy-matching imperfect product queries to catalog IDs
  4. Injecting a strict prompt that only asks for missing slots
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)

_FIELD_LABELS = {
    "customer_name": "Name",
    "phone_number": "Phone number",
    "shipping_city": "City",
    "shipping_address": "Address",
    "email_address": "Email",
}

_EXTRACT_SYSTEM = (
    "You extract checkout slots AND customer profile context from ONE customer WhatsApp message "
    "(Darija / Arabic / French / English / Franco-Arab).\n"
    "Return ONLY JSON with keys:\n"
    "  customer_name, city, address, email_address, product_query, phone_number,\n"
    "  customer_context, confidence\n"
    "Use null when a key is not clearly present. confidence maps each key to 0.0–1.0.\n"
    "\n"
    "Intent rules (follow meaning, not keywords):\n"
    "- Extract the DELIVERY city for THIS order — not every place mentioned.\n"
    "  «أنا كاين دابا في سلا، غدا غادي نمشي طنجة» → city=طنجة "
    "(tomorrow / delivery destination), NOT سلا (current location).\n"
    "  «أنا كاين دابا في الجديدة، غدا غادي نمشي الدار البيضاء» → city=الدار البيضاء.\n"
    "- Bare agreement (اه / نعم / واخا / ok / yes / oui / تمام…) → all keys null.\n"
    "- Asking for / naming a product to buy → product_query only "
    "(never put that sentence in customer_name, city, or address).\n"
    "- Giving a personal name → customer_name only.\n"
    "- Giving a street/neighborhood/building → address (and city only if clearly the delivery city).\n"
    "- Do not invent values. Prefer null over guessing.\n"
    "- product_query: keep the customer's wording for catalog matching.\n"
    "- Normalize obvious typos in names when confidence is high; otherwise keep raw text.\n"
    "\n"
    "customer_context (sales profile — NOT a checkout slot):\n"
    "- Capture any lasting personal fact useful for closing: skin/health conditions, "
    "pain points, objections, skepticism, rural/hard-to-reach location, prior bad "
    "experiences with similar products, budget sensitivity, gift occasion, urgency, "
    "family/use-case details, specific ingredient concerns.\n"
    "- Return a short English or Arabic bullet string (1–3 facts max for THIS message only).\n"
    "- If already_known.customer_notes already contains the same fact, return null "
    "(do not repeat).\n"
    "- Never put checkout slots (name/city/address/email/phone) into customer_context.\n"
    "- If the message has no profile insight, return null."
)

_CUSTOMER_NOTES_MAX_CHARS = 4000


def merge_customer_notes(existing: str, new_note: str) -> str:
    """
    Append new profile facts to accumulated notes without duplicating.
    Stores newline bullet lines; caps total length.
    """
    existing = (existing or "").strip()
    new_note = (new_note or "").strip()
    if not new_note:
        return existing

    pieces: list[str] = []
    for part in re.split(r"[\n;|]+", new_note):
        line = part.strip(" \t-•*")
        if not line or line.lower() in ("null", "none", "n/a", "-"):
            continue
        pieces.append(line[:300])
    if not pieces:
        return existing

    existing_lower = existing.lower()
    added: list[str] = []
    for p in pieces:
        if p.lower() in existing_lower:
            continue
        added.append(p)
        existing_lower += "\n" + p.lower()
    if not added:
        return existing

    block = "\n".join(f"- {p}" for p in added)
    merged = f"{existing.rstrip()}\n{block}" if existing else block
    if len(merged) <= _CUSTOMER_NOTES_MAX_CHARS:
        return merged
    # Keep the most recent facts when over cap
    trimmed = merged[-_CUSTOMER_NOTES_MAX_CHARS:]
    nl = trimmed.find("\n")
    if nl >= 0:
        trimmed = trimmed[nl + 1 :]
    return trimmed


def build_customer_profile_notes_prompt(notes: str) -> str:
    """System-prompt block: customer profile context for empathy / closing."""
    text = (notes or "").strip()
    if not text:
        return ""
    return (
        "### Customer Profile & Notes:\n"
        f"{text}\n\n"
        "BEHAVIORAL RULE (STRICT): Use the 'Customer Profile & Notes' to show empathy, "
        "address objections proactively, and personalize your sales pitch "
        "(e.g., if they have sensitive skin, reassure them about the natural ingredients). "
        "Do not explicitly mention that you saved this information — just use it naturally "
        "in conversation."
    )


# Cheap short-circuit only: whole-message agreement → skip the extract LLM call.
_CONFIRMATION_TOKENS = frozenset({
    "اه", "آه", "اها", "ايه", "أيوه", "ايوه", "أيوا", "ايوا", "إييه",
    "نعم", "أجل", "اجل", "بلى", "بله",
    "واخا", "وخا", "واخاا", "واخة",
    "ok", "okay", "k", "kk", "oki", "okey",
    "oui", "ouais", "yes", "yep", "yeah", "yup", "sure", "yea",
    "صح", "صحيح", "تمام", "حاضر",
    "أوكي", "اوكي", "اوك", "وكي",
    "موافق", "متافق", "متفق", "صافي",
})


def get_or_create_checkout_state(channel, customer_phone: str):
    """Return the durable checkout row for (channel, phone)."""
    from discount.models import WhatsAppCheckoutState

    if not channel or not customer_phone:
        return None
    phone = str(customer_phone).strip()
    if not phone:
        return None
    state, _ = WhatsAppCheckoutState.objects.get_or_create(
        channel=channel,
        customer_phone=phone,
    )
    return state


def reset_checkout_state(channel, customer_phone: str) -> None:
    """Clear slots after order complete / hard reset / product pivot."""
    from discount.models import WhatsAppCheckoutState

    if not channel or not customer_phone:
        return
    WhatsAppCheckoutState.objects.filter(
        channel=channel,
        customer_phone=str(customer_phone).strip(),
    ).update(
        customer_name="",
        city="",
        address="",
        email_address="",
        product=None,
        is_ready_for_checkout=False,
        raw_extractions={},
        is_waiting_for_answer=False,
        pending_knowledge_question="",
        pending_knowledge_answer="",
        # CTWA ad attribution is preserved so a completed/reset checkout
        # still counts as an attributed chat and later orders inherit it
        # until a new referral overwrites the fields.
    )


def clear_customer_slots_keep_product(channel, customer_phone: str) -> None:
    """On product pivot: drop name/city/address but keep nothing product-bound."""
    reset_checkout_state(channel, customer_phone)


def _nonempty(value) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return text


def _normalize_confirm_token(text: str) -> str:
    t = (text or "").strip().lower()
    t = re.sub(r"[!?.،,؛:…]+", "", t).strip()
    t = re.sub(r"\s+", " ", t)
    return t


def _is_confirmation_only(text: str) -> bool:
    """True when the whole message is just agreement (اه / ok / نعم…), not data."""
    t = _normalize_confirm_token(text)
    return bool(t) and t in _CONFIRMATION_TOKENS


def _is_placeholder(value: str) -> bool:
    try:
        from discount.orders_ai import is_placeholder_order_field

        return is_placeholder_order_field(value)
    except Exception:
        return not (value or "").strip()


def _reject_bad_slot_value(field: str, value: str, *, message: str = "") -> bool:
    """Return True when ``value`` must NOT be written into the given checkout slot."""
    val = _nonempty(value)
    if not val or _is_placeholder(val):
        return True
    # Never persist a bare confirmation as any slot
    if _is_confirmation_only(val):
        return True
    if field == "customer_name" and (len(val) > 60 or len(val.split()) > 6):
        return True
    return False


def refresh_ready_flag(state, product=None) -> bool:
    """Set ``is_ready_for_checkout`` from product required fields + filled slots."""
    if not state:
        return False
    product = product or getattr(state, "product", None)
    if not product:
        state.is_ready_for_checkout = False
        return False

    from discount.orders_ai import get_required_order_fields_for_product

    required = get_required_order_fields_for_product(product) or []
    collected = state_to_collected_fields(state)
    phone = (getattr(state, "customer_phone", None) or "").strip()
    ready = True
    for field in required:
        if field == "phone_number":
            val = collected.get("phone_number") or phone
        else:
            val = collected.get(field) or ""
        if _is_placeholder(val):
            ready = False
            break
    # Instant-submit products still need a resolved product id
    if not required:
        ready = True
    state.is_ready_for_checkout = bool(ready and product)
    return state.is_ready_for_checkout


def state_to_collected_fields(state) -> dict[str, str]:
    if not state:
        return {}
    out = {}
    name = _nonempty(getattr(state, "customer_name", None))
    city = _nonempty(getattr(state, "city", None))
    address = _nonempty(getattr(state, "address", None))
    email = _nonempty(getattr(state, "email_address", None))
    phone = _nonempty(getattr(state, "customer_phone", None))
    if name and not _is_confirmation_only(name) and len(name) <= 60:
        out["customer_name"] = name
    if city and not _is_confirmation_only(city):
        out["shipping_city"] = city
    if address and not _is_confirmation_only(address):
        out["shipping_address"] = address
    if email:
        out["email_address"] = email
    if phone:
        out["phone_number"] = phone
    return out


def apply_entities_to_state(
    state,
    entities: dict,
    *,
    channel=None,
    product=None,
    overwrite: bool = False,
    source_message: str = "",
):
    """
    Merge extracted entities into ``state``. Never clears an already-filled slot
    unless ``overwrite`` is True. Resolves ``product_query`` via fuzzy lookup.
    """
    if not state or not isinstance(entities, dict):
        return state

    channel = channel or getattr(state, "channel", None)
    msg = (source_message or "").strip()

    # Pure confirmation turn → do not touch any slots
    if msg and _is_confirmation_only(msg):
        state.raw_extractions = {
            "entities": entities,
            "product_query": None,
            "resolved_product_id": getattr(state, "product_id", None),
            "skipped": "confirmation_only",
        }
        state.save(update_fields=["raw_extractions", "updated_at"])
        return state

    mapping = (
        ("customer_name", "customer_name"),
        ("city", "city"),
        ("address", "address"),
        ("email_address", "email_address"),
    )
    changed = False
    for entity_key, field_name in mapping:
        val = _nonempty(entities.get(entity_key))
        if not val or _is_placeholder(val):
            continue
        if _reject_bad_slot_value(field_name, val, message=msg):
            continue
        current = _nonempty(getattr(state, field_name, None))
        if current and not overwrite:
            continue
        if val != current:
            setattr(state, field_name, val[:500] if field_name == "address" else val[:200])
            changed = True

    # Profile notes — append new context; survive product pivots (not checkout slots).
    context_raw = entities.get("customer_context")
    if context_raw is None:
        context_raw = entities.get("customer_notes")
    if isinstance(context_raw, list):
        context_raw = "\n".join(str(x).strip() for x in context_raw if str(x).strip())
    context_val = _nonempty(context_raw)
    if context_val and not _is_placeholder(context_val):
        merged_notes = merge_customer_notes(
            getattr(state, "customer_notes", "") or "",
            context_val,
        )
        if merged_notes != _nonempty(getattr(state, "customer_notes", None)):
            state.customer_notes = merged_notes
            changed = True

    # Product resolution — trust LLM product_query (or explicit product arg)
    resolved = product
    product_query = _nonempty(entities.get("product_query"))
    if product_query and channel is not None:
        hit = fuzzy_lookup_product(product_query, channel=channel)
        if hit is not None:
            resolved = hit
    if resolved is not None and getattr(state, "product_id", None) != getattr(resolved, "id", None):
        prev_pid = getattr(state, "product_id", None)
        state.product = resolved
        changed = True
        # New catalog product from a product_query → drop leftover shipping slots
        # from a previous chat on the same phone (Lab / returning customer).
        # Keep customer_notes — profile context still applies across products.
        if product_query:
            state.customer_name = ""
            state.city = ""
            state.address = ""
            state.email_address = ""
        logger.info(
            "checkout product bound id=%s (was %s) via query=%r",
            getattr(resolved, "id", None),
            prev_pid,
            (product_query or "")[:80],
        )

    state.raw_extractions = {
        "entities": entities,
        "product_query": product_query or None,
        "resolved_product_id": getattr(state, "product_id", None),
    }
    refresh_ready_flag(state, product=getattr(state, "product", None))
    state.save(
        update_fields=[
            "customer_name",
            "city",
            "address",
            "email_address",
            "customer_notes",
            "product",
            "is_ready_for_checkout",
            "raw_extractions",
            "updated_at",
        ]
    )
    return state


def extract_checkout_entities(
    message: str,
    *,
    known_state=None,
    required_fields: Optional[list] = None,
    catalog_hint: str = "",
    use_llm: bool = True,
) -> dict[str, Any]:
    """
    LLM-first extraction of checkout slots from the newest user message.
    Heuristic is only a fallback when the LLM call fails / is disabled.
    """
    text = (message or "").strip()
    if not text:
        return {}

    empty = {
        "customer_name": None,
        "city": None,
        "address": None,
        "email_address": None,
        "product_query": None,
        "phone_number": None,
        "customer_context": None,
        "confidence": {},
    }

    # Skip extract LLM on pure اه/ok — saves tokens, no data to write.
    if _is_confirmation_only(text):
        return empty

    known = {}
    if known_state is not None:
        known = {
            "customer_name": _nonempty(getattr(known_state, "customer_name", None)) or None,
            "city": _nonempty(getattr(known_state, "city", None)) or None,
            "address": _nonempty(getattr(known_state, "address", None)) or None,
            "email_address": _nonempty(getattr(known_state, "email_address", None)) or None,
            "product_id": getattr(known_state, "product_id", None),
            "customer_notes": _nonempty(getattr(known_state, "customer_notes", None)) or None,
        }

    if not use_llm:
        return _heuristic_extract_entities(text, known=known)

    llm_result = _llm_extract_entities(
        text,
        known=known,
        required_fields=required_fields or [],
        catalog_hint=catalog_hint or "",
    )
    if llm_result:
        # Drop accidental confirmation tokens if the model still emits them
        for slot_key in ("customer_name", "city", "address"):
            slot_val = llm_result.get(slot_key)
            if slot_val and _reject_bad_slot_value(slot_key, str(slot_val), message=text):
                llm_result[slot_key] = None
        return llm_result

    return _heuristic_extract_entities(text, known=known)

def _llm_extract_entities(
    text: str,
    *,
    known: dict,
    required_fields: list,
    catalog_hint: str,
) -> dict[str, Any]:
    try:
        import litellm
        from ai_assistant.services import (
            DEFAULT_MODEL,
            _normalize_litellm_model_name,
            _prepare_litellm_provider_key,
        )
    except Exception as exc:
        logger.debug("checkout extract: litellm unavailable: %s", exc)
        return {}

    user_payload = {
        "newest_message": text,
        "already_known": known,
        "required_fields": list(required_fields or []),
        "catalog_hint": (catalog_hint or "")[:800],
    }
    model = _normalize_litellm_model_name(DEFAULT_MODEL)
    try:
        _prepare_litellm_provider_key(model)
        response = litellm.completion(
            model=model,
            messages=[
                {"role": "system", "content": _EXTRACT_SYSTEM},
                {
                    "role": "user",
                    "content": json.dumps(user_payload, ensure_ascii=False),
                },
            ],
            max_tokens=500,
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        content = ""
        if getattr(response, "choices", None):
            msg = response.choices[0].message
            content = (getattr(msg, "content", "") or "").strip()
        if not content:
            return {}
        data = json.loads(content)
        if not isinstance(data, dict):
            return {}
        return _normalize_entity_dict(data)
    except Exception as exc:
        logger.warning("checkout entity LLM extract failed: %s", exc)
        return {}


def _normalize_entity_dict(data: dict) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in (
        "customer_name",
        "city",
        "address",
        "email_address",
        "product_query",
        "phone_number",
    ):
        val = data.get(key)
        if val is None:
            out[key] = None
            continue
        s = str(val).strip()
        out[key] = s if s and s.lower() not in ("null", "none", "n/a") else None

    # customer_context may be a string or list of short facts
    ctx = data.get("customer_context")
    if ctx is None:
        ctx = data.get("customer_notes")
    if isinstance(ctx, list):
        parts = [str(x).strip() for x in ctx if str(x).strip()]
        out["customer_context"] = "\n".join(parts) if parts else None
    elif ctx is None:
        out["customer_context"] = None
    else:
        s = str(ctx).strip()
        out["customer_context"] = s if s and s.lower() not in ("null", "none", "n/a") else None

    conf = data.get("confidence")
    out["confidence"] = conf if isinstance(conf, dict) else {}
    return out


_EMAIL_RE = re.compile(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", re.I)
_NAME_EXPLICIT_RE = re.compile(
    r"(?:اسمي|سمّيتي|سميت|ana|je m['’]appelle|my name is)\s+([^\n,.]{2,40})",
    re.I,
)


def _heuristic_extract_entities(text: str, *, known: dict) -> dict[str, Any]:
    """
    Minimal offline fallback when the extract LLM is unavailable.
    Does NOT guess cities, addresses, or product intent from keyword lists —
    those decisions belong to the LLM.
    """
    out: dict[str, Any] = {
        "customer_name": None,
        "city": None,
        "address": None,
        "email_address": None,
        "product_query": None,
        "phone_number": None,
        "customer_context": None,
        "confidence": {},
    }
    raw = (text or "").strip()
    if not raw or _is_confirmation_only(raw):
        return out

    email_m = _EMAIL_RE.search(raw)
    if email_m:
        out["email_address"] = email_m.group(0)
        out["confidence"]["email_address"] = 0.9

    if not known.get("customer_name"):
        m = _NAME_EXPLICIT_RE.search(raw)
        if m:
            name = m.group(1).strip()
            if name and not _is_confirmation_only(name):
                out["customer_name"] = name[:200]
                out["confidence"]["customer_name"] = 0.55

    return out


def fuzzy_lookup_product(user_query: str, *, channel=None, owner=None, queryset=None):
    """
    Robust catalog match for imperfect inputs (typos, Darija variants, partial names).

    Pipeline (delegates to product_search): exact/alias → fuzzy difflib → embeddings.
    """
    from discount.services.product_search import find_matching_product

    return find_matching_product(
        user_query,
        owner=owner,
        channel=channel,
        queryset=queryset,
    )


def build_checkout_state_prompt(
    state,
    *,
    required_fields: Optional[list] = None,
    product_name: str = "",
    customer_phone: str = "",
) -> str:
    """
    Strict system-prompt block: only ask for missing fields; never re-ask collected ones.
    Without a locked product, forbids order registration entirely.
    """
    if not state and not required_fields and not product_name:
        return ""

    collected = state_to_collected_fields(state) if state else {}
    phone = (customer_phone or collected.get("phone_number") or "").strip()
    product = getattr(state, "product", None) if state else None
    pname = (product_name or "").strip()
    if not pname and product is not None:
        pname = (getattr(product, "name", None) or "").strip()
    pid = None
    if product is not None:
        pid = getattr(product, "id", None)
    elif state is not None:
        pid = getattr(state, "product_id", None)

    # ── Hard gate: no product → no checkout talk ─────────────────────────────
    if not pid:
        return (
            "╔══════════════════════════════════════════════════╗\n"
            "║  [NO ACTIVE PRODUCT — CHECKOUT LOCKED]           ║\n"
            "╚══════════════════════════════════════════════════╝\n"
            "Session has NO locked product. Absolute rules:\n"
            "1. FORBIDDEN: ask for / confirm name, city, address, or phone for an order.\n"
            "2. FORBIDDEN: say you will register the order, list «معلوماتك كاملة», or call "
            "submit_customer_order / send_whatsapp_flow.\n"
            "3. REQUIRED: call search_products for what they want (or empty query to show "
            "categories / available items). When a match is found the backend locks "
            "active_product — only THEN may you collect checkout fields.\n"
            "4. If search returns nothing: apologize briefly, suggest similar products or "
            "categories from the tool result — never invent a product, never start checkout.\n"
            "══════════════════════════════════════════════════"
        )

    fields: list[str]
    if required_fields is not None:
        fields = list(required_fields)
    elif product is not None:
        try:
            from discount.orders_ai import get_required_order_fields_for_product

            fields = list(get_required_order_fields_for_product(product) or [])
        except Exception:
            fields = ["customer_name", "phone_number", "shipping_city", "shipping_address"]
    else:
        fields = ["customer_name", "phone_number", "shipping_city", "shipping_address"]

    known_lines = []
    if phone:
        known_lines.append(f"• Phone: {phone} ✅ ALREADY KNOWN — NEVER ASK")
    known_lines.append(
        f"• Product: {pname or '(selected)'} [DB_PRODUCT_ID: {pid}] ✅ LOCKED — NEVER ASK WHICH PRODUCT"
    )

    slot_map = [
        ("customer_name", "Name"),
        ("shipping_city", "City"),
        ("shipping_address", "Address"),
        ("email_address", "Email"),
    ]
    for tool_key, label in slot_map:
        if tool_key not in fields:
            continue
        val = collected.get(tool_key) or ""
        if val and not _is_placeholder(val):
            known_lines.append(f"• {label}: {val} ✅ ALREADY COLLECTED — NEVER ASK AGAIN")

    missing_ordered: list[str] = []
    for key in fields:
        if key == "phone_number":
            if phone:
                continue
            missing_ordered.append(key)
            continue
        val = collected.get(key) or ""
        if not val or _is_placeholder(val):
            missing_ordered.append(key)

    # Instant-submit: no customer slots, but product still required
    if not fields and not pid:
        missing_ordered = []

    missing_labels = [_FIELD_LABELS.get(k, k.replace("_", " ").title()) for k in missing_ordered]
    ready = bool(getattr(state, "is_ready_for_checkout", False)) if state else False
    locked_city = (collected.get("shipping_city") or "").strip()

    lines = [
        "╔══════════════════════════════════════════════════╗",
        "║   [CHECKOUT STATE MEMORY — HIGHEST PRIORITY]     ║",
        "╚══════════════════════════════════════════════════╝",
        "This block is the SOURCE OF TRUTH for checkout slots.",
        "Ignore chat-history guesses that contradict it.",
        "",
        "ALREADY COLLECTED (do NOT re-ask, do NOT confirm repeatedly):",
    ]
    if known_lines:
        lines.extend(known_lines)
    else:
        lines.append("• (nothing collected yet)")

    if locked_city:
        lines.append("")
        lines.append(
            f"DELIVERY CITY LOCKED = «{locked_city}». "
            "Do NOT ask «سلا ولا طنجة» / current city vs tomorrow city. "
            "Use this single city for the order."
        )

    lines.append("")
    if missing_ordered:
        lines.append(
            "MISSING — ask ONLY for these, preferably in one short message: "
            + ", ".join(missing_labels)
        )
        lines.append("FORBIDDEN: asking for any field listed under ALREADY COLLECTED.")
    else:
        lines.append("MISSING: none. All required slots are filled.")
        if ready or (pid and not missing_ordered):
            lines.append(
                "NEXT ACTION: call submit_customer_order NOW with the known values "
                f"(product_id={pid}, phone_number={phone or 'WhatsApp number'}). "
                "Do not stall with extra questions."
            )

    lines.append("")
    lines.append(
        "PHRASING (customer-facing): No Robotic Phrasing — NEVER use literal translations "
        "or bracketed explanations (e.g. do not say \"First or Full Name\" or "
        "\"(الكامل ولا الأول)\"). Ask simply in the matching dialect "
        "(e.g. \"شنو سميتك؟\", \"What is your name?\"). Slot labels above are internal only."
    )
    lines.append(
        "When calling submit_customer_order, ALWAYS pass the ALREADY COLLECTED "
        "values exactly as shown above — never invent placeholders."
    )
    lines.append("══════════════════════════════════════════════════")
    return "\n".join(lines)


def sync_checkout_state_to_session(channel, customer_phone: str, state) -> dict:
    """Mirror durable state into ChatSession.context_data['collected_order_fields']."""
    if not channel or not customer_phone or not state:
        return {}
    collected = state_to_collected_fields(state)
    try:
        from discount.whatssapAPI.session_state import (
            CTX_COLLECTED_ORDER_FIELDS,
            update_session_context_data,
            set_session_active_product,
        )

        update_session_context_data(
            channel,
            customer_phone,
            {CTX_COLLECTED_ORDER_FIELDS: collected},
        )
        product = getattr(state, "product", None)
        if product is not None:
            set_session_active_product(
                channel,
                customer_phone,
                product,
                reason="checkout_state_sync",
            )
    except Exception as exc:
        logger.debug("sync_checkout_state_to_session: %s", exc)
    return collected


def merge_state_into_submit_args(arguments: dict, state, customer_phone: str = "") -> dict:
    """Fill missing submit_customer_order args from durable checkout state."""
    args = dict(arguments or {}) if isinstance(arguments, dict) else {}
    if not state:
        return args
    collected = state_to_collected_fields(state)
    fills = {
        "customer_name": collected.get("customer_name"),
        "shipping_city": collected.get("shipping_city"),
        "shipping_address": collected.get("shipping_address"),
        "email_address": collected.get("email_address"),
        "phone_number": collected.get("phone_number") or customer_phone,
    }
    for key, val in fills.items():
        cur = args.get(key)
        if (cur is None or _is_placeholder(str(cur))) and val and not _is_placeholder(val):
            args[key] = val
    if (args.get("product_id") is None or _is_placeholder(str(args.get("product_id")))):
        pid = getattr(state, "product_id", None)
        if pid:
            args["product_id"] = int(pid)
    return args


def process_incoming_checkout_message(
    channel,
    customer_phone: str,
    message: str,
    *,
    session=None,
    product=None,
    required_fields: Optional[list] = None,
) -> Any:
    """
    Main entry: extract entities from newest message → update WhatsAppCheckoutState
    → sync into session context. Returns the updated state (or None).
    """
    if not channel or not customer_phone:
        return None

    state = get_or_create_checkout_state(channel, customer_phone)
    if state is None:
        return None

    # Seed product from session / active product when empty
    if product is None and session is not None:
        product = getattr(session, "active_product", None)
    if product is not None and getattr(state, "product_id", None) is None:
        state.product = product
        state.save(update_fields=["product", "updated_at"])

    fields = list(required_fields) if required_fields is not None else None
    if fields is None and (product or getattr(state, "product", None)):
        try:
            from discount.orders_ai import get_required_order_fields_for_product

            fields = get_required_order_fields_for_product(product or state.product) or []
        except Exception:
            fields = None

    catalog_hint = ""
    try:
        from discount.services.product_scope import channel_catalog_queryset

        names = list(
            channel_catalog_queryset(channel).order_by("name").values_list("name", flat=True)[:40]
        )
        catalog_hint = ", ".join(n for n in names if n)
    except Exception:
        catalog_hint = ""

    entities = extract_checkout_entities(
        message,
        known_state=state,
        required_fields=fields or [],
        catalog_hint=catalog_hint,
    )
    apply_entities_to_state(
        state,
        entities,
        channel=channel,
        product=product,
        source_message=message or "",
    )
    # After a real product bind, also sync ChatSession.active_product
    if getattr(state, "product", None) is not None and channel and customer_phone:
        try:
            from discount.whatssapAPI.session_state import set_session_active_product

            set_session_active_product(
                channel,
                customer_phone,
                state.product,
                reason="checkout_state_sync",
            )
        except Exception as _bind_err:
            logger.debug("checkout bind active_product: %s", _bind_err)
    sync_checkout_state_to_session(channel, customer_phone, state)
    return state
