import os


def sentry_config(request):
    return {
        "SENTRY_DSN_FRONTEND": os.environ.get("SENTRY_DSN_FRONTEND", ""),
    }


def app_navbar(request):
    """Channel chip data for the shared top navbar."""
    user = getattr(request, "user", None)
    empty = {
        "nav_user_channels": [],
        "nav_active_channel": None,
        "nav_initial_channel_id": None,
    }
    if not user or not getattr(user, "is_authenticated", False):
        return empty
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return empty
    try:
        from django.db.models import Count, Q
        from discount.models import WhatsAppChannel
    except Exception:
        return empty

    if getattr(user, "is_team_admin", False) or user.is_superuser:
        channels = WhatsAppChannel.objects.filter(owner=user)
    else:
        channels = WhatsAppChannel.objects.filter(assigned_agents=user)
    channels = channels.annotate(
        unread_count=Count(
            "messages",
            filter=Q(messages__is_read=False, messages__is_from_me=False),
        )
    )

    active = WhatsAppChannel.resolve_for_request(request, channels)

    return {
        "nav_user_channels": channels,
        "nav_active_channel": active,
        "nav_initial_channel_id": active.id if active else None,
    }
