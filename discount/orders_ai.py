"""
Save order data extracted by AI (e.g. from GPT function calling or [ORDER_DATA: ...] tag).
Used by the AI voice / sales agent auto-reply flow.

ARCHITECTURE RULE: Do not use hardcoded arrays or regex to guess user intent from chat
messages. Always use LLM Tool descriptions and injected context to extract structured data.
This module validates and persists data; it does not interpret phrases like "same number".
"""
import json
import logging
import re
import traceback
import uuid
from datetime import timedelta
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone

from discount.models import SimpleOrder, Products, WhatsAppChannel, CustomUser, Contact

logger = logging.getLogger(__name__)

# Only these keys may appear in submit_customer_order payload; strip any other keys (LLM hallucination).
ALLOWED_ORDER_KEYS = ("customer_name", "phone_number", "shipping_city", "shipping_address")

# Checkout mode (product.checkout_mode) → required_order_fields for AI tool schema and validation
CHECKOUT_MODE_MAP = {
    "quick_lead": ["customer_name", "phone_number"],
    "standard_cod": ["customer_name", "phone_number", "shipping_city"],
    "strict_cod": ["customer_name", "phone_number", "shipping_city", "shipping_address"],
}
CHECKOUT_MODE_LABELS = {
    "quick_lead": "Quick Lead (Name & Phone only)",
    "standard_cod": "Standard COD (Name, Phone, City)",
    "strict_cod": "Strict COD (Full Address)",
}


def get_required_order_fields_for_product(product):
    """
    Resolve required order fields for a product: use checkout_mode if set, else required_order_fields.
    Returns a list of valid field keys for submit_customer_order (e.g. customer_name, phone_number, shipping_city, shipping_address).
    """
    if not product:
        return ["customer_name", "phone_number", "shipping_city", "shipping_address"]
    mode = (getattr(product, "checkout_mode", None) or "").strip()
    if mode and mode in CHECKOUT_MODE_MAP:
        return list(CHECKOUT_MODE_MAP[mode])
    _raw = getattr(product, "required_order_fields", None)
    _valid = {"customer_name", "phone_number", "shipping_city", "shipping_address"}
    if isinstance(_raw, list):
        _filtered = [str(f) for f in _raw if isinstance(f, str) and f in _valid]
        if _filtered:
            return _filtered
    return ["customer_name", "phone_number", "shipping_city", "shipping_address"]


def get_or_create_ai_agent_user(owner, agent_name=None):
    """
    Get or create a Virtual Team Member (CustomUser with is_bot=True) for the given merchant.
    Used so orders created by the AI are attributed to this bot user instead of the account owner.
    """
    if not owner:
        return None
    agent_name = (agent_name or "AI Agent").strip() or "AI Agent"
    # Slug for uniqueness: first word or sanitized agent_name (e.g. "Simo - AI Closer" -> "simo")
    slug = "".join(c for c in agent_name.split()[0].lower() if c.isalnum()) if agent_name else "default"
    if not slug:
        slug = "agent"
    slug = slug[:30]
    owner_id = getattr(owner, "id", None) or getattr(owner, "pk", None)
    if not owner_id:
        return None
    username = f"bot_agent_{owner_id}_{slug}"
    email = f"bot+{owner_id}+{slug}@internal.bot"
    try:
        bot = CustomUser.objects.filter(
            bot_owner_id=owner_id,
            is_bot=True,
            agent_role=agent_name,
        ).first()
        if bot:
            return bot
        # Ensure unique username/email in case of race
        if CustomUser.objects.filter(username=username).exists():
            bot = CustomUser.objects.filter(bot_owner_id=owner_id, is_bot=True).first()
            return bot
        bot = CustomUser.objects.create(
            username=username,
            email=email,
            is_bot=True,
            agent_role=agent_name,
            bot_owner_id=owner_id,
            is_active=True,
        )
        bot.set_unusable_password()
        bot.save()
        logger.info("Created virtual team member (bot) for owner %s: %s", owner_id, agent_name)
        return bot
    except Exception as e:
        logger.warning("get_or_create_ai_agent_user failed: %s; falling back to owner", e)
        return owner

# -----------------------------------------------------------------------------
# International phone validation (Order Extraction Tool guardrail)
# Accepts any country: digits only, 8–15 digits (E.164 allows up to 15).
# Examples: 0612345678 (MA), +966501234567 (SA), +33 6 12 34 56 78 (FR), 201234567890 (EG).
# Returns normalized digits (no + or spaces) for storage; no country-specific rules.
# -----------------------------------------------------------------------------

# Minimum and maximum length for a valid international number (digits only)
_PHONE_DIGITS_MIN = 8
_PHONE_DIGITS_MAX = 15


def validate_phone_international(phone):
    """
    Validate and normalize a phone number from any country.
    Accepts with or without country code, and with spaces/dashes/dots/plus.
    Returns (normalized_digits, None) if valid, or (None, error_message) if invalid.
    normalized_digits: digits only, no + (e.g. 212612345678, 966501234567, 0612345678).
    """
    if not phone or not isinstance(phone, str):
        return (None, "No phone number provided.")
    digits = re.sub(r"\D", "", phone.strip())
    if not digits:
        return (None, "Phone number is empty.")
    if len(digits) < _PHONE_DIGITS_MIN:
        return (
            None,
            "SYSTEM ERROR: The phone number is too short. "
            "Politely ask the customer to provide a valid phone number (with country code if possible, e.g. +XXX...).",
        )
    if len(digits) > _PHONE_DIGITS_MAX:
        digits = digits[:_PHONE_DIGITS_MAX]
    return (digits, None)


