import json
import logging
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.core.exceptions import PermissionDenied

from discount.models import Message, WhatsAppChannel
from discount.services.security_check import verify_plan_access, FEATURE_AI_VOICE, FEATURE_AUTO_REPLY
from .services import generate_reply
from .models import AIUsageLog
from .copilot_service import run_copilot_chat

logger = logging.getLogger(__name__)

MAX_HISTORY_MESSAGES = 20
MAX_COPILOT_MESSAGES = 20


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

    # Hard-guard: verify plan allows AI/suggest before calling OpenAI
    store = getattr(channel, "owner", None)
    try:
        verify_plan_access(store, FEATURE_AUTO_REPLY)
    except PermissionDenied as e:
        return JsonResponse({"error": str(e)}, status=403)

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


@login_required
@require_POST
def ai_send_reply_as_voice(request):
    """
    POST /ai-assistant/api/send-as-voice/
    Body JSON: { channel_id, phone, text }

    Generates TTS from text using channel's voice settings and sends the audio
    to the contact via WhatsApp.
    """
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"success": False, "error": "Invalid JSON body."}, status=400)

    channel_id = body.get("channel_id")
    phone = (body.get("phone") or "").strip()
    text = (body.get("text") or "").strip()

    if not phone:
        return JsonResponse({"success": False, "error": "Phone number is required."}, status=400)
    if not channel_id:
        return JsonResponse({"success": False, "error": "Channel ID is required."}, status=400)
    if not text:
        return JsonResponse({"success": False, "error": "Text is required."}, status=400)

    user = request.user
    if user.is_superuser or getattr(user, "is_team_admin", False):
        channel_qs = WhatsAppChannel.objects.filter(owner=user)
    else:
        channel_qs = WhatsAppChannel.objects.filter(assigned_agents=user)

    channel = channel_qs.filter(id=channel_id).first()
    if not channel:
        return JsonResponse({"success": False, "error": "Channel not found or access denied."}, status=403)

    # Hard-guard: verify plan allows AI voice before calling TTS/WhatsApp
    store = getattr(channel, "owner", None)
    try:
        verify_plan_access(store, FEATURE_AI_VOICE)
    except PermissionDenied as e:
        return JsonResponse({"success": False, "error": str(e)}, status=403)

    try:
        from discount.whatssapAPI.voice_engine import generate_audio_file
        from discount.whatssapAPI.process_messages import send_whatsapp_audio_file
    except ImportError as e:
        logger.warning("Send-as-voice imports failed: %s", e)
        return JsonResponse({"success": False, "error": "Voice feature not available."}, status=502)

    audio_path = generate_audio_file(text, channel)
    if not audio_path:
        return JsonResponse({"success": False, "error": "Could not generate voice. Check TTS settings and API keys."}, status=502)

    try:
        result = send_whatsapp_audio_file(phone, audio_path, channel, user=user)
        if result and result.get("ok"):
            return JsonResponse({"success": True})
        return JsonResponse({"success": False, "error": result.get("error", "Failed to send audio.") or "Failed to send."}, status=502)
    except Exception as e:
        logger.exception("send_whatsapp_audio_file failed: %s", e)
        return JsonResponse({"success": False, "error": "Failed to send voice message."}, status=500)


def _user_channel_queryset(user):
    if user.is_superuser or getattr(user, "is_team_admin", False):
        return WhatsAppChannel.objects.filter(owner=user)
    return WhatsAppChannel.objects.filter(assigned_agents=user)


