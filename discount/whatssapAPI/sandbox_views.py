"""Local AI sandbox — talk to the same WhatsApp inbound pipeline without Meta."""
from __future__ import annotations

import json
import logging
import traceback

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from discount.services.context_integration import get_conversation_state_debug
from discount.services.sandbox import (
    SANDBOX_CONTACT_NAME,
    build_inbound_message,
    can_access_sandbox,
    list_sandbox_channels,
    reset_sandbox_identity,
    resolve_sandbox_channel,
    sandbox_phone_for,
    serialize_sandbox_message,
)

logger = logging.getLogger(__name__)

LOGIN_URL = "/auth/login/"


def _forbid_if_needed(request):
    if not can_access_sandbox(request.user):
        return HttpResponseForbidden(
            "Sandbox is only available in DEBUG, or to a superuser."
        )
    return None


def _json_body(request) -> dict:
    if request.content_type and "application/json" in request.content_type:
        try:
            data = json.loads(request.body.decode("utf-8") or "{}")
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    return request.POST.dict() if request.POST else {}


def _channel_payload(channel, user):
    phone = sandbox_phone_for(user, channel) if channel else ""
    return {
        "id": channel.id if channel else None,
        "name": getattr(channel, "name", "") if channel else "",
        "phone_number": getattr(channel, "phone_number", "") if channel else "",
        "ai_auto_reply": bool(getattr(channel, "ai_auto_reply", False)) if channel else False,
        "sandbox_phone": phone,
    }


@login_required(login_url=LOGIN_URL)
def sandbox_lab_page(request):
    denied = _forbid_if_needed(request)
    if denied:
        return denied
    channels = list(_channel_payload(ch, request.user) for ch in list_sandbox_channels(request.user))
    requested = request.GET.get("channel_id")
    selected = resolve_sandbox_channel(request.user, requested)
    return render(
        request,
        "whatssap/sandbox_lab.html",
        {
            "channels": channels,
            "selected_channel": _channel_payload(selected, request.user) if selected else None,
        },
    )


@login_required(login_url=LOGIN_URL)
@require_GET
def sandbox_bootstrap(request):
    denied = _forbid_if_needed(request)
    if denied:
        return JsonResponse({"error": "Forbidden"}, status=403)
    channels = list(_channel_payload(ch, request.user) for ch in list_sandbox_channels(request.user))
    selected = resolve_sandbox_channel(request.user, request.GET.get("channel_id"))
    return JsonResponse(
        {
            "ok": True,
            "channels": channels,
            "channel": _channel_payload(selected, request.user) if selected else None,
        }
    )


def _messages_qs(channel, phone):
    from discount.models import Message

    return Message.objects.filter(channel=channel, sender=phone).order_by("timestamp", "id")


@login_required(login_url=LOGIN_URL)
@require_GET
def sandbox_messages(request):
    denied = _forbid_if_needed(request)
    if denied:
        return JsonResponse({"error": "Forbidden"}, status=403)
    channel = resolve_sandbox_channel(request.user, request.GET.get("channel_id"))
    if not channel:
        return JsonResponse({"error": "No channel"}, status=404)
    phone = sandbox_phone_for(request.user, channel)
    since_id = request.GET.get("since_id")
    qs = _messages_qs(channel, phone)
    if since_id:
        try:
            qs = qs.filter(id__gt=int(since_id))
        except (TypeError, ValueError):
            pass
    rows = [serialize_sandbox_message(m) for m in qs[:400]]
    return JsonResponse({"ok": True, "phone": phone, "messages": rows})


@login_required(login_url=LOGIN_URL)
@require_GET
def sandbox_state(request):
    denied = _forbid_if_needed(request)
    if denied:
        return JsonResponse({"error": "Forbidden"}, status=403)
    channel = resolve_sandbox_channel(request.user, request.GET.get("channel_id"))
    if not channel:
        return JsonResponse({"error": "No channel"}, status=404)
    phone = sandbox_phone_for(request.user, channel)
    from discount.models import SimpleOrder

    debug = get_conversation_state_debug(channel.id, phone)
    orders = list(
        SimpleOrder.objects.filter(channel=channel, customer_phone=phone)
        .order_by("-created_at")
        .values("id", "order_id", "status", "product_name", "price", "created_at")[:8]
    )
    for row in orders:
        created = row.get("created_at")
        if created:
            row["created_at"] = created.isoformat()
        if row.get("price") is not None:
            row["price"] = str(row["price"])
    debug["orders"] = orders
    debug["ai_auto_reply"] = bool(getattr(channel, "ai_auto_reply", False))
    debug["sandbox_phone"] = phone
    debug["channel_name"] = channel.name
    return JsonResponse({"ok": True, "state": debug})