def validate_moroccan_phone(phone):
    """
    Validate and normalize a Moroccan mobile number (legacy / Morocco-only flows).
    Accepts with or without country code (+212). Returns (normalized_10_digits, None) or (None, error_message).
    """
    normalized, err = validate_phone_international(phone)
    if err:
        return (None, err)
    digits = normalized
    # With country code: 212 + 6/7 + 8 digits = 12 digits
    if digits.startswith("212") and len(digits) >= 12:
        digits = digits[3:12]
    if len(digits) == 10 and digits.startswith(("06", "07")):
        pass
    elif len(digits) == 10 and digits[0] in ("6", "7"):
        digits = "0" + digits[0] + digits[1:9]
    elif len(digits) == 9 and digits[0] in ("6", "7"):
        digits = "0" + digits
    elif len(digits) > 10 and not digits.startswith("212"):
        tail = digits[-9:] if len(digits) >= 9 else digits
        if tail and tail[0] in ("6", "7") and len(tail) == 9:
            digits = "0" + tail
        else:
            digits = digits[:10]
    else:
        digits = digits[:10] if len(digits) > 10 else digits
    if len(digits) != 10 or digits[0] != "0" or digits[1] not in ("6", "7") or not digits[2:].isdigit() or len(digits[2:]) != 8:
        return (
            None,
            "SYSTEM ERROR: The phone number is not a valid Moroccan mobile. "
            "Politely ask for 06XXXXXXXX, 07XXXXXXXX, or +212 6XX...",
        )
    return (digits, None)


def _safe_order_arg(arguments, key, default=""):
    """Null-safe extraction: checkout_mode may omit fields (e.g. quick_lead has no shipping_*). Never crash on missing or None."""
    if not isinstance(arguments, dict):
        return default or ""
    val = arguments.get(key)
    if val is None:
        return default or ""
    try:
        return (str(val).strip() or default) or ""
    except (TypeError, AttributeError):
        return default or ""


def handle_submit_order_tool(arguments, session_product_id, session_seller_id, channel, customer_phone_from_chat=None):
    """
    Bulletproof submit_customer_order handler.

    - Static schema: product_id, customer_name and phone_number required; shipping_city and shipping_address optional.
    - Asynchronous UX: caller sends the transitional WhatsApp message immediately before calling this handler.
    - DB-safe: shipping_city and shipping_address are always coerced to empty strings (no NULL crashes).
    - Feedback loop: ALWAYS returns a JSON string for the LLM to read (never raises to the caller).
    """
    try:
        logger.info("TOOL CALLED: Raw arguments received -> %s", arguments)

        if not channel or not session_seller_id:
            logger.error(
                "submit_customer_order: missing channel/product/seller (channel=%s, product_id=%s, seller_id=%s)",
                getattr(channel, "id", None),
                session_product_id,
                session_seller_id,
            )
            return json.dumps({
                "status": "error",
                "success": False,
                "message": "Technical configuration error. Tell the user there was a technical glitch and that a human agent will assist shortly.",
            }, ensure_ascii=False)

        if not isinstance(arguments, dict):
            logger.error("submit_customer_order: invalid arguments type (%s)", type(arguments))
            return json.dumps({
                "status": "error",
                "success": False,
                "message": "Invalid order details from AI. Politely ask the user to resend their name and phone number.",
            }, ensure_ascii=False)

        # Static, safe parsing
        customer_name = _safe_order_arg(arguments, "customer_name", "")
        phone_number = _safe_order_arg(arguments, "phone_number", "")
        shipping_city = _safe_order_arg(arguments, "shipping_city", "")
        shipping_address = _safe_order_arg(arguments, "shipping_address", "")
        raw_product_id = arguments.get("product_id")
        tool_product_id = None
        if raw_product_id is not None:
            try:
                tool_product_id = int(raw_product_id)
            except (TypeError, ValueError):
                return json.dumps({
                    "status": "error",
                    "success": False,
                    "message": "product_id is invalid. Ask the user clearly which product they want from the catalog, then use the correct numeric ID.",
                }, ensure_ascii=False)

        # Enforce required fields in code (product_id + name + phone)
        effective_product_id = tool_product_id or session_product_id
        if not effective_product_id:
            return json.dumps({
                "status": "error",
                "success": False,
                "message": "product_id is missing. Ask the user exactly which product they want to order from the catalog, then call the tool again with that product_id.",
            }, ensure_ascii=False)

        if not customer_name:
            return json.dumps({
                "status": "error",
                "success": False,
                "message": "Customer name is missing. Politely ask the user to share their full name.",
            }, ensure_ascii=False)

        phone_to_use = phone_number or (customer_phone_from_chat or "")
        phone_to_use = phone_to_use.strip()
        if not phone_to_use:
            return json.dumps({
                "status": "error",
                "success": False,
                "message": "Phone number is missing. Politely ask the user to confirm or send their phone number (with country code).",
            }, ensure_ascii=False)

        normalized_phone, phone_error = validate_phone_international(phone_to_use)
        if phone_error:
            return json.dumps({
                "status": "error",
                "success": False,
                "message": phone_error,
            }, ensure_ascii=False)

        # At this point, shipping_city / shipping_address are guaranteed non-None strings (possibly "")
        logger.info("VALIDATION PASSED: name=%s, phone=%s, city=%s, address=%s",
                    customer_name, normalized_phone, shipping_city, shipping_address)

        # Resolve product and store
        product = Products.objects.filter(id=effective_product_id, admin_id=session_seller_id).first()
        if not product:
            logger.error("submit_customer_order: product_id=%s not found for seller %s", effective_product_id, session_seller_id)
            return json.dumps({
                "status": "error",
                "success": False,
                "message": "Product not available anymore or does not belong to this store. Tell the user to choose a product from the catalog and use its ID.",
            }, ensure_ascii=False)

        store = getattr(channel, "owner", None)
        if not store or getattr(store, "id", None) != session_seller_id:
            logger.error("submit_customer_order: store mismatch (channel.owner_id=%s, session_seller_id=%s)",
                         getattr(store, "id", None), session_seller_id)
            return json.dumps({
                "status": "error",
                "success": False,
                "message": "Store configuration mismatch. Tell the user there was a technical glitch and that a human agent will assist shortly.",
            }, ensure_ascii=False)

        # Database insertion with strict try/except
        try:
            logger.info("DB INSERT ATTEMPT... (product_id=%s, customer=%s)", effective_product_id, customer_name)

            try:
                price = Decimal(str(getattr(product, "price", None) or "0"))
            except Exception:
                price = Decimal("0")
            if price is None or price <= 0:
                price = Decimal("0")

            order_agent = get_or_create_ai_agent_user(store, agent_name="AI Agent") or store

            order_id = str(uuid.uuid4())[:8]
            while SimpleOrder.objects.filter(order_id=order_id).exists():
                order_id = str(uuid.uuid4())[:8]

            customer_city_display = f"{shipping_city} | {shipping_address}".strip()

            _ord_cur = (getattr(product, "currency", None) or "").strip() or "MAD"
            order = SimpleOrder.objects.create(
                product=product,
                agent=order_agent,
                channel=channel,
                sku=str(getattr(product, "sku", "") or "")[:100],
                product_name=str(getattr(product, "name", "") or "")[:200],
                customer_name=str(customer_name)[:200],
                customer_phone=str(normalized_phone)[:20],
                # Explicitly avoid NULLs: use "" when no city/address provided
                customer_city=customer_city_display[:100] if customer_city_display else "",
                order_id=order_id,
                status="pending",
                created_at=timezone.now(),
                price=price,
                currency=_ord_cur,
                quantity=Decimal("1"),
                created_by_ai=True,
                created_by_bot_session=(f"submit_order:{getattr(channel, 'id', '')}:{normalized_phone}"[:100] or None),
                sheets_export_status="pending",
            )

            logger.info("DB SUCCESS: Order ID -> %s", order_id)

            try:
                from discount.whatssapAPI.follow_up import cancel_pending_follow_up_tasks_for_customer
                cancel_pending_follow_up_tasks_for_customer(channel, normalized_phone)
            except Exception as e:
                logger.warning("cancel_pending_follow_up_tasks_for_customer: %s", e)

            try:
                if order:
                    _notify_owner_order_created(channel, order)
                contact = Contact.objects.filter(channel=channel).filter(phone=normalized_phone).first()
                if not contact and len(normalized_phone) >= 8:
                    contact = Contact.objects.filter(channel=channel).filter(phone__endswith=normalized_phone[-8:]).first()
                if contact:
                    contact.pipeline_stage = Contact.PipelineStage.CLOSED
                    contact.save(update_fields=["pipeline_stage"])
            except Exception as e:
                logger.warning("submit_customer_order: contact pipeline update failed: %s", e)

            return json.dumps({
                "status": "success",
                "success": True,
                "message": "Order saved successfully. Confirm the order with the customer now.",
                "order_id": order_id,
            }, ensure_ascii=False)

        except Exception as db_err:
            logger.error("DB INSERT ERROR in submit_customer_order -> %s", db_err)
            logger.error("DB INSERT ERROR (stack) -> %s", traceback.format_exc())
            return json.dumps({
                "status": "error",
                "success": False,
                "message": "Database insertion failed. Tell the user there was a technical glitch and ask them to verify their details or wait for human support.",
            }, ensure_ascii=False)

    except Exception as e:
        logger.error("FATAL TOOL ERROR in submit_customer_order -> %s", e)
        logger.error("FATAL TOOL ERROR (stack) -> %s", traceback.format_exc())
        return json.dumps({
            "status": "error",
            "success": False,
            "message": "System error while processing the order. Tell the user there was a technical glitch and that a human agent will assist shortly.",
        }, ensure_ascii=False)


