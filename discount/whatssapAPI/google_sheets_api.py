"""
Google Sheets integration HTTP API (stubs).

The full stack (global service account, ``GoogleSheetsConfig``, ``google_sheets_service``)
was in an older tree. These endpoints keep ``whatsapp_settings.html`` and ``{% url %}``
resolves working until that layer is restored.

Replace with real handlers from ``flow.api_google_sheets_*`` when the service is back.
"""
import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods, require_POST

# Mirrors the field list the UI expects for drag-and-drop mapping.
SHEETS_MAPPING_AVAILABLE_FIELDS = [
    "customer_name",
    "phone",
    "city",
    "address",
    "product_name",
    "price",
    "sku",
    "tracking_number",
    "status",
    "notes",
]


def _json_body(request):
    if not request.body:
        return {}
    try:
        return json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}


@csrf_exempt
@require_http_methods(["GET", "POST", "PUT"])
def api_google_sheets_config(request):
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=401)
    if request.method == "GET":
        return JsonResponse(
            {
                "spreadsheet_id": "",
                "sheet_name": "Orders",
                "column_mapping": {},
                "sheets_mapping": [],
                "available_fields": SHEETS_MAPPING_AVAILABLE_FIELDS,
                "configured": False,
                "service_account_email": "",
                "orders_exported_count": 0,
            }
        )
    data = _json_body(request)
    return JsonResponse(
        {
            "success": True,
            "spreadsheet_id": (data.get("spreadsheet_id") or "").strip(),
            "sheet_name": (data.get("sheet_name") or "Orders").strip() or "Orders",
            "column_mapping": data.get("column_mapping") if isinstance(data.get("column_mapping"), dict) else {},
            "sheets_mapping": data.get("sheets_mapping") if isinstance(data.get("sheets_mapping"), list) else [],
            "configured": False,
        }
    )


@csrf_exempt
@require_GET
def api_google_sheets_service_email(request):
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=401)
    return JsonResponse({"service_account_email": "", "configured": False})


@csrf_exempt
@require_POST
def api_google_sheets_test_connection(request):
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return JsonResponse({"success": False, "message": "Authentication required"}, status=401)
    return JsonResponse(
        {
            "success": False,
            "message": "Google Sheets backend is not configured. Add discount.services.google_sheets_service "
            "and wire these URLs to the full implementation when ready.",
        }
    )
