"""
API View للحصول على Context المحادثة
"""
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_GET, require_POST
from django.utils import timezone
from discount.services.context_integration import (
    get_conversation_state_debug,
    channel_accessible_for_user,
)
from discount.models import WhatsAppChannel
import logging

logger = logging.getLogger(__name__)


@login_required
@require_GET
def get_conversation_context_api(request, channel_id, customer_phone):
    """
    GET /api/conversation-context/{channel_id}/{phone}/
    
    Returns conversation context (product, customer data, stage, etc.)
    for display in the UI Context Panel.
    
    Access control: user must have access to the channel.
    """
    try:
        user = request.user
        channel = WhatsAppChannel.objects.filter(id=channel_id).first()
        if not channel or not channel_accessible_for_user(channel, user):
            return JsonResponse({
                'error': 'Channel not found or access denied'
            }, status=403)
        
        # الحصول على السياق
        context_data = get_conversation_state_debug(
            channel_id=int(channel_id),
            customer_phone=customer_phone
        )
        
        # إضافة معلومات إضافية
        context_data['channel_name'] = channel.name
        context_data['timestamp'] = timezone.now().isoformat()
        
        return JsonResponse(context_data)
    
    except Exception as e:
        logger.exception(f"Error in get_conversation_context_api: {e}")
        return JsonResponse({
            'error': str(e)
        }, status=500)


@login_required
@require_POST
def reset_conversation_context_api(request, channel_id, customer_phone):
    """
    POST /api/reset-context/{channel_id}/{phone}/
    
    Reset conversation context (start fresh conversation).
    """
    try:
        from discount.services.context_integration import reset_conversation_context
        
        user = request.user
        channel = WhatsAppChannel.objects.filter(id=channel_id).first()
        if not channel or not channel_accessible_for_user(channel, user):
            return JsonResponse({
                'error': 'Channel not found or access denied'
            }, status=403)
        
        # إعادة تعيين السياق
        reset_conversation_context(int(channel_id), customer_phone)
        
        logger.info(
            f"Context reset by user {user.id} for "
            f"channel {channel_id}, phone {customer_phone}"
        )
        
        return JsonResponse({
            'success': True,
            'message': 'Context reset successfully'
        })
    
    except Exception as e:
        logger.exception(f"Error in reset_conversation_context_api: {e}")
        return JsonResponse({
            'error': str(e)
        }, status=500)