def handle_add_upsell_tool(arguments, channel):
    """
    UPDATE an existing order to add an upsell item (same package, same shipment).
    Appends the new item name to product_name, adds price, increments quantity.
    Returns a JSON string for the LLM context.
    """
    try:
        logger.info("UPSELL TOOL CALLED: args -> %s", arguments)

        if not isinstance(arguments, dict):
            return json.dumps({"status": "error", "success": False,
                               "message": "Invalid arguments. Ask the user to confirm the upsell."}, ensure_ascii=False)

        order_id = _safe_order_arg(arguments, "order_id", "")
        new_item_name = _safe_order_arg(arguments, "new_item_name", "")
        raw_price = arguments.get("new_item_price")

        if not order_id:
            return json.dumps({"status": "error", "success": False,
                               "message": "order_id is missing. You should have the order_id from the previous order in your context."}, ensure_ascii=False)
        if not new_item_name:
            return json.dumps({"status": "error", "success": False,
                               "message": "new_item_name is missing. Ask the user which product they want to add."}, ensure_ascii=False)

        try:
            new_price = Decimal(str(raw_price or "0"))
            if new_price < 0:
                new_price = Decimal("0")
        except Exception:
            new_price = Decimal("0")

        order = SimpleOrder.objects.filter(order_id=order_id).first()
        if not order:
            logger.error("UPSELL: order_id=%s not found", order_id)
            return json.dumps({"status": "error", "success": False,
                               "message": "Order not found. The order_id may be incorrect."}, ensure_ascii=False)

        if channel and order.channel_id and order.channel_id != channel.id:
            logger.error("UPSELL: order channel mismatch (order.channel=%s, current=%s)", order.channel_id, channel.id)
            return json.dumps({"status": "error", "success": False,
                               "message": "Order does not belong to this channel."}, ensure_ascii=False)

        old_product_name = (order.product_name or "").strip()
        old_price = order.price or Decimal("0")
        old_quantity = order.quantity or Decimal("1")

        order.product_name = f"{old_product_name} + {new_item_name.strip()}"[:200]
        order.price = old_price + new_price
        order.quantity = old_quantity + Decimal("1")

        if order.sheets_export_status == "success":
            order.sheets_export_status = "pending"

        order.save(update_fields=["product_name", "price", "quantity", "sheets_export_status"])

        logger.info("UPSELL DB SUCCESS: order_id=%s, new total=%s, items=%s",
                     order_id, order.price, order.product_name)

        try:
            _resync_upsell_to_google_sheets(order)
        except Exception as gs_err:
            logger.warning("UPSELL Google Sheets re-sync: %s", gs_err)

        return json.dumps({
            "status": "success",
            "success": True,
            "message": f"Upsell added! The order now contains: {order.product_name}. New total: {order.price}. Confirm this with the customer.",
            "order_id": order_id,
            "updated_product_name": order.product_name,
            "updated_price": str(order.price),
        }, ensure_ascii=False)

    except Exception as e:
        logger.error("FATAL UPSELL TOOL ERROR -> %s", e)
        logger.error("FATAL UPSELL TOOL ERROR (stack) -> %s", traceback.format_exc())
        return json.dumps({"status": "error", "success": False,
                           "message": "System error adding the upsell. Tell the user there was a glitch."}, ensure_ascii=False)


