"""Native WhatsApp Flows: build JSON, sync with Meta, and ingest form replies."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from decimal import Decimal, InvalidOperation

import requests
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

FLOW_JSON_VERSION = "6.0"
SCREEN_ID = "FORM"
MAX_FIELDS = 8
FLOW_PENDING_PREFIX = "wa_flow_pending:"
FLOW_TOKEN_PREFIX = "wa_flow_token:"
FLOW_PENDING_TTL = 7200

PURPOSE_LEAD = "lead_generation"
PURPOSE_FEEDBACK = "feedback"
PURPOSE_ORDER = "collect_order"

PURPOSE_CATEGORY = {
    PURPOSE_LEAD: "LEAD_GENERATION",
    PURPOSE_FEEDBACK: "SURVEY",
    PURPOSE_ORDER: "SHOPPING",
}

DEFAULT_FIELDS = {
    PURPOSE_LEAD: [
        {"key": "full_name", "label": "Full name", "field_type": "text", "required": True, "maps_to": "name", "options": ""},
        {"key": "phone", "label": "Phone", "field_type": "phone", "required": True, "maps_to": "phone", "options": ""},
        {"key": "email", "label": "Email", "field_type": "email", "required": False, "maps_to": "email", "options": ""},
    ],
    PURPOSE_FEEDBACK: [
        {"key": "rating", "label": "How was your experience?", "field_type": "rating", "required": True, "maps_to": "rating", "options": ""},
        {"key": "comment", "label": "Your feedback", "field_type": "textarea", "required": True, "maps_to": "notes", "options": ""},
    ],
    PURPOSE_ORDER: [
        {"key": "full_name", "label": "Full name", "field_type": "text", "required": True, "maps_to": "name", "options": ""},
        {"key": "city", "label": "City", "field_type": "text", "required": True, "maps_to": "city", "options": ""},
    ],
}


def parse_flow_node_content(raw_or_dict):
    content = {}
    if isinstance(raw_or_dict, dict):
        content = dict(raw_or_dict)
    elif isinstance(raw_or_dict, str):
        raw = raw_or_dict.strip()
        if raw.startswith("{"):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    content = parsed
            except Exception:
                content = {}
    purpose = (content.get("purpose") or PURPOSE_LEAD).strip()
    if purpose not in PURPOSE_CATEGORY:
        purpose = PURPOSE_LEAD
    fields = _normalize_fields(content.get("fields"), purpose)
    delay = 0
    try:
        delay = int(content.get("delay") or 0) or 0
    except Exception:
        delay = 0
    product_id = content.get("product_id")
    try:
        product_id = int(product_id) if product_id not in (None, "", "null") else None
    except Exception:
        product_id = None
    return {
        "purpose": purpose,
        "text": str(content.get("text") or content.get("body") or "").strip()[:1024],
        "header_text": str(content.get("header_text") or "").strip()[:60],
        "footer_text": str(content.get("footer_text") or "").strip()[:60],
        "cta_label": (str(content.get("cta_label") or "Open form").strip() or "Open form")[:20],
        "screen_title": (str(content.get("screen_title") or "Your details").strip() or "Your details")[:80],
        "submit_label": (str(content.get("submit_label") or "Submit").strip() or "Submit")[:20],
        "helper_text": str(content.get("helper_text") or "").strip()[:80],
        "fields": fields,
        "product_id": product_id,
        "product_name": str(content.get("product_name") or "").strip(),
        "delay": delay,
        "meta_flow_id": str(content.get("meta_flow_id") or "").strip(),
        "meta_flow_json_hash": str(content.get("meta_flow_json_hash") or "").strip(),
    }


def _normalize_fields(raw_fields, purpose):
    if not isinstance(raw_fields, list) or not raw_fields:
        raw_fields = DEFAULT_FIELDS.get(purpose) or DEFAULT_FIELDS[PURPOSE_LEAD]
    used = set()
    out = []
    for i, item in enumerate(raw_fields[:MAX_FIELDS], start=1):
        if isinstance(item, str):
            item = {"label": item}
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or f"Field {i}").strip()[:80] or f"Field {i}"
        key = _safe_field_key(item.get("key") or label, i, used)
        field_type = str(item.get("field_type") or item.get("type") or "text").strip().lower()
        if field_type not in ("text", "textarea", "phone", "email", "number", "date", "dropdown", "rating"):
            field_type = "text"
        options = item.get("options") or ""
        if isinstance(options, list):
            options = "\n".join(str(x).strip() for x in options if str(x).strip())
        else:
            options = str(options)
        maps_to = str(item.get("maps_to") or "custom").strip() or "custom"
        out.append({
            "key": key,
            "label": label,
            "field_type": field_type,
            "required": bool(item.get("required", True)),
            "maps_to": maps_to,
            "options": options,
        })
    return out or list(DEFAULT_FIELDS[PURPOSE_LEAD])


def _safe_field_key(raw, index, used):
    slug = re.sub(r"[^a-zA-Z0-9_]", "", str(raw or "").strip().replace(" ", "_"))
    if not slug or not slug[0].isalpha():
        slug = f"field_{index}"
    slug = slug[:28]
    name = slug
    n = 2
    while name.lower() in used or name in ("form", "screen", "data"):
        name = f"{slug}_{n}"[:32]
        n += 1
    used.add(name.lower())
    return name


def build_flow_json(content):
    parsed = parse_flow_node_content(content if isinstance(content, dict) else {})
    children = []
    helper = parsed["helper_text"]
    if parsed["purpose"] == PURPOSE_ORDER and parsed.get("product_name"):
        helper = helper or f"Product: {parsed['product_name']}"[:80]
    if helper:
        children.append({"type": "TextBody", "text": helper})
    form_children = []
    payload = {}
    for field in parsed["fields"]:
        component, payload_ref = _field_to_component(field)
        if not component:
            continue
        form_children.append(component)
        payload[field["key"]] = payload_ref
    form_children.append({
        "type": "Footer",
        "label": parsed["submit_label"],
        "on-click-action": {
            "name": "complete",
            "payload": payload,
        },
    })
    children.append({
        "type": "Form",
        "name": "form",
        "children": form_children,
    })
    return {
        "version": FLOW_JSON_VERSION,
        "screens": [
            {
                "id": SCREEN_ID,
                "title": parsed["screen_title"][:30] or "Form",
                "terminal": True,
                "success": True,
                "data": {},
                "layout": {
                    "type": "SingleColumnLayout",
                    "children": children,
                },
            }
        ],
    }


def _field_to_component(field):
    key = field["key"]
    label = field["label"]
    required = bool(field.get("required"))
    ftype = field.get("field_type") or "text"
    ref = f"${{form.{key}}}"
    if ftype == "textarea":
        return {
            "type": "TextArea",
            "name": key,
            "label": label,
            "required": required,
        }, ref
    if ftype == "date":
        return {
            "type": "DatePicker",
            "name": key,
            "label": label,
            "required": required,
        }, ref
    if ftype == "dropdown":
        source = _options_source(field.get("options") or "")
        if not source:
            source = [{"id": "option_1", "title": "Option 1"}]
        return {
            "type": "Dropdown",
            "name": key,
            "label": label,
            "required": required,
            "data-source": source,
        }, ref
    if ftype == "rating":
        return {
            "type": "RadioButtonsGroup",
            "name": key,
            "label": label,
            "required": required,
            "data-source": [
                {"id": "5", "title": "★★★★★ Excellent"},
                {"id": "4", "title": "★★★★ Good"},
                {"id": "3", "title": "★★★ OK"},
                {"id": "2", "title": "★★ Poor"},
                {"id": "1", "title": "★ Very poor"},
            ],
        }, ref
    input_type = {
        "phone": "phone",
        "email": "email",
        "number": "number",
        "text": "text",
    }.get(ftype, "text")
    return {
        "type": "TextInput",
        "name": key,
        "label": label,
        "required": required,
        "input-type": input_type,
    }, ref


def _options_source(raw):
    lines = [ln.strip() for ln in str(raw or "").splitlines() if ln.strip()]
    out = []
    used = set()
    for i, line in enumerate(lines[:20], start=1):
        key = _safe_field_key(line, i, used)
        out.append({"id": key[:80], "title": line[:30]})
    return out


def flow_json_hash(flow_json):
    blob = json.dumps(flow_json, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:40]


def _graph_base(channel):
    version = (getattr(channel, "api_version", None) or "v22.0").strip() or "v22.0"
    if not version.startswith("v"):
        version = "v" + version
    return f"https://graph.facebook.com/{version}"


def _find_flow_id_by_name(channel, headers, waba_id, name):
    try:
        res = requests.get(
            f"{_graph_base(channel)}/{waba_id}/flows",
            headers=headers,
            params={"limit": 50},
            timeout=20,
        )
        for item in (res.json() or {}).get("data") or []:
            if str(item.get("name") or "") == name and item.get("id"):
                return str(item["id"])
    except Exception as exc:
        logger.warning("list WhatsApp Flows failed: %s", exc)
    return ""


def ensure_meta_flow_id(channel, parsed, *, name_suffix, existing_id="", existing_hash=""):
    """Create or update a published WhatsApp Flow. Returns (flow_id, json_hash, error)."""
    flow_json = build_flow_json(parsed)
    json_hash = flow_json_hash(flow_json)
    token = (getattr(channel, "access_token", None) or "").strip()
    waba_id = (getattr(channel, "business_account_id", None) or "").strip()
    if not token:
        return "", json_hash, "Channel access token is missing"
    if not waba_id:
        return "", json_hash, "WhatsApp Business Account ID is missing on this channel"

    meta_id = (existing_id or parsed.get("meta_flow_id") or "").strip()
    stored_hash = (existing_hash or parsed.get("meta_flow_json_hash") or "").strip()
    if meta_id and stored_hash == json_hash:
        return meta_id, json_hash, ""

    headers = {"Authorization": f"Bearer {token}"}
    name = f"ds_wf_{getattr(channel, 'id', 0)}_{name_suffix}"[:80]
    category = PURPOSE_CATEGORY.get(parsed.get("purpose"), "OTHER")

    if not meta_id:
        try:
            res = requests.post(
                f"{_graph_base(channel)}/{waba_id}/flows",
                headers={**headers, "Content-Type": "application/json"},
                json={"name": name, "categories": [category]},
                timeout=25,
            )
            data = res.json() if res.content else {}
            if res.status_code >= 400:
                logger.warning("WhatsApp Flow create failed: %s %s", res.status_code, res.text)
                meta_id = _find_flow_id_by_name(channel, headers, waba_id, name)
                if not meta_id:
                    return "", json_hash, data.get("error", {}).get("message") or res.text[:300]
            else:
                meta_id = str(data.get("id") or "").strip()
        except Exception as exc:
            logger.exception("WhatsApp Flow create error")
            return "", json_hash, str(exc)
    if not meta_id:
        return "", json_hash, "Meta did not return a Flow id"

    try:
        files = {
            "file": ("flow.json", json.dumps(flow_json, ensure_ascii=False).encode("utf-8"), "application/json"),
        }
        res = requests.post(
            f"{_graph_base(channel)}/{meta_id}/assets",
            headers=headers,
            data={"name": "flow.json", "asset_type": "FLOW_JSON"},
            files=files,
            timeout=25,
        )
        if res.status_code >= 400:
            logger.warning("WhatsApp Flow upload failed: %s %s", res.status_code, res.text)
            return meta_id, json_hash, res.text[:300]
    except Exception as exc:
        logger.exception("WhatsApp Flow upload error")
        return meta_id, json_hash, str(exc)

    try:
        res = requests.post(
            f"{_graph_base(channel)}/{meta_id}/publish",
            headers={**headers, "Content-Type": "application/json"},
            json={},
            timeout=25,
        )
        if res.status_code >= 400:
            logger.warning("WhatsApp Flow publish failed: %s %s", res.status_code, res.text)
    except Exception as exc:
        logger.warning("WhatsApp Flow publish error: %s", exc)

    return meta_id, json_hash, ""


def ensure_meta_flow(channel, node, content):
    """Create or update a published WhatsApp Flow. Returns (flow_id, error)."""
    parsed = parse_flow_node_content(content)
    meta_id, json_hash, err = ensure_meta_flow_id(
        channel,
        parsed,
        name_suffix=str(getattr(node, "id", 0)),
        existing_id=parsed.get("meta_flow_id") or "",
        existing_hash=parsed.get("meta_flow_json_hash") or "",
    )
    if meta_id:
        _persist_meta_ids(node, meta_id, json_hash)
    return meta_id, err


def _persist_meta_ids(node, meta_flow_id, json_hash):
    if not node:
        return
    try:
        content = parse_flow_node_content(node.content_text)
        content["meta_flow_id"] = meta_flow_id
        content["meta_flow_json_hash"] = json_hash
        node.content_text = json.dumps(content, ensure_ascii=False)
        node.save(update_fields=["content_text", "updated_at"])
    except Exception as exc:
        logger.warning("persist meta flow id failed: %s", exc)


def persist_meta_on_ai_node(node, meta_flow_id, json_hash):
    if not node:
        return
    try:
        cfg = dict(getattr(node, "ai_model_config", None) or {})
        cfg["checkout_form_meta_flow_id"] = meta_flow_id
        cfg["checkout_form_json_hash"] = json_hash
        node.ai_model_config = cfg
        node.save(update_fields=["ai_model_config", "updated_at"])
    except Exception as exc:
        logger.warning("persist meta flow id on ai node failed: %s", exc)


def _outbound_flow_item(parsed, meta_id, *, node=None, delay=0):
    body_text = parsed["text"]
    flow_token = f"wf_{getattr(node, 'id', 0)}_{uuid.uuid4().hex[:12]}"
    interactive = {
        "type": "flow",
        "body": {"text": body_text},
        "action": {
            "name": "flow",
            "parameters": {
                "flow_message_version": "3",
                "flow_token": flow_token,
                "flow_id": meta_id,
                "flow_cta": parsed["cta_label"],
                "flow_action": "navigate",
                # WhatsApp rejects empty data: {} — omit data unless we pass real keys.
                "flow_action_payload": {"screen": SCREEN_ID},
            },
        },
    }
    if parsed["header_text"]:
        interactive["header"] = {"type": "text", "text": parsed["header_text"]}
    if parsed["footer_text"]:
        interactive["footer"] = {"text": parsed["footer_text"]}
    item = {
        "type": "interactive",
        "interactive": interactive,
        "content": body_text,
        "delay": delay,
        "flow_token": flow_token,
        "meta_flow_id": meta_id,
        "wa_flow_purpose": parsed["purpose"],
    }
    return item, ""


def overlay_order_fields_from_product(parsed, node=None, channel=None):
    """Collect-order forms follow the product checkout_mode, not a custom field list."""
    if not isinstance(parsed, dict) or parsed.get("purpose") != PURPOSE_ORDER:
        return parsed
    product_id = parsed.get("product_id")
    if not product_id:
        return parsed
    try:
        from discount.orders_ai import get_required_order_fields_for_product
        from discount.whatssapAPI.checkout_capture import build_order_form_content, checkout_locale
        from discount.services.product_scope import get_channel_product

        if channel is None and node is not None:
            channel = getattr(getattr(node, "flow", None), "channel", None)
        product = get_channel_product(channel, product_id=product_id) if channel is not None else None
        if not product:
            return parsed
        required = get_required_order_fields_for_product(product)
        if not required:
            parsed["fields"] = []
            return parsed
        locale = checkout_locale(node) if node else "ar"
        built = build_order_form_content(product, required, locale)
        parsed["fields"] = built.get("fields") or []
        if built.get("product_name"):
            parsed["product_name"] = built["product_name"]
    except Exception as exc:
        logger.debug("overlay_order_fields_from_product: %s", exc)
    return parsed


def build_outbound_flow_message(channel, node, sender, connections=None):
    """Return (output_item, error). output_item is sent via send_automated_response."""
    parsed = parse_flow_node_content(getattr(node, "content_text", None))
    parsed = overlay_order_fields_from_product(parsed, node=node, channel=channel)
    if not parsed["text"]:
        return None, "WhatsApp Flow body text is required"
    if parsed["purpose"] == PURPOSE_ORDER and not parsed["product_id"]:
        return None, "Collect order requires a product"
    if parsed["purpose"] == PURPOSE_ORDER and not parsed["fields"]:
        return None, "This product does not collect form details (Direct Sale)"
    if not parsed["fields"]:
        return None, "WhatsApp Flow needs at least one input"

    meta_id, err = ensure_meta_flow(channel, node, parsed)
    if not meta_id:
        return None, err or "Could not create WhatsApp Flow on Meta"

    delay = getattr(node, "delay", 0) or parsed["delay"] or 0
    return _outbound_flow_item(parsed, meta_id, node=node, delay=delay)


def build_outbound_flow_from_parsed(channel, content, sender, *, persist_ai_node=None):
    """Build a Flow message from a content dict (AI hybrid checkout). Does not overwrite node.content_text."""
    parsed = parse_flow_node_content(content if isinstance(content, dict) else {})
    parsed = overlay_order_fields_from_product(parsed, node=persist_ai_node, channel=channel)
    if persist_ai_node:
        cfg = getattr(persist_ai_node, "ai_model_config", None) or {}
        if isinstance(cfg, dict):
            parsed["meta_flow_id"] = parsed.get("meta_flow_id") or cfg.get("checkout_form_meta_flow_id") or ""
            parsed["meta_flow_json_hash"] = (
                parsed.get("meta_flow_json_hash") or cfg.get("checkout_form_json_hash") or ""
            )
    if not parsed["text"]:
        return None, "WhatsApp Flow body text is required"
    if not parsed["fields"]:
        return None, "WhatsApp Flow needs at least one input"
    if parsed["purpose"] == PURPOSE_ORDER and not parsed["product_id"]:
        return None, "Collect order requires a product"

    meta_id, json_hash, err = ensure_meta_flow_id(
        channel,
        parsed,
        name_suffix=f"ai_{getattr(persist_ai_node, 'id', 0)}",
        existing_id=parsed.get("meta_flow_id") or "",
        existing_hash=parsed.get("meta_flow_json_hash") or "",
    )
    if not meta_id:
        return None, err or "Could not create WhatsApp Flow on Meta"
    if persist_ai_node:
        persist_meta_on_ai_node(persist_ai_node, meta_id, json_hash)
    delay = parsed.get("delay") or 0
    return _outbound_flow_item(parsed, meta_id, node=persist_ai_node, delay=delay)


def set_flow_pending(channel, sender, payload):
    if not channel or not sender or not payload:
        return
    key = f"{FLOW_PENDING_PREFIX}{channel.id}:{sender}"
    cache.set(key, payload, timeout=FLOW_PENDING_TTL)
    token = (payload.get("flow_token") or "").strip()
    if token:
        cache.set(f"{FLOW_TOKEN_PREFIX}{token}", payload, timeout=FLOW_PENDING_TTL)


def get_flow_pending(channel, sender, flow_token=""):
    token = (flow_token or "").strip()
    if token:
        data = cache.get(f"{FLOW_TOKEN_PREFIX}{token}")
        if data:
            return data
    if channel and sender:
        return cache.get(f"{FLOW_PENDING_PREFIX}{channel.id}:{sender}")
    return None


def clear_flow_pending(channel, sender, flow_token=""):
    if channel and sender:
        cache.delete(f"{FLOW_PENDING_PREFIX}{channel.id}:{sender}")
    token = (flow_token or "").strip()
    if token:
        cache.delete(f"{FLOW_TOKEN_PREFIX}{token}")


def parse_nfm_reply(msg):
    interactive = msg.get("interactive") if isinstance(msg, dict) else {}
    if not isinstance(interactive, dict):
        return None
    if (interactive.get("type") or "").strip() != "nfm_reply":
        return None
    nfm = interactive.get("nfm_reply") if isinstance(interactive.get("nfm_reply"), dict) else {}
    raw = nfm.get("response_json") or "{}"
    data = {}
    if isinstance(raw, dict):
        data = raw
    elif isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                data = parsed
        except Exception:
            data = {}
    answers = {k: v for k, v in data.items() if k != "flow_token"}
    return {
        "flow_token": str(data.get("flow_token") or "").strip(),
        "answers": answers,
        "body": (nfm.get("body") or "Form submitted").strip() or "Form submitted",
    }


def mapped_value(fields, answers, maps_to):
    for field in fields or []:
        if (field.get("maps_to") or "") == maps_to:
            val = answers.get(field.get("key"))
            if val not in (None, ""):
                if isinstance(val, list):
                    return ", ".join(str(x) for x in val if x not in (None, ""))
                return str(val).strip()
    return ""


def ingest_whatsapp_flow_submission(
    *,
    channel,
    sender,
    answers,
    flow_token="",
    pending=None,
    whatsapp_message_id=None,
):
    """Save the form, optionally create a SimpleOrder, update the contact. Returns submission."""
    from discount.models import Contact, Node, Products, SimpleOrder, WhatsAppFlowSubmission

    pending = pending or {}
    node = None
    node_id = pending.get("from_node_id")
    if node_id:
        node = Node.objects.filter(id=node_id).select_related("flow").first()
    if isinstance(pending.get("content"), dict):
        content = parse_flow_node_content(pending.get("content"))
    else:
        content = parse_flow_node_content(node.content_text if node else None)
    purpose = pending.get("purpose") or content.get("purpose") or PURPOSE_LEAD
    fields = content.get("fields") or []

    name = mapped_value(fields, answers, "name") or ""
    city = mapped_value(fields, answers, "city")
    address = mapped_value(fields, answers, "address")
    email = mapped_value(fields, answers, "email")
    notes = mapped_value(fields, answers, "notes")
    rating = mapped_value(fields, answers, "rating")
    qty_raw = mapped_value(fields, answers, "quantity") or "1"
    try:
        quantity = Decimal(str(qty_raw))
        if quantity <= 0:
            quantity = Decimal("1")
    except (InvalidOperation, TypeError, ValueError):
        quantity = Decimal("1")

    contact = None
    if channel and sender:
        contact = Contact.objects.filter(channel=channel, phone=sender).first()
        if not contact and len(str(sender)) >= 8:
            contact = Contact.objects.filter(channel=channel, phone__endswith=str(sender)[-8:]).first()
        if contact and name and not (contact.name or "").strip():
            contact.name = name[:255]
            contact.save(update_fields=["name"])
        if contact:
            try:
                if purpose == PURPOSE_ORDER:
                    contact.pipeline_stage = Contact.PipelineStage.CLOSED
                elif purpose == PURPOSE_LEAD:
                    contact.pipeline_stage = Contact.PipelineStage.INTERESTED
                contact.save(update_fields=["pipeline_stage"])
            except Exception:
                pass

    product = None
    product_id = pending.get("product_id") or content.get("product_id")
    if product_id and channel:
        from discount.services.product_scope import get_channel_product

        product = get_channel_product(channel, product_id=product_id)

    order = None
    if purpose == PURPOSE_ORDER and product and channel:
        order = _create_order_from_flow(
            channel=channel,
            sender=sender,
            product=product,
            customer_name=name,
            customer_email=email,
            city=city,
            address=address,
            notes=notes,
            quantity=quantity,
            node=node,
        )

    msg_id = (whatsapp_message_id or "").strip() or None
    if msg_id and WhatsAppFlowSubmission.objects.filter(whatsapp_message_id=msg_id).exists():
        return WhatsAppFlowSubmission.objects.filter(whatsapp_message_id=msg_id).first()

    submission = WhatsAppFlowSubmission.objects.create(
        channel=channel,
        contact=contact,
        automation_flow=getattr(node, "flow", None) if node else None,
        node=node,
        product=product,
        order=order,
        purpose=purpose,
        customer_phone=str(sender or "")[:30],
        customer_name=(name or (getattr(contact, "name", None) or ""))[:200],
        payload={
            "answers": answers,
            "rating": rating,
            "city": city,
            "address": address,
            "email": email,
            "notes": notes,
            "quantity": str(quantity),
        },
        flow_token=(flow_token or "")[:200],
        meta_flow_id=str(pending.get("meta_flow_id") or content.get("meta_flow_id") or "")[:64],
        whatsapp_message_id=msg_id,
    )
    return submission


def _create_order_from_flow(*, channel, sender, product, customer_name, customer_email, city, address, notes, quantity, node):
    from discount.models import SimpleOrder
    from discount.orders_ai import _notify_owner_order_created

    city_display = " | ".join(filter(None, [str(city or "").strip(), str(address or "").strip()]))[:100]
    order_id = str(uuid.uuid4())[:8]
    while SimpleOrder.objects.filter(order_id=order_id).exists():
        order_id = str(uuid.uuid4())[:8]
    price = getattr(product, "price", None) or 0
    try:
        price = Decimal(str(price))
    except Exception:
        price = Decimal("0")
    try:
        total = (price * quantity).quantize(Decimal("0.01"))
    except Exception:
        total = price
    is_digital = bool(getattr(product, "is_digital", False))
    status = "pending_payment" if is_digital else "pending"
    note_parts = [str(notes or "").strip()]
    if node:
        note_parts.append(f"WhatsApp Flow node {node.id}")
    order = SimpleOrder.objects.create(
        product=product,
        channel=channel,
        sku=str(getattr(product, "sku", "") or "")[:100],
        product_name=str(getattr(product, "name", "") or "")[:200],
        customer_name=str(customer_name or "")[:200],
        customer_phone=str(sender or "")[:20],
        customer_email=(str(customer_email).strip()[:254] or None) if customer_email else None,
        customer_city=city_display or None,
        is_digital=is_digital,
        order_id=order_id,
        status=status,
        created_at=timezone.now(),
        price=total,
        currency=getattr(product, "currency", None) or "MAD",
        quantity=quantity,
        created_by_ai=False,
        created_by_bot_session=(f"whatsapp_flow:{getattr(channel, 'id', '')}:{sender}"[:100] or None),
        sheets_export_status="pending",
        order_notes="\n".join(p for p in note_parts if p)[:2000] or None,
    )
    try:
        _notify_owner_order_created(channel, order)
    except Exception as exc:
        logger.warning("flow order notify failed: %s", exc)
    return order


def submission_summary(submission):
    if not submission:
        return "Form submitted"
    answers = (submission.payload or {}).get("answers") or {}
    bits = []
    for key, val in answers.items():
        if val in (None, ""):
            continue
        bits.append(f"{key}: {val}")
    label = submission.get_purpose_display()
    extra = " · ".join(bits[:6])
    order = getattr(submission, "order", None)
    if order and getattr(order, "order_id", None):
        extra = f"Order {order.order_id}" + (f" · {extra}" if extra else "")
    return f"{label}: {extra}"[:500] if extra else label


from django.views.decorators.http import require_GET, require_POST
from django.contrib.auth.decorators import login_required

@login_required
@require_GET
def api_whatsapp_flow_submissions(request):
    """GET ?channel_id= — recent WhatsApp Flow form submissions for the channel."""
    from django.http import JsonResponse
    from discount.models import WhatsAppFlowSubmission
    from discount.whatssapAPI.views import get_target_channel

    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return JsonResponse({"submissions": [], "error": "Authentication required"}, status=401)
    channel = get_target_channel(user, request.GET.get("channel_id"))
    if not channel:
        return JsonResponse({"submissions": []})
    rows = (
        WhatsAppFlowSubmission.objects.filter(channel=channel)
        .select_related("product", "order", "contact")
        .order_by("-created_at")[:100]
    )
    data = []
    for row in rows:
        data.append({
            "id": row.id,
            "purpose": row.purpose,
            "customer_phone": row.customer_phone,
            "customer_name": row.customer_name,
            "product_id": row.product_id,
            "product_name": getattr(row.product, "name", "") if row.product_id else "",
            "order_id": getattr(row.order, "order_id", None) if row.order_id else None,
            "payload": row.payload,
            "created_at": row.created_at.isoformat() if row.created_at else "",
        })
    return JsonResponse({"submissions": data})


@login_required
@require_POST
def api_whatsapp_flow_ingest(request):
    """
    POST JSON: {channel_id, sender, answers, flow_token?}
    Manual/test ingest of a form payload (production path is the WhatsApp webhook nfm_reply).
    """
    from django.http import JsonResponse
    from discount.whatssapAPI.views import get_target_channel

    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return JsonResponse({"success": False, "error": "Authentication required"}, status=401)
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)
    channel = get_target_channel(user, payload.get("channel_id"))
    sender = str(payload.get("sender") or "").strip()
    answers = payload.get("answers") if isinstance(payload.get("answers"), dict) else {}
    if not channel or not sender:
        return JsonResponse({"success": False, "error": "channel_id and sender are required"}, status=400)
    pending = get_flow_pending(channel, sender, payload.get("flow_token") or "") or {}
    if payload.get("purpose"):
        pending["purpose"] = payload.get("purpose")
    if payload.get("product_id"):
        pending["product_id"] = payload.get("product_id")
    submission = ingest_whatsapp_flow_submission(
        channel=channel,
        sender=sender,
        answers=answers,
        flow_token=payload.get("flow_token") or "",
        pending=pending,
    )
    return JsonResponse({
        "success": True,
        "submission_id": submission.id if submission else None,
        "order_id": getattr(getattr(submission, "order", None), "order_id", None),
        "summary": submission_summary(submission),
    })


INBOX_FLOW_META_TTL = 60 * 60 * 24 * 30


@login_required
@require_POST
def api_send_checkout_flow(request):
    """
    Inbox: send the product order WhatsApp Flow to the open chat.
    POST JSON: {channel_id, to|phone, product_id}
    """
    from django.http import JsonResponse
    from discount.models import Products
    from discount.orders_ai import get_required_order_fields_for_product
    from discount.whatssapAPI.process_messages import send_automated_response
    from discount.whatssapAPI.views import get_target_channel

    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return JsonResponse({"success": False, "error": "Authentication required"}, status=401)
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)

    channel = get_target_channel(user, payload.get("channel_id"))
    sender = str(payload.get("to") or payload.get("phone") or payload.get("sender") or "").strip()
    try:
        product_id = int(payload.get("product_id") or 0)
    except (TypeError, ValueError):
        product_id = 0
    if not channel or not sender:
        return JsonResponse({"success": False, "error": "channel_id and recipient are required"}, status=400)
    if not product_id:
        return JsonResponse({"success": False, "error": "product_id is required"}, status=400)

    from discount.services.product_scope import get_channel_product

    product = get_channel_product(channel, product_id=product_id)
    if not product:
        return JsonResponse({"success": False, "error": "Product not found"}, status=404)

    from discount.whatssapAPI.checkout_capture import (
        apply_copy_dict_to_content,
        build_order_form_content,
        clip_form_copy_fields,
        copy_row_to_dict,
        form_preview_for_product,
    )
    from discount.models import UserCheckoutFormCopy

    required = get_required_order_fields_for_product(product)
    preview = form_preview_for_product(product, "ar")
    if not preview.get("can_send_form") or not required:
        return JsonResponse({
            "success": False,
            "error": "This product does not collect a form (Direct Sale).",
        }, status=400)

    content = build_order_form_content(product, required, "ar")
    saved_row = UserCheckoutFormCopy.objects.filter(user=user, product=product).first()
    apply_copy_dict_to_content(content, copy_row_to_dict(saved_row))
    apply_copy_dict_to_content(content, clip_form_copy_fields(payload))
    cache_key = f"wa_inbox_flow_meta:{channel.id}:{product.id}"
    cached = cache.get(cache_key) or {}
    if isinstance(cached, dict):
        content["meta_flow_id"] = cached.get("id") or ""
        content["meta_flow_json_hash"] = cached.get("hash") or ""

    item, err = build_outbound_flow_from_parsed(channel, content, sender)
    if not item:
        return JsonResponse({"success": False, "error": err or "Could not build WhatsApp Flow"}, status=502)

    parsed = overlay_order_fields_from_product(parse_flow_node_content(content))
    try:
        cache.set(
            cache_key,
            {"id": item.get("meta_flow_id"), "hash": flow_json_hash(build_flow_json(parsed))},
            INBOX_FLOW_META_TTL,
        )
    except Exception:
        pass

    pending = {
        "flow_id": None,
        "from_node_id": None,
        "next_node_id": None,
        "purpose": PURPOSE_ORDER,
        "product_id": product.id,
        "meta_flow_id": item.get("meta_flow_id"),
        "flow_token": item.get("flow_token"),
        "source": "inbox_checkout_flow",
        "content": parsed,
    }
    set_flow_pending(channel, sender, pending)
    sent = send_automated_response(sender, [item], channel=channel, user=user)
    if not sent:
        return JsonResponse({"success": False, "error": "Could not send the form"}, status=502)
    return JsonResponse({
        "success": True,
        "product_id": product.id,
        "product_name": getattr(product, "name", "") or "",
        "meta_flow_id": item.get("meta_flow_id") or "",
    })


def _inbox_owned_product(user, payload):
    from discount.whatssapAPI.views import get_target_channel

    channel = get_target_channel(user, (payload or {}).get("channel_id"))
    try:
        product_id = int((payload or {}).get("product_id") or 0)
    except (TypeError, ValueError):
        product_id = 0
    if not channel or not product_id:
        return None, None
    from discount.services.product_scope import get_channel_product

    product = get_channel_product(channel, product_id=product_id)
    return channel, product


@login_required
@require_POST
def api_save_checkout_form_copy(request):
    """
    Save or reset this user's order-form message for one product.
    POST JSON: {channel_id, product_id, text, header_text, footer_text, cta_label}
    POST JSON: {channel_id, product_id, reset: true} restores the default copy.
    """
    from django.http import JsonResponse
    from discount.models import UserCheckoutFormCopy
    from discount.whatssapAPI.checkout_capture import (
        clip_form_copy_fields,
        copy_row_to_dict,
        form_preview_for_product,
        merge_preview_with_user_copy,
    )

    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return JsonResponse({"success": False, "error": "Authentication required"}, status=401)
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)

    channel, product = _inbox_owned_product(user, payload)
    if not channel or not product:
        return JsonResponse({"success": False, "error": "Product not found"}, status=404)

    reset = bool(payload.get("reset"))
    if reset:
        UserCheckoutFormCopy.objects.filter(user=user, product=product).delete()
        preview = merge_preview_with_user_copy(form_preview_for_product(product, "ar"), None)
        return JsonResponse({"success": True, "reset": True, "form_preview": preview})

    copy = clip_form_copy_fields(payload)
    if not copy.get("body"):
        return JsonResponse({"success": False, "error": "Message text is required"}, status=400)
    row, _created = UserCheckoutFormCopy.objects.update_or_create(
        user=user,
        product=product,
        defaults={
            "header_text": copy["header"],
            "body_text": copy["body"],
            "footer_text": copy["footer"],
            "cta_label": copy["cta"],
        },
    )
    preview = merge_preview_with_user_copy(form_preview_for_product(product, "ar"), row)
    return JsonResponse({
        "success": True,
        "reset": False,
        "saved": copy_row_to_dict(row),
        "form_preview": preview,
    })

