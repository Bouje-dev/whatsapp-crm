"""
Smart Follow-up Node: task creation, cancellation, and send logic.
- Cancel PENDING tasks when customer replies or places an order.
- Create task when flow reaches a follow-up node.
- Quiet hours: 23:00–08:00 → reschedule to next 08:00.
"""
import logging
from datetime import timedelta

from django.utils import timezone

from discount.models import FollowUpTask, FollowUpNode

logger = logging.getLogger(__name__)

# Quiet hours: no follow-up sent between 23:00 and 08:00 (local or server time)
QUIET_HOUR_START = 23  # 11 PM
QUIET_HOUR_END = 8     # 8 AM


def cancel_pending_follow_up_tasks(channel, customer_phone):
    """
    Cancel all PENDING follow-up tasks for this channel + customer_phone.
    Call when the customer sends a new message or places an order.
    """
    if not channel or not customer_phone:
        return
    try:
        qs = FollowUpTask.objects.filter(
            channel=channel,
            customer_phone=str(customer_phone).strip(),
            status=FollowUpTask.STATUS_PENDING,
        )
        updated = qs.update(
            status=FollowUpTask.STATUS_CANCELLED,
            is_cancelled=True,
        )
        if updated:
            logger.info("Cancelled %s PENDING follow-up task(s) for %s", updated, customer_phone)
    except Exception as e:
        logger.exception("cancel_pending_follow_up_tasks: %s", e)


# Alias for process_messages import
cancel_pending_follow_up_tasks_for_customer = cancel_pending_follow_up_tasks


def _next_allowed_send_time(now=None):
    """Return next datetime after now when we are allowed to send (outside quiet hours)."""
    now = now or timezone.now()
    hour = now.hour
    if QUIET_HOUR_END <= hour < QUIET_HOUR_START:
        return now  # already in allowed window
    # In quiet period: move to next 08:00
    from datetime import datetime
    today = now.date()
    next_morning = timezone.make_aware(
        datetime(today.year, today.month, today.day, QUIET_HOUR_END, 0, 0),
        timezone.get_current_timezone(),
    )
    if now >= next_morning:
        next_morning = next_morning + timedelta(days=1)
    return next_morning


def schedule_follow_up_time(scheduled_at):
    """
    If scheduled_at falls in quiet hours (23:00–08:00), return next 08:00.
    Otherwise return scheduled_at.
    """
    hour = scheduled_at.hour
    if QUIET_HOUR_END <= hour < QUIET_HOUR_START:
        return scheduled_at
    return _next_allowed_send_time(scheduled_at)


def create_follow_up_task(node, channel, customer_phone):
    """
    Create a FollowUpTask for the given follow-up node. Uses FollowUpNode config
    for delay_hours; applies quiet hours to scheduled_at.
    Returns the created FollowUpTask or None.
    """
    if not node or not channel or not customer_phone:
        return None
    try:
        config = getattr(node, "follow_up_config", None)
        if not config:
            # Node might not have follow_up_config yet (e.g. old flow); try to get or create
            config = _get_or_create_follow_up_config(node)
        if not config:
            logger.warning("Follow-up node %s has no config", node.id)
            return None
        delay_hours = getattr(config, "delay_hours", 6) or 6
        scheduled_at = timezone.now() + timedelta(hours=delay_hours)
        scheduled_at = schedule_follow_up_time(scheduled_at)
        task = FollowUpTask.objects.create(
            channel=channel,
            node=node,
            customer_phone=str(customer_phone).strip(),
            scheduled_at=scheduled_at,
            status=FollowUpTask.STATUS_PENDING,
        )
        logger.info("Created follow-up task for %s at %s (node %s)", customer_phone, scheduled_at, node.id)
        return task
    except Exception as e:
        logger.exception("create_follow_up_task: %s", e)
        return None


def _get_or_create_follow_up_config(node):
    """Get FollowUpNode for this node; if missing and node is follow-up type, create default."""
    if node.node_type != "follow-up":
        return None
    try:
        config, _ = FollowUpNode.objects.get_or_create(
            node=node,
            defaults={
                "delay_hours": 6,
                "response_type": FollowUpNode.RESPONSE_TYPE_TEXT,
                "ai_personalized": False,
                "caption": "",
            },
        )
        return config
    except Exception:
        return None