_NOTE_CATEGORY_CANONICAL = {
    "delivery_time": "delivery_time",
    "alternate_phone": "alternate_phone",
    "general_instruction": "general_instruction",
    "general": "general_instruction",
}


def _first_valid_phone_in_text(text):
    """Extract first internationally-valid phone digit sequence from free-form note text."""
    if not text or not isinstance(text, str):
        return None
    for chunk in re.findall(r"\+?[\d\s\-\.]{8,24}", text):
        normalized, err = validate_phone_international(chunk)
        if not err and normalized:
            return normalized
    digits_only = re.sub(r"\D", "", text)
    if len(digits_only) >= _PHONE_DIGITS_MIN:
        normalized, err = validate_phone_international(digits_only)
        if not err and normalized:
            return normalized
    return None


def execute_update_order_notes(order_id, note_category, note_content, channel=None, customer_phone_from_chat=None):
    """
    Persist post-order instructions on SimpleOrder.order_notes (append). Optionally updates
    customer_phone when note_category is alternate_phone and a valid number is found in note_content.

    Returns a JSON str for the LLM tool result (never raises to caller).
    """
    try:
        order_id = _safe_order_arg({"order_id": order_id}, "order_id", "")
        note_category = (str(note_category or "").strip())
        note_content = (str(note_content or "").strip())

        if not order_id:
            return json.dumps({
                "status": "error",
                "success": False,
                "message": "order_id is missing. Use the active order_id from your context (e.g. last_order_id).",
            }, ensure_ascii=False)
        if not note_content:
            return json.dumps({
                "status": "error",
                "success": False,
                "message": "note_content is empty. Ask the customer to repeat their instruction.",
            }, ensure_ascii=False)

        cat_key = (note_category or "").strip().lower().replace(" ", "_")
        canonical = _NOTE_CATEGORY_CANONICAL.get(cat_key, "general_instruction")

        order = SimpleOrder.objects.filter(order_id=order_id).first()
        if not order:
            logger.error("update_order_notes: order_id=%s not found", order_id)
            return json.dumps({
                "status": "error",
                "success": False,
                "message": "Order not found. Confirm the order reference with the customer.",
            }, ensure_ascii=False)

        if channel and order.channel_id and order.channel_id != channel.id:
            logger.error(
                "update_order_notes: channel mismatch (order.channel=%s, current=%s)",
                order.channel_id, getattr(channel, "id", None),
            )
            return json.dumps({
                "status": "error",
                "success": False,
                "message": "Order does not belong to this store channel.",
            }, ensure_ascii=False)

        # Loose match: order should belong to this chat customer when possible
        if customer_phone_from_chat:
            chat_n, _ = validate_phone_international(str(customer_phone_from_chat))
            ord_n, _ = validate_phone_international(order.customer_phone or "")
            if chat_n and ord_n and chat_n != ord_n:
                if len(chat_n) >= 8 and len(ord_n) >= 8 and chat_n[-8:] != ord_n[-8:]:
                    logger.warning(
                        "update_order_notes: phone mismatch (chat vs order) order_id=%s — still allowing (same channel)",
                        order_id,
                    )

        ts = timezone.now().strftime("%Y-%m-%d %H:%M")
        line = f"[{ts}] [{canonical}] {note_content.strip()}"
        prev = (order.order_notes or "").strip()
        order.order_notes = (prev + "\n" + line).strip() if prev else line

        update_fields = ["order_notes"]

        if canonical == "alternate_phone":
            alt = _first_valid_phone_in_text(note_content)
            if alt:
                order.customer_phone = str(alt)[:20]
                update_fields.append("customer_phone")

        if getattr(order, "sheets_export_status", None) == "success":
            order.sheets_export_status = "pending"
            update_fields.append("sheets_export_status")

        order.save(update_fields=list(dict.fromkeys(update_fields)))

        logger.info("update_order_notes: saved order_id=%s category=%s", order_id, canonical)

        return json.dumps({
            "status": "success",
            "success": True,
            "message": "Note saved on the order. Confirm to the customer it was registered for the delivery team.",
            "order_id": order_id,
        }, ensure_ascii=False)

    except Exception as e:
        logger.error("execute_update_order_notes: %s", e)
        logger.error(traceback.format_exc())
        return json.dumps({
            "status": "error",
            "success": False,
            "message": "Could not save the note. Ask the customer to try again or contact support.",
        }, ensure_ascii=False)


