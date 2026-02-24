"""
Google Sheets export service: authenticate with Service Account, append rows using column mapping.
Credentials are read from the environment variable GOOGLE_SHEETS_CREDENTIALS_JSON (JSON string).
Uses gspread.service_account_from_dict() to authenticate. Falls back to per-user encrypted JSON.
All values (especially phone) are written as strings to preserve leading zeros.
"""
import json
import logging
import os
import threading
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# File logger for every sync attempt (logs/google_sheets.log)
_google_sheets_file_logger = None


def _get_sheets_file_logger():
    global _google_sheets_file_logger
    if _google_sheets_file_logger is not None:
        return _google_sheets_file_logger
    try:
        log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs")
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "google_sheets.log")
        file_logger = logging.getLogger("discount.google_sheets.file")
        if not file_logger.handlers:
            handler = logging.FileHandler(log_file, encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
            file_logger.addHandler(handler)
            file_logger.setLevel(logging.INFO)
        _google_sheets_file_logger = file_logger
        return file_logger
    except Exception as e:
        logger.warning("Could not create google_sheets file logger: %s", e)
        return None

try:
    import gspread
    GSPREAD_AVAILABLE = True
except ImportError:
    GSPREAD_AVAILABLE = False
    gspread = None


# Permission-denied / 403 friendly message
PERMISSION_DENIED_MESSAGE = (
    "Please make sure you have shared the sheet with our email address (as Editor)."
)


def _normalize_credentials_dict(info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ensure private_key has real newlines. When JSON is stored in an env var,
    the key is often pasted with literal \\n; Google expects actual newlines.
    """
    if not isinstance(info, dict):
        return info
    key = info.get("private_key")
    if isinstance(key, str) and "\\n" in key:
        info = {**info, "private_key": key.replace("\\n", "\n")}
    return info


def _get_global_credentials_dict() -> Optional[Dict[str, Any]]:
    """
    Get credentials as a Python dict from the environment variable string.
    Prefers Django settings (so settings can load from file); falls back to os.getenv.
    Uses json.loads() and normalizes private_key. Never expose the result to the frontend.
    """
    raw = ""
    try:
        from django.conf import settings
        raw = (getattr(settings, "GOOGLE_SHEETS_CREDENTIALS_JSON", None) or "").strip()
    except Exception:
        pass
    if not raw:
        raw = os.getenv("GOOGLE_SHEETS_CREDENTIALS_JSON", "").strip()
    if not raw:
        return None
    try:
        credentials_dict = json.loads(raw)
        if not isinstance(credentials_dict, dict):
            return None
        return _normalize_credentials_dict(credentials_dict)
    except json.JSONDecodeError as e:
        logger.exception("Invalid GOOGLE_SHEETS_CREDENTIALS_JSON: %s", e)
        return None


def get_global_client() -> Optional[Any]:
    """
    Authenticate using the global credentials string from the environment.
    Returns a gspread Client from service_account_from_dict(credentials_dict), or None.
    """
    if not GSPREAD_AVAILABLE:
        return None
    credentials_dict = _get_global_credentials_dict()
    if not credentials_dict:
        return None
    try:
        return gspread.service_account_from_dict(credentials_dict)
    except Exception as e:
        logger.exception("Failed to build global gspread client: %s", e)
        return None


def get_global_service_account_email() -> Optional[str]:
    """
    Return the Service Account client_email for display (copy in UI).
    Uses: credentials JSON dict, or Django setting GOOGLE_SHEETS_SERVICE_ACCOUNT_EMAIL as fallback.
    """
    d = _get_global_credentials_dict()
    if d:
        email = (d.get("client_email") or "").strip()
        if email:
            return email
    try:
        from django.conf import settings
        email = (getattr(settings, "GOOGLE_SHEETS_SERVICE_ACCOUNT_EMAIL", None) or "").strip()
        if email:
            return email
    except Exception:
        pass
    return None


def _get_client_from_config(config) -> Optional[Any]:
    """
    Build gspread Client from GoogleSheetsConfig (per-user encrypted JSON).
    Used only when global credentials are not set (backward compatibility).
    """
    if not GSPREAD_AVAILABLE:
        return None
    encrypted = getattr(config, "service_account_json_encrypted", None)
    if not encrypted:
        return None
    try:
        from discount.crypto import decrypt_token
        raw = decrypt_token(encrypted)
        info = json.loads(raw)
        if not isinstance(info, dict):
            return None
        info = _normalize_credentials_dict(info)
        return gspread.service_account_from_dict(info)
    except Exception as e:
        logger.exception("Failed to build client from config: %s", e)
        return None


def get_client_for_config(config) -> Optional[Any]:
    """
    Prefer Global Service Account client; fall back to per-user config.
    Use this for all auth in this module. Returns a gspread Client or None.
    """
    client = get_global_client()
    if client:
        return client
    return _get_client_from_config(config)


def _ensure_string(value: Any) -> str:
    """Format value as string for Sheets; prevents losing leading zeros (e.g. Moroccan phone)."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


# Available database fields for drag-and-drop mapping (order/SimpleOrder keys)
SHEETS_MAPPING_AVAILABLE_FIELDS = [
    {"field": "customer_name", "label": "Customer Name"},
    {"field": "customer_phone", "label": "Phone"},
    {"field": "phone", "label": "Phone (alt)"},
    {"field": "customer_city", "label": "City / Address"},
    {"field": "city", "label": "City"},
    {"field": "address", "label": "Address"},
    {"field": "order_id", "label": "Order ID"},
    {"field": "product_name", "label": "Product Name"},
    {"field": "price", "label": "Price"},
    {"field": "quantity", "label": "Quantity"},
    {"field": "created_at", "label": "Created At"},
    {"field": "sku", "label": "SKU"},
    {"field": "customer_country", "label": "Country"},
]


def transform_order_for_sheet(order: Any, mapping: list) -> list:
    """
    Build a list of cell values for one row from an order and a sheets_mapping list.
    order: dict (e.g. from _order_to_sheets_data) or object with getattr.
    mapping: list of {"field": "customer_name", "header": "Customer Name"}. Order = column order.
    Returns list of strings (one per column).
    """
    if not mapping or not isinstance(mapping, list):
        return []
    if isinstance(order, dict):
        def get_val(key):
            return order.get(key) if key else ""
    else:
        def get_val(key):
            return getattr(order, key, None) if key else None
    row = []
    for item in mapping:
        if not isinstance(item, dict):
            row.append("")
            continue
        field = (item.get("field") or "").strip()
        val = get_val(field)
        row.append(_ensure_string(val))
    return row


def test_connection(config) -> Tuple[bool, str]:
    """
    Test if the system can access the given Google Sheet.
    Uses Global Service Account (or per-user credentials) and config.spreadsheet_id.

    Returns:
        (success: bool, message: str)
    """
    if not GSPREAD_AVAILABLE:
        return False, "gspread or google-auth not installed"
    client = get_client_for_config(config)
    if not client:
        if get_global_client():
            return False, "Spreadsheet ID is required"
        return False, "Google Sheets is not configured. Set GOOGLE_SHEETS_CREDENTIALS_JSON or add your own credentials."
    spreadsheet_id = (getattr(config, "spreadsheet_id", None) or "").strip()
    if not spreadsheet_id:
        return False, "Spreadsheet ID is required"
    try:
        client.open_by_key(spreadsheet_id)
        return True, "Connection successful"
    except gspread.exceptions.APIError as e:
        msg = str(e)
        if hasattr(e, "response") and e.response is not None:
            try:
                body = e.response.json()
                msg = (body.get("error") or {}).get("message", msg)
                if e.response.status_code == 403 or "permission" in msg.lower() or "forbidden" in msg.lower():
                    return False, PERMISSION_DENIED_MESSAGE
            except Exception:
                pass
        logger.warning("Google Sheets API error (test connection): %s", msg)
        return False, msg or PERMISSION_DENIED_MESSAGE
    except Exception as e:
        logger.exception("test_connection failed: %s", e)
        return False, str(e)


def export_to_google_sheets(
    user_id: int,
    order_data: Dict[str, Any],
    config,
    order_instance=None,
) -> Tuple[bool, str]:
    """
    Append one row to the configured Google Sheet using column_mapping.
    order_data keys (e.g. customer_name, phone, city) are mapped to columns (A, B, C...).
    All values are written as strings to preserve leading zeros in phone numbers.

    If order_instance is provided and export fails, its sheets_export_status is set to 'failed'.

    Returns:
        (success: bool, message: str)
    """
    def _set_failed(inst, err_msg):
        if not inst:
            return
        try:
            inst.sheets_export_status = "failed"
            if hasattr(inst, "sheets_export_error"):
                inst.sheets_export_error = (err_msg or "")[:500]
            inst.save(update_fields=["sheets_export_status", "sheets_export_error"] if hasattr(inst, "sheets_export_error") else ["sheets_export_status"])
        except Exception:
            pass

    if not GSPREAD_AVAILABLE:
        msg = "gspread or google-auth not installed"
        _set_failed(order_instance, msg)
        return False, msg

    client = get_client_for_config(config)
    if not client:
        msg = "Invalid or missing Service Account credentials (set GOOGLE_SHEETS_CREDENTIALS_JSON or add credentials in settings)"
        _set_failed(order_instance, msg)
        return False, msg

    spreadsheet_id = (getattr(config, "spreadsheet_id", None) or "").strip()
    sheet_name = (getattr(config, "sheet_name", None) or "Orders").strip()
    sheets_mapping = getattr(config, "sheets_mapping", None)
    column_mapping = getattr(config, "column_mapping", None) or {}

    if not spreadsheet_id:
        msg = "Spreadsheet ID is required"
        _set_failed(order_instance, msg)
        return False, msg

    # Build row: prefer sheets_mapping (drag-and-drop) over column_mapping
    if sheets_mapping and isinstance(sheets_mapping, list) and len(sheets_mapping) > 0:
        row_values = transform_order_for_sheet(order_data, sheets_mapping)
    else:
        col_letters = sorted(column_mapping.keys(), key=lambda c: (len(c), c))
        row_values = []
        for col in col_letters:
            var_key = column_mapping.get(col)
            value = order_data.get(var_key) if var_key else ""
            row_values.append(_ensure_string(value))

    if not row_values:
        logger.warning("export_to_google_sheets: column_mapping empty or no matching keys in order_data")
        _set_failed(order_instance, "No column mapping or no data to export")
        return False, "No column mapping or no data to export"

    try:
        spreadsheet = client.open_by_key(spreadsheet_id)
        worksheet = spreadsheet.worksheet(sheet_name)
        # Ensure each new order goes on the next row: first order at row 1, second at row 2, etc.
        all_rows = worksheet.get_all_values()
        next_row = len(all_rows) + 1
        start_cell = f"A{next_row}"
        worksheet.update(start_cell, [row_values], value_input_option="USER_ENTERED")
        if order_instance:
            try:
                order_instance.sheets_export_status = "success"
                if hasattr(order_instance, "sheets_export_error"):
                    order_instance.sheets_export_error = None
                order_instance.save(update_fields=["sheets_export_status", "sheets_export_error"] if hasattr(order_instance, "sheets_export_error") else ["sheets_export_status"])
            except Exception:
                pass
        return True, "Row appended successfully"
    except gspread.exceptions.APIError as e:
        msg = "Sheet not accessible or invalid"
        if hasattr(e, "response") and e.response is not None:
            try:
                err_body = e.response.json()
                msg = err_body.get("error", {}).get("message", msg)
                if e.response.status_code == 403 or "permission" in msg.lower() or "forbidden" in msg.lower():
                    msg = PERMISSION_DENIED_MESSAGE
            except Exception:
                pass
        logger.warning("Google Sheets API error (export): %s", msg)
        _set_failed(order_instance, msg)
        return False, msg
    except Exception as e:
        logger.exception("export_to_google_sheets failed: %s", e)
        _set_failed(order_instance, str(e))
        return False, str(e)


def _order_to_sheets_data(order) -> Dict[str, Any]:
    """Build order_data dict for export from SimpleOrder. Keys match column_mapping (name, city, address, created_at, etc.)."""
    from django.utils.dateformat import format as date_format
    created_str = ""
    if getattr(order, "created_at", None):
        try:
            created_str = order.created_at.strftime("%Y-%m-%d %H:%M")
        except Exception:
            created_str = str(order.created_at)
    return {
        "customer_name": getattr(order, "customer_name", None) or "",
        "name": getattr(order, "customer_name", None) or "",
        "phone": getattr(order, "customer_phone", None) or "",
        "customer_phone": getattr(order, "customer_phone", None) or "",
        "city": getattr(order, "customer_city", None) or "",
        "customer_city": getattr(order, "customer_city", None) or "",
        "address": getattr(order, "customer_city", None) or "",
        "created_at": created_str,
        "order_id": getattr(order, "order_id", None) or "",
        "product_name": getattr(order, "product_name", None) or "",
        "price": getattr(order, "price", None) is not None and str(order.price) or "",
        "quantity": getattr(order, "quantity", None) is not None and str(order.quantity) or "",
    }


def sync_order_to_google_sheets(order_id: int) -> Tuple[bool, str]:
    """
    Fetch order (SimpleOrder), get merchant GoogleSheetsConfig, append row to sheet.
    Updates order.sheets_export_status ('success' / 'failed') and order.sheets_export_error on failure.
    On Permission Denied (403), sets user-friendly message telling them to re-check Share with service account email.
    Returns (success, message).
    """
    file_log = _get_sheets_file_logger()
    if file_log:
        file_log.info("sync_order_to_google_sheets attempt order_id=%s", order_id)

    try:
        from discount.models import SimpleOrder, GoogleSheetsConfig
    except ImportError as e:
        msg = "Cannot import discount models: %s" % e
        logger.exception(msg)
        if file_log:
            file_log.error("%s", msg)
        return False, msg

    try:
        order = SimpleOrder.objects.select_related("channel", "channel__owner").get(pk=order_id)
    except SimpleOrder.DoesNotExist:
        msg = "Order %s not found" % order_id
        logger.warning(msg)
        if file_log:
            file_log.warning("%s", msg)
        return False, msg

    if not order.channel or not order.channel.owner_id:
        msg = "Order has no channel or owner"
        if file_log:
            file_log.warning("order_id=%s: %s", order_id, msg)
        return False, msg

    if getattr(order, "sheets_export_status", None) == "success":
        if file_log:
            file_log.info("order_id=%s already exported, skip", order_id)
        return True, "Already exported"

    config = GoogleSheetsConfig.objects.filter(user_id=order.channel.owner_id).first()
    if not config or not (getattr(config, "spreadsheet_id", None) or "").strip():
        msg = "No Google Sheets config or spreadsheet_id for this merchant"
        try:
            order.sheets_export_status = "failed"
            order.sheets_export_error = msg
            order.save(update_fields=["sheets_export_status", "sheets_export_error"])
        except Exception:
            pass
        if file_log:
            file_log.warning("order_id=%s: %s", order_id, msg)
        return False, msg

    order_data = _order_to_sheets_data(order)
    success, message = export_to_google_sheets(
        user_id=order.channel.owner_id,
        order_data=order_data,
        config=config,
        order_instance=order,
    )

    if not success:
        err_msg = message
        if err_msg and ("permission" in err_msg.lower() or "403" in err_msg or "forbidden" in err_msg.lower()):
            err_msg = PERMISSION_DENIED_MESSAGE
        try:
            order.sheets_export_status = "failed"
            order.sheets_export_error = (err_msg or message)[:500]
            order.save(update_fields=["sheets_export_status", "sheets_export_error"])
        except Exception as e:
            logger.warning("Could not save sheets_export_error: %s", e)
        if file_log:
            file_log.error("order_id=%s sync failed: %s", order_id, err_msg or message)
        return False, err_msg or message

    try:
        order.sheets_export_error = None
        order.save(update_fields=["sheets_export_error"])
    except Exception:
        pass
    if file_log:
        file_log.info("order_id=%s sync success", order_id)
    return True, message
