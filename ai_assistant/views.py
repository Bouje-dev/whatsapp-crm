import json
import logging
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required

from discount.models import Message, WhatsAppChannel
from .services import generate_reply
from .models import AIUsageLog

logger = logging.getLogger(__name__)

MAX_HISTORY_MESSAGES = 20


@login_required
@require_POST
def ai_suggest_reply(request):
    """
    POST /ai-assistant/api/suggest/
    Body JSON: { channel_id, phone, instruction? }

    Reads the last N messages for this contact on this channel,
    sends them to OpenAI, and returns a suggested reply.
    """
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON body."}, status=400)

    channel_id = body.get("channel_id")
    phone = body.get("phone", "").strip()
    instruction = body.get("instruction", "").strip() or None

    if not phone:
        return JsonResponse({"error": "Phone number is required."}, status=400)
    if not channel_id:
        return JsonResponse({"error": "Channel ID is required."}, status=400)

    # Verify the user has access to this channel
    user = request.user
    if user.is_superuser or getattr(user, "is_team_admin", False):
        channel_qs = WhatsAppChannel.objects.filter(owner=user)
    else:
        channel_qs = WhatsAppChannel.objects.filter(assigned_agents=user)

    channel = channel_qs.filter(id=channel_id).first()
    if not channel:
        return JsonResponse({"error": "Channel not found or access denied."}, status=403)

    # Fetch recent messages for this conversation
    recent_msgs = (
        Message.objects.filter(channel=channel, sender=phone)
        .order_by("-id")[:MAX_HISTORY_MESSAGES]
    )
    recent_msgs = list(recent_msgs)
    recent_msgs.reverse()

    if not recent_msgs:
        return JsonResponse(
            {"error": "No conversation history found for this contact."},
            status=404,
        )

    # Build conversation for OpenAI
    conversation = []
    for msg in recent_msgs:
        if msg.is_internal:
            continue
        role = "agent" if msg.is_from_me else "customer"
        text = msg.body or ""
        if not text and msg.media_type:
            text = f"[{msg.media_type}]"
        if text:
            conversation.append({"role": role, "body": text})

    if not conversation:
        return JsonResponse(
            {"error": "No text messages found in conversation history."},
            status=404,
        )

    # Call OpenAI
    try:
        result = generate_reply(conversation, custom_instruction=instruction)
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=400)
    except RuntimeError as e:
        return JsonResponse({"error": str(e)}, status=502)

    # Log usage (non-blocking)
    try:
        AIUsageLog.objects.create(
            user=user,
            channel_id=channel_id,
            contact_phone=phone,
            prompt_tokens=result["prompt_tokens"],
            completion_tokens=result["completion_tokens"],
            model_used=result["model"],
        )
    except Exception as e:
        logger.warning("Failed to log AI usage: %s", e)

    return JsonResponse({
        "reply": result["reply"],
        "tokens_used": result["prompt_tokens"] + result["completion_tokens"],
    })