def _resync_upsell_to_google_sheets(order):
    """
    After an upsell UPDATE, find the existing row in Google Sheets by order_id
    and update the product_name and price cells in-place (no new row).
    """
    try:
        from discount.models import GoogleSheetsConfig
        from discount.services.google_sheets_service import get_client_for_config
    except ImportError:
        return

    if not order.channel or not order.channel.owner_id:
        return

    config = GoogleSheetsConfig.objects.filter(user_id=order.channel.owner_id).first()
    if not config or not (getattr(config, "spreadsheet_id", None) or "").strip():
        return

    client = get_client_for_config(config)
    if not client:
        return

    spreadsheet_id = (config.spreadsheet_id or "").strip()
    sheet_name = (getattr(config, "sheet_name", None) or "Orders").strip()

    try:
        spreadsheet = client.open_by_key(spreadsheet_id)
        worksheet = spreadsheet.worksheet(sheet_name)

        sheets_mapping = getattr(config, "sheets_mapping", None)
        column_mapping = getattr(config, "column_mapping", None) or {}

        order_id_col = _find_column_for_field("order_id", sheets_mapping, column_mapping)
        product_name_col = _find_column_for_field("product_name", sheets_mapping, column_mapping)
        price_col = _find_column_for_field("price", sheets_mapping, column_mapping)
        quantity_col = _find_column_for_field("quantity", sheets_mapping, column_mapping)

        if not order_id_col:
            logger.info("UPSELL SHEETS: no order_id column mapped, cannot locate row")
            return

        all_values = worksheet.col_values(_col_letter_to_index(order_id_col))
        target_row = None
        oid_str = str(order.order_id or "")
        for i, val in enumerate(all_values):
            if str(val).strip() == oid_str:
                target_row = i + 1
                break

        if not target_row:
            logger.info("UPSELL SHEETS: order_id=%s not found in column %s, appending fresh row instead", oid_str, order_id_col)
            order.sheets_export_status = "pending"
            order.save(update_fields=["sheets_export_status"])
            from discount.services.google_sheets_service import sync_order_to_google_sheets
            sync_order_to_google_sheets(order.pk)
            return

        updates = {}
        if product_name_col:
            updates[f"{product_name_col}{target_row}"] = order.product_name or ""
        if price_col:
            updates[f"{price_col}{target_row}"] = str(order.price) if order.price is not None else ""
        if quantity_col:
            updates[f"{quantity_col}{target_row}"] = str(order.quantity) if order.quantity is not None else ""

        if updates:
            for cell_ref, value in updates.items():
                worksheet.update(cell_ref, [[value]], value_input_option="USER_ENTERED")
            logger.info("UPSELL SHEETS: updated row %d for order_id=%s (%s)", target_row, oid_str, list(updates.keys()))

        order.sheets_export_status = "success"
        order.sheets_export_error = None
        order.save(update_fields=["sheets_export_status", "sheets_export_error"])

    except Exception as e:
        logger.exception("_resync_upsell_to_google_sheets failed: %s", e)
        try:
            order.sheets_export_status = "failed"
            order.sheets_export_error = str(e)[:500]
            order.save(update_fields=["sheets_export_status", "sheets_export_error"])
        except Exception:
            pass


def _find_column_for_field(field_name, sheets_mapping, column_mapping):
    """Find the column letter for a given field name from sheets_mapping or column_mapping."""
    if sheets_mapping and isinstance(sheets_mapping, list):
        for i, entry in enumerate(sheets_mapping):
            mapped_field = entry.get("field") if isinstance(entry, dict) else None
            if mapped_field == field_name:
                return _col_index_to_letter(i + 1)
    if column_mapping and isinstance(column_mapping, dict):
        for col_letter, var_key in column_mapping.items():
            if var_key == field_name:
                return col_letter
    return None


def _col_index_to_letter(index):
    """Convert 1-based column index to letter (1=A, 2=B, ..., 27=AA)."""
    result = ""
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _col_letter_to_index(letter):
    """Convert column letter to 1-based index (A=1, B=2, ..., AA=27)."""
    result = 0
    for ch in letter.upper():
        result = result * 26 + (ord(ch) - 64)
    return result


def handle_update_lead_status(channel, customer_phone, new_status):
    """
    Update the Contact (lead) pipeline_stage in the database.
    Used by the update_lead_status AI tool.

    - If the current status is already 'closed', do NOT downgrade to interested/follow_up
      (protect completed sales).
    - Valid new_status: 'interested', 'follow_up', 'rejected'.

    Returns:
        dict: {"success": True} or {"success": False, "message": "..."}
    """
    if not channel or not customer_phone:
        return {"success": False, "message": "Channel or customer phone missing."}
    valid = ("interested", "follow_up", "rejected")
    if new_status not in valid:
        return {"success": False, "message": f"Invalid status. Use one of: {valid}."}
    try:
        contact = Contact.objects.filter(channel=channel, phone=customer_phone).first()
        if not contact and len(customer_phone) >= 8:
            contact = Contact.objects.filter(channel=channel).filter(phone__endswith=customer_phone[-8:]).first()
        if not contact:
            return {"success": False, "message": "Contact not found."}
        current = (contact.pipeline_stage or "").strip().lower()
        if current == Contact.PipelineStage.CLOSED:
            return {"success": True, "message": "Lead already closed; no change."}
        contact.pipeline_stage = new_status
        contact.save(update_fields=["pipeline_stage"])
        return {"success": True}
    except Exception as e:
        logger.exception("handle_update_lead_status: %s", e)
        return {"success": False, "message": str(e)}


# Robust match for [ORDER_DATA: {...}] — extract JSON by brace-matching so commas/quotes inside values are safe
ORDER_DATA_TAG_PREFIX_RE = re.compile(r"\[ORDER_DATA:\s*(\{)", re.IGNORECASE)


def _extract_order_data_json(reply_text):
    """
    Find [ORDER_DATA: {...}] and return (start, end, json_str) for the first valid brace-balanced block.
    Returns (None, None, None) if not found or invalid.
    """
    if not reply_text or not isinstance(reply_text, str):
        return (None, None, None)
    m = ORDER_DATA_TAG_PREFIX_RE.search(reply_text)
    if not m:
        return (None, None, None)
    start_brace = m.start(1)
    i = start_brace + 1
    depth = 1
    while i < len(reply_text) and depth > 0:
        c = reply_text[i]
        if c == "\\" and i + 1 < len(reply_text):
            i += 2
            continue
        if c == '"':
            j = i + 1
            while j < len(reply_text):
                if reply_text[j] == "\\":
                    j += 2
                    continue
                if reply_text[j] == '"':
                    i = j + 1
                    break
                j += 1
            else:
                i = j
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                tag_end = i + 1
                while tag_end < len(reply_text) and reply_text[tag_end] in " \t\r\n]":
                    tag_end += 1
                return (m.start(), tag_end, reply_text[start_brace : i + 1])
        i += 1
    return (None, None, None)