def _build_media_url(file_field):
    """Build absolute URL for a FileField (for WhatsApp media link)."""
    if not file_field:
        return None
    try:
        from django.conf import settings
        base = getattr(settings, "BASE_URL", "") or ""
        if not base and hasattr(settings, "ALLOWED_HOSTS") and settings.ALLOWED_HOSTS:
            base = "https://" + (settings.ALLOWED_HOSTS[0] if settings.ALLOWED_HOSTS else "")
        url = (file_field.url or "").strip()
        if not url:
            return None
        if url.startswith("http"):
            return url
        return (base.rstrip("/") + "/" + url.lstrip("/")) if base else None
    except Exception:
        return None


def run_follow_up_task(task):
    """
    Process one follow-up task: send message (text/media/audio), mark SENT, log to FollowUpSentLog.
    If current time is in quiet hours, reschedule task to next 08:00 and return without sending.
    Returns True if sent, False if skipped or error.
    """
    from django.utils import timezone
    from discount.models import FollowUpSentLog

    now = timezone.now()
    # Quiet hours (23:00–08:00): reschedule to next 08:00 instead of sending
    hour = now.hour
    if hour >= QUIET_HOUR_START or hour < QUIET_HOUR_END:
        next_allowed = _next_allowed_send_time(now)
        task.scheduled_at = next_allowed
        task.save(update_fields=["scheduled_at"])
        logger.info("Follow-up task %s rescheduled to %s (quiet hours)", task.id, next_allowed)
        return False

    config = getattr(task.node, "follow_up_config", None) or _get_or_create_follow_up_config(task.node)
    if not config:
        task.status = FollowUpTask.STATUS_CANCELLED
        task.is_cancelled = True
        task.save(update_fields=["status", "is_cancelled"])
        return False

    channel = task.channel
    phone = task.customer_phone
    response_type = (config.response_type or FollowUpNode.RESPONSE_TYPE_TEXT).upper()
    caption = (config.caption or "").strip()

    if getattr(config, "ai_personalized", False):
        try:
            from discount.services.follow_up_service import generate_follow_up_text
            text = generate_follow_up_text(channel, phone, limit=10)
            if text:
                caption = text
        except Exception as e:
            logger.warning("generate_follow_up_text: %s", e)
    if not caption and response_type == FollowUpNode.RESPONSE_TYPE_TEXT:
        caption = "مرحباً، تذكرنا أنك كنت مهتماً بمنتجاتنا. هل تحتاج مساعدة؟"

    try:
        if response_type == FollowUpNode.RESPONSE_TYPE_TEXT:
            from discount.whatssapAPI.process_messages import send_automated_response
            send_automated_response(phone, [{"type": "text", "content": caption, "delay": 0}], channel=channel)
        elif response_type == FollowUpNode.RESPONSE_TYPE_AUDIO:
            if getattr(config, "ai_personalized", False) and caption:
                from discount.whatssapAPI.voice_engine import generate_audio_file
                from discount.whatssapAPI.process_messages import send_whatsapp_audio_file
                store_settings = channel  # channel has voice_provider, elevenlabs_api_key, etc.
                audio_path = generate_audio_file(caption, store_settings)
                if audio_path:
                    send_whatsapp_audio_file(phone, audio_path, channel)
            elif config.file_attachment:
                media_url = _build_media_url(config.file_attachment)
                if media_url:
                    from discount.whatssapAPI.process_messages import send_automated_response
                    send_automated_response(
                        phone,
                        [{"type": "audio", "media_url": media_url, "content": caption}],
                        channel=channel,
                    )
        elif response_type in (FollowUpNode.RESPONSE_TYPE_IMAGE, FollowUpNode.RESPONSE_TYPE_VIDEO):
            media_url = _build_media_url(config.file_attachment) if config.file_attachment else None
            if media_url:
                from discount.whatssapAPI.process_messages import send_automated_response
                send_automated_response(
                    phone,
                    [{"type": response_type.lower(), "media_url": media_url, "content": caption}],
                    channel=channel,
                )
        else:
            from discount.whatssapAPI.process_messages import send_automated_response
            send_automated_response(phone, [{"type": "text", "content": caption or "", "delay": 0}], channel=channel)

        task.status = FollowUpTask.STATUS_SENT
        task.sent_at = now
        task.save(update_fields=["status", "sent_at"])
        FollowUpSentLog.objects.create(
            channel=channel,
            customer_phone=phone,
            node_id=task.node_id,
            response_type=response_type,
        )
        logger.info("Follow-up sent to %s (task %s)", phone, task.id)
        return True
    except Exception as e:
        logger.exception("run_follow_up_task %s: %s", task.id, e)
        return False
