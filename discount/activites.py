import logging
import threading
from django.contrib.contenttypes.models import ContentType
from django.db import transaction

logger = logging.getLogger(__name__)

_VALID_TYPES = None


def _get_valid_types():
    """Cache the set of valid activity_type keys on first call."""
    global _VALID_TYPES
    if _VALID_TYPES is None:
        from .models import Activity
        _VALID_TYPES = {t[0] for t in Activity.ACTIVITY_TYPES}
    return _VALID_TYPES


def _extract_ip(request):
    """Extract client IP from request, handling proxies."""
    if request is None:
        return None
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def log_activity(
    activity_type,
    description='',
    user=None,
    request=None,
    related_object=None,
    ip_address=None,
    defer=True,
):
    """
    Lightweight activity logger.

    Parameters
    ----------
    activity_type : str
        Must match one of Activity.ACTIVITY_TYPES keys.
    description : str
        Human-readable description of what happened.
    user : CustomUser | None
        The actor. Falls back to request.user if not given.
    request : HttpRequest | None
        Optional. Used to extract user and IP when not provided explicitly.
    related_object : Model | None
        Optional Django model instance to link via GenericForeignKey.
    ip_address : str | None
        Explicit IP. Auto-extracted from request if omitted.
    defer : bool
        If True (default), the DB write runs after the current transaction
        commits via transaction.on_commit, so it never slows down the
        response. Set False only when you need the Activity row immediately.
    """
    if activity_type not in _get_valid_types():
        logger.warning("log_activity: unknown type '%s', skipping", activity_type)
        return

    if user is None and request is not None:
        user = getattr(request, 'user', None)
        if user is not None and not user.is_authenticated:
            user = None

    if ip_address is None:
        ip_address = _extract_ip(request)

    ct_id = None
    obj_id = None
    if related_object is not None:
        try:
            ct_id = ContentType.objects.get_for_model(related_object).pk
            obj_id = related_object.pk
        except Exception:
            pass

    def _write():
        try:
            from .models import Activity
            Activity.objects.create(
                user=user,
                activity_type=activity_type,
                description=description[:2000] if description else '',
                ip_address=ip_address,
                content_type_id=ct_id,
                object_id=obj_id,
            )
        except Exception:
            logger.exception("log_activity: failed to write '%s'", activity_type)

    if defer:
        try:
            transaction.on_commit(_write)
        except Exception:
            threading.Thread(target=_write, daemon=True).start()
    else:
        _write()


def log_activity_async(activity_type, description='', user=None, ip_address=None):
    """
    Fire-and-forget version for use inside async contexts (WebSocket consumers).
    Runs the DB write in a background thread to avoid blocking the event loop.
    """
    if activity_type not in _get_valid_types():
        return

    user_id = user.pk if user else None

    def _write():
        try:
            from .models import Activity, CustomUser
            u = CustomUser.objects.get(pk=user_id) if user_id else None
            Activity.objects.create(
                user=u,
                activity_type=activity_type,
                description=description[:2000] if description else '',
                ip_address=ip_address,
            )
        except Exception:
            logger.exception("log_activity_async: failed '%s'", activity_type)

    threading.Thread(target=_write, daemon=True).start()


# ── Legacy wrapper (backward-compatible) ──

def activity_log(request, activity_type=None, description='',
                 related_object=None, ip_address=None, active_time=None):
    """Kept for backward compatibility with existing call sites."""
    if not activity_type:
        return False
    log_activity(
        activity_type=activity_type,
        description=description,
        request=request,
        related_object=related_object,
        ip_address=ip_address,
        defer=True,
    )
    return True


# ── View for tracking page activity (referenced in urls.py) ──

def save_activity_tracking(request):
    """Log when a user accesses the tracking page."""
    from django.http import JsonResponse
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'POST required'}, status=405)
    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'message': 'Not authenticated'}, status=401)
    phone_number = request.POST.get('phone', '')
    log_activity(
        'order_tracked',
        f"Tracked order for phone: {phone_number}",
        request=request,
    )
    return JsonResponse({'success': True, 'message': 'Activity logged'})