# Buying-signal phrases: customer must show intent before we ask for name/city/address
BUYING_SIGNAL_PATTERNS = [
    r"\b(how much is it|how much|what.?s the price|is there a discount|any discount|how do i pay|how can i pay|i liked this|i like it|does it have a warranty|warranty\?|garantie)\b",
    r"\b(i want it|i want one|i'll take it|i'll take one|i need it|how can i buy|how do i buy|where can i buy)\b",
    r"\b(ok|okay|yes|confirm|confirmed|deal|done|let's do it|جيبلي|بدي|بدّي|كيفاش نشري|نشري|ونين نقدمو|نقدمو)\b",
    r"\b(je le prends|je veux|je prends|combien|comment acheter|j'achète|ça coûte|prix|réduction)\b",
    r"\b(السعر مناسب|الثمن مزيان|تمام|نعم|أكيد|كم الثمن|كم السعر|في تخفيض|ضمان)\b",
]
BUYING_SIGNAL_RE = re.compile("|".join(BUYING_SIGNAL_PATTERNS), re.IGNORECASE)

TRUST_SCORE_MIN_FOR_ORDER = 1  # Allow order save after 1+ helpful exchange (was 3; AI confirms only when it has name+address)
TRUST_SCORE_MAX = 10
TRUST_SCORE_CACHE_TIMEOUT = 3600


def get_trust_score(channel_id, sender):
    """Get current trust_score from cache (0 if missing)."""
    try:
        from django.core.cache import cache
        key = f"trust_score:{channel_id}:{sender}"
        val = cache.get(key)
        return max(0, min(TRUST_SCORE_MAX, int(val))) if val is not None else 0
    except Exception:
        return 0


def increment_trust_score(channel_id, sender):
    """Increment trust_score after a helpful reply (cap at TRUST_SCORE_MAX). Returns new value."""
    try:
        from django.core.cache import cache
        key = f"trust_score:{channel_id}:{sender}"
        current = get_trust_score(channel_id, sender)
        new_val = min(TRUST_SCORE_MAX, current + 1)
        cache.set(key, new_val, TRUST_SCORE_CACHE_TIMEOUT)
        return new_val
    except Exception:
        return 0


def reset_trust_score(channel_id, sender):
    """Reset trust_score to 0 (e.g. after order is saved)."""
    try:
        from django.core.cache import cache
        cache.set(f"trust_score:{channel_id}:{sender}", 0, TRUST_SCORE_CACHE_TIMEOUT)
    except Exception:
        pass


def customer_gave_buying_signal(conversation_messages, last_n=5):
    """
    Return True if any of the last_n customer messages contain a buying signal
    (e.g. "I want it", "how can I buy", "ok", "جيبلي"). Used to allow ORDER_DATA
    only after the customer has agreed to buy.
    """
    if not conversation_messages:
        return False
    customer_bodies = [
        (m.get("body") or "").strip()
        for m in conversation_messages[-last_n:]
        if m.get("role") == "customer"
    ]
    for body in customer_bodies:
        if body and BUYING_SIGNAL_RE.search(body):
            return True
    return False


def should_accept_order_data(conversation_messages, order_data, current_stage=None, trust_score=None):
    """
    Return True only when we should save ORDER_DATA (strict slot-filling).
    Required: name (full or first), phone (from sender), and delivery location (address or city).
    We require: name and (address or city) non-empty; trust_score >= TRUST_SCORE_MIN_FOR_ORDER if provided;
    and either stage is order_capture, customer gave a buying signal, or we have full slots and minimal trust (AI confirmed).
    """
    if not order_data or not isinstance(order_data, dict):
        return False
    name = (order_data.get("name") or order_data.get("customer_name") or "").strip()
    city = (order_data.get("city") or order_data.get("customer_city") or "").strip()
    address = (order_data.get("address") or "").strip()
    delivery = (address or city).strip()
    if not name or not delivery:
        return False
    ts = int(trust_score) if trust_score is not None else 0
    if trust_score is not None and ts < TRUST_SCORE_MIN_FOR_ORDER:
        return False
    if current_stage == "order_capture":
        return True
    if customer_gave_buying_signal(conversation_messages or []):
        return True
    # AI only outputs ORDER_DATA / calls save_order when it has name+address; accept with minimal trust
    if ts >= TRUST_SCORE_MIN_FOR_ORDER:
        return True
    return False


def is_order_cap_reached(channel):
    """Return True if the channel's plan has max_monthly_orders and current month count >= cap."""
    store = getattr(channel, "owner", None)
    if not store:
        return False
    try:
        from discount.services.plan_limits import is_limit_reached
        reached, _limit, _current = is_limit_reached(store, "max_monthly_orders")
        return reached
    except Exception:
        logger.debug("is_order_cap_reached: plan_limits import failed, falling back")
        if not hasattr(store, "get_plan") or not callable(store.get_plan):
            return False
        plan = store.get_plan()
        if not plan or getattr(plan, "max_monthly_orders", None) is None:
            return False
        start_of_month = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        count = SimpleOrder.objects.filter(channel=channel, created_at__gte=start_of_month).count()
        return count >= plan.max_monthly_orders


def _order_data_has_all_mandatory_slots(data):
    """Strict slot-filling: require name and delivery location (address required; city optional)."""
    if not data or not isinstance(data, dict):
        return False
    name = (data.get("name") or data.get("customer_name") or "").strip()
    city = (data.get("city") or data.get("customer_city") or "").strip()
    address = (data.get("address") or "").strip()
    return bool(name) and bool(address or city)


# Phrases that mean "order confirmed" — if these appear without [ORDER_DATA] we flag Incomplete Capture
ORDER_CONFIRMATION_PHRASES_RE = re.compile(
    r"(?:تم\s+تسجيل\s+طلبك|طلبك\s+تم\s+تسجيله|order\s+is\s+registered|your\s+order\s+is\s+confirmed|"
    r"commande\s+enregistrée|طلبك\s+مسجل)",
    re.IGNORECASE | re.UNICODE,
)


def looks_like_order_confirmation_without_data(reply_text):
    """
    True if the reply sounds like an order confirmation but we did not get valid [ORDER_DATA].
    Used to trigger retry / incomplete-capture handling.
    """
    if not reply_text or not isinstance(reply_text, str):
        return False
    return bool(ORDER_CONFIRMATION_PHRASES_RE.search(reply_text))