@login_required
@require_POST
def copilot_chat(request):
    """
    POST /ai-assistant/api/copilot-chat/

    Body JSON:
      {
        "channel_id": 123,                         // optional but recommended (auth scope)
        "prompt": "Show today's sales",          // optional if messages provided
        "messages": [{"role":"user","content":"..."}]  // optional chat history
      }

    Returns structured payload for dashboard UI blocks:
      { "success": true, "message", "ui_component", "component_data" }
    """
    try:
        body = json.loads(request.body or b"{}")
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"success": False, "error": "Invalid JSON body."}, status=400)

    channel_id = body.get("channel_id")
    prompt = (body.get("prompt") or "").strip()
    messages = body.get("messages")

    if messages is not None and not isinstance(messages, list):
        return JsonResponse({"success": False, "error": "messages must be a list."}, status=400)

    chat_messages = []
    if isinstance(messages, list) and messages:
        for m in messages:
            role = (m.get("role") or "").strip().lower()
            content = m.get("content")
            if role in ("user", "assistant") and content is not None:
                chat_messages.append({"role": role, "content": str(content)[:8000]})
        chat_messages = chat_messages[-MAX_COPILOT_MESSAGES:]

    if prompt:
        if chat_messages and chat_messages[-1].get("role") == "user":
            chat_messages[-1]["content"] = prompt
        else:
            chat_messages.append({"role": "user", "content": prompt[:8000]})

    if not chat_messages or chat_messages[-1].get("role") != "user":
        return JsonResponse(
            {"success": False, "error": "Provide a user prompt or messages ending with a user turn."},
            status=400,
        )

    extra_context = None
    if channel_id is not None:
        try:
            channel_id = int(channel_id)
        except (TypeError, ValueError):
            return JsonResponse({"success": False, "error": "Invalid channel_id."}, status=400)

        channel = _user_channel_queryset(request.user).filter(id=channel_id).first()
        if not channel:
            return JsonResponse({"success": False, "error": "Channel not found or access denied."}, status=403)
        if hasattr(channel, "has_user_permission") and not channel.has_user_permission(request.user):
            return JsonResponse({"success": False, "error": "Forbidden."}, status=403)

        store = getattr(channel, "owner", None)
        try:
            verify_plan_access(store, FEATURE_AUTO_REPLY)
        except PermissionDenied as e:
            return JsonResponse({"success": False, "error": str(e)}, status=403)

        extra_context = f"Channel name: {getattr(channel, 'name', channel_id)}"

    try:
        payload = run_copilot_chat(
            chat_messages,
            channel_id=channel_id,
            extra_context=extra_context,
        )
    except ValueError as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)
    except RuntimeError as e:
        return JsonResponse({"success": False, "error": str(e)}, status=502)

    # Optional persistence (same model as legacy coach-ai)
    if channel_id is not None:
        try:
            from discount.models import CoachConversation, CoachConversationMessage

            channel = WhatsAppChannel.objects.get(pk=channel_id)
            conversation_id = body.get("conversation_id")
            conversation = None
            if conversation_id:
                try:
                    conversation = CoachConversation.objects.select_related("channel").get(pk=conversation_id)
                except (CoachConversation.DoesNotExist, ValueError, TypeError):
                    conversation = None
                if (
                    conversation is None
                    or conversation.user_id != request.user.id
                    or conversation.channel_id != channel.id
                ):
                    conversation = None
            if conversation is None:
                conversation = CoachConversation.objects.create(
                    channel=channel,
                    user=request.user,
                    title="New chat",
                )
            last_user = next((m for m in reversed(chat_messages) if m.get("role") == "user"), None)
            if last_user and (last_user.get("content") or "").strip():
                user_content = (last_user.get("content") or "").strip()[:10000]
                CoachConversationMessage.objects.create(
                    conversation=conversation,
                    channel=channel,
                    user=request.user,
                    role="user",
                    content=user_content,
                )
                CoachConversationMessage.objects.create(
                    conversation=conversation,
                    channel=channel,
                    user=request.user,
                    role="assistant",
                    content=(payload.get("message") or "").strip()[:10000],
                )
                title = conversation.title
                if not (title or "").strip() or title.strip().lower() == "new chat":
                    conversation.title = user_content[:200]
                conversation.updated_at = timezone.now()
                conversation.save(update_fields=["title", "updated_at"])
        except Exception as e:
            logger.warning("copilot_chat: save conversation failed: %s", e)

    return JsonResponse({"success": True, **payload})
