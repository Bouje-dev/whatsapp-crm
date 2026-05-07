"""
Stripe / wallet HTTP API (stubs).

``templates/user/user.html`` (restored from older commits) and WhatsApp settings
call these routes. Full implementations lived on ``views.create_*`` with Stripe;
restore from history when keys and webhooks are configured.
"""
import json

from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods, require_POST


def _json_body(request):
    if not request.body:
        return {}
    try:
        return json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}


def _require_user(request):
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return JsonResponse({"success": False, "error": "Authentication required"}, status=401)
    return None


@csrf_exempt
@require_POST
def create_portal_session(request):
    err = _require_user(request)
    if err:
        return err
    try:
        json.loads(request.body.decode("utf-8") or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        pass
    return JsonResponse(
        {
            "error": "Billing portal is not configured. Add Stripe integration to enable customer portal links.",
        }
    )


@require_GET
def wallet_summary(request):
    err = _require_user(request)
    if err:
        return err
    return JsonResponse(
        {
            "success": True,
            "walletBalance": 0.0,
            "totalTokensUsed": 0,
            "lowBalanceAlertEnabled": True,
        }
    )


@require_POST
def wallet_settings(request):
    err = _require_user(request)
    if err:
        return err
    data = _json_body(request)
    enabled = data.get("lowBalanceAlertEnabled")
    if enabled is None:
        enabled = True
    return JsonResponse(
        {
            "success": True,
            "lowBalanceAlertEnabled": bool(enabled),
        }
    )


@require_POST
def wallet_topup(request):
    err = _require_user(request)
    if err:
        return err
    return JsonResponse(
        {
            "error": "Wallet top-up is not configured. Add Stripe checkout for wallet credits.",
        },
        status=503,
    )


@csrf_exempt
@require_POST
def stripe_webhook(request):
    # Real handler verifies ``Stripe-Signature``; accept POST so Stripe CLI / dashboard tests get 200.
    return HttpResponse(status=200)