def extract_order_data_from_reply(reply_text):
    """
    If reply_text contains the hidden tag [ORDER_DATA: {...}], parse and return the dict
    only when all mandatory slots are present (name, city or address). Strip the tag from text.
    Uses brace-matching for robust JSON extraction. Returns (cleaned_reply, order_data_dict or None).
    """
    if not reply_text or not isinstance(reply_text, str):
        return (reply_text or "", None)
    start, end, json_str = _extract_order_data_json(reply_text)
    if start is None or not json_str:
        return (reply_text.strip(), None)
    try:
        data = json.loads(json_str)
        if not isinstance(data, dict):
            return (reply_text.strip(), None)
        # Normalize keys (name/customer_name, city/customer_city, address, sku/product_name)
        name = (data.get("name") or data.get("customer_name") or "").strip()
        city = (data.get("city") or data.get("customer_city") or "").strip()
        address = (data.get("address") or "").strip()
        sku = (data.get("sku") or "").strip()
        product_name = (data.get("product_name") or data.get("product") or "").strip()
        if not name or not (address or city):
            logger.warning("extract_order_data_from_reply: tag found but name/city/address missing or empty")
            return (reply_text.strip(), None)
        # Require product: do not accept [ORDER_DATA] without at least sku or product_name
        if not sku and not product_name:
            logger.warning("extract_order_data_from_reply: tag found but no product (sku or product_name); rejecting to avoid order without product")
            return (reply_text.strip(), None)
        order_data = {"name": name, "city": city or "", "address": address or "", "sku": sku, "product_name": product_name}
        cleaned = (reply_text[:start].strip() + " " + reply_text[end:].strip()).strip()
        return (cleaned, order_data)
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning("extract_order_data_from_reply parse error: %s", e)
    return (reply_text.strip(), None)


def track_order(customer_phone, channel=None):
    """
    Find the latest order for the given customer_phone (optionally scoped to channel).
    Returns a dict with status, shipping_company, expected_delivery_date, customer_name, and found (bool).
    If no order is found, returns found=False and status=None, etc.
    """
    if not customer_phone or not isinstance(customer_phone, str):
        return {
            "found": False,
            "status": None,
            "shipping_company": None,
            "expected_delivery_date": None,
            "days_until_delivery": None,
            "customer_name": None,
        }
    qs = SimpleOrder.objects.filter(customer_phone=customer_phone.strip()).order_by("-created_at")
    if channel:
        qs = qs.filter(channel=channel)
    order = qs.first()
    if not order:
        return {
            "found": False,
            "status": None,
            "shipping_company": None,
            "expected_delivery_date": None,
            "days_until_delivery": None,
            "customer_name": None,
        }
    expected_date = None
    days_until_delivery = None
    if getattr(order, "expected_delivery_date", None):
        expected_date = order.expected_delivery_date.isoformat()
        today = timezone.now().date()
        delta = order.expected_delivery_date - today
        days_until_delivery = max(0, delta.days)
    return {
        "found": True,
        "status": (order.status or "").strip() or "pending",
        "shipping_company": (getattr(order, "shipping_company", None) or "").strip() or None,
        "expected_delivery_date": expected_date,
        "days_until_delivery": days_until_delivery,
        "customer_name": (order.customer_name or "").strip() or None,
    }