@login_required(login_url=LOGIN_URL)
@require_POST
def sandbox_send(request):
    denied = _forbid_if_needed(request)
    if denied:
        return JsonResponse({"error": "Forbidden"}, status=403)
    payload = _json_body(request)
    channel = resolve_sandbox_channel(request.user, payload.get("channel_id"))
    if not channel:
        return JsonResponse({"error": "No channel"}, status=404)

    phone = sandbox_phone_for(request.user, channel)
    text = (payload.get("text") or "").strip()
    msg_type = (payload.get("type") or "text").strip().lower()
    flow_answers = payload.get("flow_answers") if isinstance(payload.get("flow_answers"), dict) else None
    if msg_type not in ("text", "interactive", "button", "nfm_reply", "flow_reply"):
        msg_type = "text"
    if flow_answers is not None:
        msg_type = "nfm_reply"
    if msg_type == "text" and not text:
        return JsonResponse({"error": "Empty message"}, status=400)

    inbound = build_inbound_message(
        phone,
        text,
        msg_type=msg_type,
        button_id=str(payload.get("button_id") or ""),
        button_title=str(payload.get("button_title") or ""),
        list_id=str(payload.get("list_id") or ""),
        list_title=str(payload.get("list_title") or ""),
        list_description=str(payload.get("list_description") or ""),
        flow_token=str(payload.get("flow_token") or ""),
        flow_answers=flow_answers,
    )

    from discount.models import Message

    before_id = (
        Message.objects.filter(channel=channel, sender=phone)
        .order_by("-id")
        .values_list("id", flat=True)
        .first()
        or 0
    )

    error_text = ""
    try:
        import time as _time

        from discount.whatssapAPI.process_messages import (
            DEBOUNCE_WINDOW_SECONDS,
            is_debounce_pending,
            process_messages,
            wait_until_debounce_idle,
        )

        process_messages(
            [inbound],
            channel=channel,
            name=SANDBOX_CONTACT_NAME,
            # Same debounce as production WhatsApp webhooks (burst → one AI turn).
            # _skip_debounce=False,
                        _skip_debounce=True,

        )

        # Text path buffers then flushes on a timer thread — wait for quiet + LLM.
        if is_debounce_pending(channel, phone):
            wait_until_debounce_idle(
                channel,
                phone,
                timeout=DEBOUNCE_WINDOW_SECONDS + 4.0,
            )
            _deadline = _time.time() + 90.0
            while _time.time() < _deadline:
                if Message.objects.filter(
                    channel=channel,
                    sender=phone,
                    id__gt=before_id,
                    is_from_me=True,
                ).exists():
                    break
                _time.sleep(0.35)
    except Exception as exc:
        logger.exception("sandbox process_messages failed")
        error_text = f"{exc}\n{traceback.format_exc()}"

    new_rows = list(
        Message.objects.filter(channel=channel, sender=phone, id__gt=before_id).order_by(
            "timestamp", "id"
        )
    )
    state = get_conversation_state_debug(channel.id, phone)
    state["ai_auto_reply"] = bool(getattr(channel, "ai_auto_reply", False))
    return JsonResponse(
        {
            "ok": not error_text,
            "error": error_text,
            "phone": phone,
            "ai_auto_reply": bool(getattr(channel, "ai_auto_reply", False)),
            "messages": [serialize_sandbox_message(m) for m in new_rows],
            "state": state,
        }
    )


@login_required(login_url=LOGIN_URL)
@require_POST
def sandbox_reset(request):
    denied = _forbid_if_needed(request)
    if denied:
        return JsonResponse({"error": "Forbidden"}, status=403)
    payload = _json_body(request)
    channel = resolve_sandbox_channel(request.user, payload.get("channel_id"))
    if not channel:
        return JsonResponse({"error": "No channel"}, status=404)
    phone = sandbox_phone_for(request.user, channel)
    mode = (payload.get("mode") or "customer").strip().lower()
    wipe_orders = bool(payload.get("wipe_orders"))
    wipe_messages = mode != "memory"
    result = reset_sandbox_identity(
        channel,
        phone,
        wipe_messages=wipe_messages,
        wipe_orders=wipe_orders or mode == "all",
    )
    state = get_conversation_state_debug(channel.id, phone)
    state["ai_auto_reply"] = bool(getattr(channel, "ai_auto_reply", False))
    return JsonResponse(
        {
            "ok": bool(result.get("ok")),
            "deleted": result.get("deleted") or {},
            "phone": phone,
            "state": state,
            "messages": [] if wipe_messages else [
                serialize_sandbox_message(m) for m in _messages_qs(channel, phone)[:400]
            ],
        }
    )