def save_order_from_ai(channel, customer_phone, customer_name=None, customer_city=None,
                       sku=None, product_name=None, price=None, quantity=1,
                       agent_name=None, bot_session_id=None, **kwargs):
    """
    Create a SimpleOrder from AI-extracted data. Order is attributed to a Virtual Team Member (bot user).

    Args:
        channel: WhatsAppChannel instance (required).
        customer_phone: str (required).
        customer_name: str (optional).
        customer_city: str (optional) – address/city.
        sku: str (optional) – product SKU.
        product_name: str (optional).
        price: number or str (optional).
        quantity: number (default 1).
        agent_name: str (optional) – e.g. "Simo - AI Closer"; used to get/create the bot user.
        bot_session_id: str (optional) – conversation/session ID for tracing.
        **kwargs: ignored or used for other fields (e.g. customer_country).

    Returns:
        SimpleOrder instance on success; None on failure; or a dict {"saved": False, "message": str}
        when price is 0/missing so the AI can be told to re-check the conversation and extract the price.
    """
    if not channel or not customer_phone:
        logger.warning("save_order_from_ai: channel and customer_phone required")
        return None

    # Require at least one product identifier (no orders for "no product" / out-of-context)
    sku_str = (sku or "").strip()
    product_name_str = (product_name or "").strip()
    if not sku_str and not product_name_str:
        logger.warning("save_order_from_ai: rejected — no product (sku or product_name). Do not save when no product is selected.")
        return None

    # Parse price; when 0 or missing we may use product price from DB or ask the AI to re-extract from conversation
    price_val = Decimal("0")
    if price is not None:
        try:
            price_val = Decimal(str(price))
        except Exception:
            pass

    # Resolve product early when price is missing/0 so we can use product.price from DB
    product_instance = None
    if sku_str and getattr(channel, "owner", None):
        try:
            product_instance = Products.objects.filter(admin=channel.owner).filter(sku=sku_str).first()
            if not product_instance:
                product_instance = Products.objects.filter(sku=sku_str).first()
        except Exception as e:
            logger.warning("save_order_from_ai product lookup for sku=%s: %s", sku_str, e)
    if sku_str and not product_instance:
        logger.warning("save_order_from_ai: rejected — sku=%s does not match any product in the store.", sku_str)
        return None
    if not product_instance and product_name_str and getattr(channel, "owner", None):
        try:
            product_instance = Products.objects.filter(
                admin=channel.owner,
                name__iexact=product_name_str,
            ).first()
            if not product_instance:
                product_instance = Products.objects.filter(
                    admin=channel.owner,
                    name__icontains=product_name_str,
                ).first()
        except Exception as e:
            logger.warning("save_order_from_ai product lookup by name=%s: %s", product_name_str, e)
        if not product_instance:
            logger.warning("save_order_from_ai: rejected — product_name=%r does not match any product in the store.", product_name_str)
            return None

    # When price is 0 or missing: use product price from DB if available; otherwise ask AI to re-extract from conversation
    if price_val is None or price_val <= 0:
        if product_instance:
            try:
                p = getattr(product_instance, "price", None)
                if p is not None and Decimal(str(p)) > 0:
                    price_val = Decimal(str(p))
            except Exception:
                pass
        if price_val is None or price_val <= 0:
            logger.warning("save_order_from_ai: rejected — price must be positive (got %s). Ask AI to re-extract from conversation.", price_val)
            return {
                "saved": False,
                "message": "SYSTEM ERROR: The product price could not be determined (price is 0 or missing). Review the conversation history — if the price was mentioned or sent to the customer (e.g. in product context or in your previous messages), extract it and call save_order again with the 'price' parameter set to that value.",
            }

    store = getattr(channel, "owner", None)
    ai_agent_user = get_or_create_ai_agent_user(store, agent_name="AI Agent")
    order_agent = ai_agent_user if ai_agent_user else store

    # Plan: max_monthly_orders cap (stop auto-order when reached)
    if store and hasattr(store, "get_plan") and callable(store.get_plan):
        plan = store.get_plan()
        if plan and getattr(plan, "max_monthly_orders", None) is not None:
            start_of_month = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            count = SimpleOrder.objects.filter(channel=channel, created_at__gte=start_of_month).count()
            if count >= plan.max_monthly_orders:
                logger.info("save_order_from_ai: max_monthly_orders (%s) reached for channel %s", plan.max_monthly_orders, channel.id)
                return None

    try:
        order_id = str(uuid.uuid4())[:8]
        # Ensure uniqueness
        while SimpleOrder.objects.filter(order_id=order_id).exists():
            order_id = str(uuid.uuid4())[:8]

        qty_val = Decimal("1")
        if quantity is not None:
            try:
                qty_val = Decimal(str(quantity))
            except Exception:
                pass

        _cur = (getattr(product_instance, "currency", None) or "").strip() or "MAD" if product_instance else "MAD"
        order = SimpleOrder.objects.create(
            product=product_instance,
            agent=order_agent,
            channel=channel,
            sku=sku or "",
            product_name=(product_name or (product_instance.name if product_instance else "") or ""),
            customer_name=customer_name or customer_phone,
            customer_phone=customer_phone,
            customer_city=customer_city or "",
            customer_country=kwargs.get("customer_country"),
            order_id=order_id,
            status="pending",
            created_at=timezone.now(),
            price=price_val,
            currency=_cur,
            quantity=qty_val,
            created_by_ai=True,
            created_by_bot_session=(bot_session_id or "")[:100] or None,
            sheets_export_status="pending",
        )
        logger.info("save_order_from_ai created order_id=%s for %s", order_id, customer_phone)
        # Stop logic: cancel pending follow-up tasks when customer places an order
        try:
            from discount.whatssapAPI.follow_up import cancel_pending_follow_up_tasks_for_customer
            cancel_pending_follow_up_tasks_for_customer(channel, customer_phone)
        except Exception as e:
            logger.warning("cancel_pending_follow_up_tasks_for_customer: %s", e)
        _notify_owner_order_created(channel, order)
        return order
    except Exception as e:
        logger.exception("save_order_from_ai failed: %s", e)
        return None


def _notify_owner_order_created(channel, order):
    """If channel has order_notify_method (EMAIL or WHATSAPP), send owner a notification. Runs after order is created."""
    method = getattr(channel, "order_notify_method", None) or ""
    if not method or method not in ("EMAIL", "WHATSAPP"):
        return
    try:
        if method == "EMAIL":
            to_email = (getattr(channel, "order_notify_email", None) or "").strip()
            if not to_email and getattr(channel, "owner", None):
                to_email = (getattr(channel.owner, "email", None) or "").strip()
            if not to_email:
                return
            from django.core.mail import send_mail
            from django.conf import settings
            subject = f"New order #{getattr(order, 'order_id', '')} from AI"
            body = (
                f"A new order was created by the AI sales agent.\n\n"
                f"Order ID: {getattr(order, 'order_id', '')}\n"
                f"Customer: {getattr(order, 'customer_name', '')} / {getattr(order, 'customer_phone', '')}\n"
                f"Address/City: {getattr(order, 'customer_city', '')}\n"
                f"Product: {getattr(order, 'product_name', '')}\n"
                f"Price: {getattr(order, 'price', '')} x {getattr(order, 'quantity', 1)}\n"
            )
            send_mail(
                subject=subject,
                message=body,
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@example.com"),
                recipient_list=[to_email],
                fail_silently=True,
            )
            logger.info("order notify email sent to %s for order_id=%s", to_email, getattr(order, "order_id", ""))
        elif method == "WHATSAPP":
            to_phone = (getattr(channel, "order_notify_whatsapp_phone", None) or "").strip()
            if not to_phone and getattr(channel, "owner", None):
                to_phone = (getattr(channel.owner, "phone", None) or "").strip()
            if not to_phone:
                return
            to_phone = "".join(c for c in to_phone if c.isdigit())
            if not to_phone or len(to_phone) < 10:
                return
            from discount.whatssapAPI.process_messages import send_automated_response
            msg = (
                f"🆕 New order from AI\n"
                f"Order ID: {getattr(order, 'order_id', '')}\n"
                f"Customer: {getattr(order, 'customer_name', '')} / {getattr(order, 'customer_phone', '')}\n"
                f"Address: {getattr(order, 'customer_city', '')}\n"
                f"Product: {getattr(order, 'product_name', '')}"
            )
            send_automated_response(to_phone, [{"type": "text", "content": msg}], channel=channel)
            logger.info("order notify WhatsApp sent to %s for order_id=%s", to_phone, getattr(order, "order_id", ""))
    except Exception as e:
        logger.exception("_notify_owner_order_created failed: %s", e)
