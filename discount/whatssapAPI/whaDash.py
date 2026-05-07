import json
import logging
from discount.user_dash import change_password
from django.db.models import Count, Avg, F, ExpressionWrapper, DurationField, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.csrf import csrf_protect
from datetime import timedelta
from discount.models import Contact, WhatsAppChannel, CannedResponse, CustomUser, Message, Activity, CoachConversationMessage

def api_lifecycle_stats(request):
    user = request.user
    channel_id = request.GET.get('channel_id') # استقبال معرف القناة
    
    # 1. تحديد جهات الاتصال الأساسية بناءً على صلاحية المستخدم
    if getattr(user, 'is_team_admin', False) or user.is_superuser:
        # الأدمن يرى كل جهات الاتصال المرتبطة بفريقه
        # ملاحظة: يجب تعديل هذا الفلتر حسب هيكلية المودلز عندك بدقة
        contacts_qs = Contact.objects.filter(channel__owner=user.team_admin if user.team_admin else user) 
        # أو contacts_qs = Contact.objects.all() إذا كان السوبر يوزر يرى الكل
    else:
        # الموظف يرى فقط جهات الاتصال المسندة إليه
        contacts_qs = Contact.objects.filter(assigned_agent=user)
        print('contacts_qs',contacts_qs)

    # 2. 🔥 فلترة حسب القناة (إذا تم تحديدها) 🔥
    if channel_id and channel_id != 'all':
        # تحقق أمني: هل المستخدم مسموح له برؤية هذه القناة؟
        # (يمكنك استخدام دالة get_target_channel التي كتبناها سابقاً هنا)
        contacts_qs = contacts_qs.filter(channel_id=channel_id)

    # 3. تجميع البيانات (Aggregation)
    stats = contacts_qs.values('pipeline_stage').annotate(total=Count('id'))
    stats_dict = {item['pipeline_stage']: item['total'] for item in stats}
    
    total_contacts = contacts_qs.count() or 1 

    stages_config = [
        {
            'key': Contact.PipelineStage.NEW,  # ستعود بـ 'new'
            'label': 'New Chat', 
            'icon': '🆕', 
            'color': '#3b82f6'
        },
        {
            'key': Contact.PipelineStage.INTERESTED, # ستعود بـ 'interested'
            'label': 'Interested', 
            'icon': '🔥', 
            'color': '#f97316'
        },
        {
            'key': Contact.PipelineStage.FOLLOW_UP, # ستعود بـ 'follow_up'
            'label': 'Follow Up', 
            'icon': '🤩', 
            'color': '#8b5cf6'
        },
        {
            'key': Contact.PipelineStage.CLOSED, # ستعود بـ 'closed'
            'label': 'Close Won', 
            'icon': '💵', 
            'color': '#10b981'
        },
        {
            'key': Contact.PipelineStage.REJECTED, # ستعود بـ 'rejected'
            'label': 'No Answer', # أو التسمية التي تفضلها
            'icon': '👀', 
            'color': '#64748b'
        },
    ]

   
    data = []
    for stage in stages_config:
        count = stats_dict.get(stage['key'], 0)
        percent = (count / total_contacts) * 100
        
        data.append({
            'label': stage['label'],
            'icon': stage['icon'],
            'count': count,
            'percent': round(percent, 1),
            'color': stage['color'] , 
            'key': stage['key']
        })

    return JsonResponse({'lifecycle': data})











# quick replay 
# views.py
import mimetypes
from django.views.decorators.http import require_POST

@require_POST
def create_canned_response(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    shortcut = request.POST.get('shortcut')
    message = request.POST.get('message')
    attachment = request.FILES.get('attachment')
    channel_id =  request.POST.get('channel')
     
    channel = WhatsAppChannel.objects.get(id=channel_id)
    
    # تحديد نوع الميديا تلقائياً
    media_type = 'text'
    if attachment:
        mime_type, _ = mimetypes.guess_type(attachment.name)
        if mime_type:
            if mime_type.startswith('video'):
                media_type = 'video'
            elif mime_type.startswith('image'):
                media_type = 'image'
            else:
                media_type = 'document'

    # الحفظ
    CannedResponse.objects.create(
        user=request.user, # أو request.user.team_admin إذا كنت تطبق SaaS logic
        shortcut=shortcut,
        channel= channel,
        message=message,
        attachment=attachment,
        type=media_type
    )

    return JsonResponse({'status': 'success'})





from django.http import JsonResponse
from django.db.models import Q
from discount.models import CannedResponse

def get_canned_responses(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    channel_id = request.GET.get('channel_id')
    user = request.user
    
    # 1. تحديد "من يملك الردود" (Ownership Logic)
    # نحدد أولاً النطاق المسموح له (أنا، أو فريقي)
    if hasattr(user, 'is_team_admin') and user.is_team_admin:
        # الأدمن يرى ردوده + ردود موظفيه
        ownership_filter = Q(user=user) | Q(user__in=user.team_members.all())
        
    elif getattr(user, 'team_admin', None):
        # الموظف يرى ردوده + ردود مديره
        ownership_filter = Q(user=user) | Q(user=user.team_admin)
        
    else:
        # المستخدم العادي يرى ردوده فقط
        ownership_filter = Q(user=user)

    # 2. بناء الاستعلام الأساسي
    responses = CannedResponse.objects.filter(ownership_filter)

    # 3. فلترة القناة (Channel Logic) بذكاء
    # المنطق: نعرض الردود المرتبطة بالقناة الحالية + الردود العامة (التي ليس لها قناة)
    # لا نستخدم objects.get() هنا لتجنب الأخطاء
    if channel_id and channel_id != '0' and channel_id.isdigit():
        # (مرتبطة بهذه القناة) أو (عامة للكل)
        responses = responses.filter(
            Q(channel_id=channel_id) | Q(channel__isnull=True)
        )
    else:
        # إذا لم يتم تحديد قناة، هل تريد عرض كل شيء؟ أم العام فقط؟
        # هنا نفترض أننا نعرض العام فقط أو الكل (حسب رغبتك)
        # responses = responses # (هذا السطر يعرض كل شيء متاح للمستخدم)
        pass
 
    data = []
    for r in responses:
      
        author_label = "You"
        if r.user.id != user.id:
            author_label = r.user.first_name or r.user.username
        import time
        from datetime import datetime
        formatted_date = r.created_at.strftime('%Y-%m-%d %I:%M %p') if r.created_at else "" 
       
        data.append({
            'id': r.id,
            'shortcut': r.shortcut,
            'message': r.message or '',
            'file_url': r.attachment.url if r.attachment else None,
            'media_type': r.type or 'text',
            'author': author_label,
            'creator_name': r.user.first_name or r.user.username,
            'creator_avatar': '',
            'is_mine': r.user.id == user.id,
            'created_at': formatted_date,
            'usage': r.usage,
            'usage_count': r.usage,
        })
    from django.core.serializers.json import DjangoJSONEncoder
    return JsonResponse({'status': 'success', 'data': data}, encoder=DjangoJSONEncoder)


@require_POST
def update_canned_response(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    reply_id = request.POST.get('id')
    if not reply_id:
        return JsonResponse({'error': 'Missing id'}, status=400)
    reply = get_object_or_404(CannedResponse, id=reply_id)
    if reply.user_id != request.user.id:
        return JsonResponse({'error': 'Not allowed to edit this reply'}, status=403)
    shortcut = request.POST.get('shortcut')
    message = request.POST.get('message')
    attachment = request.FILES.get('attachment')
    if shortcut is not None:
        reply.shortcut = shortcut
    if message is not None:
        reply.message = message
    if attachment:
        mime_type, _ = mimetypes.guess_type(attachment.name)
        media_type = 'text'
        if mime_type:
            if mime_type.startswith('video'):
                media_type = 'video'
            elif mime_type.startswith('image'):
                media_type = 'image'
            else:
                media_type = 'document'
        reply.attachment = attachment
        reply.type = media_type
    reply.save()
    return JsonResponse({'status': 'success'})


@require_POST
def delete_canned_response(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    reply_id = request.POST.get('id')
    if not reply_id:
        return JsonResponse({'error': 'Missing id'}, status=400)
    reply = get_object_or_404(CannedResponse, id=reply_id)
    if reply.user_id != request.user.id:
        return JsonResponse({'error': 'Not allowed to delete this reply'}, status=403)
    reply.delete()
    return JsonResponse({'status': 'success'})


def api_agent_stats(request):
    """
    Returns performance stats for a specific agent:
    - Total online time (today + this week)
    - Average response time (across channels the agent has access to)
    - Last time online (if currently offline)
    - Messages sent today
    - Conversations handled today
    """
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Unauthorized"}, status=401)
    if not (getattr(request.user, 'is_team_admin', False) or request.user.is_superuser):
        return JsonResponse({"error": "Forbidden"}, status=403)

    raw_agent_id = request.GET.get('agent_id')
    if not raw_agent_id:
        return JsonResponse({"error": "agent_id required"}, status=400)
    try:
        agent_id = int(raw_agent_id)
    except (TypeError, ValueError):
        return JsonResponse({"error": "Invalid agent_id"}, status=400)

    try:
        agent = CustomUser.objects.get(pk=agent_id)
    except CustomUser.DoesNotExist:
        return JsonResponse({"error": "Agent not found"}, status=404)

    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=today_start.weekday())

    # --- 1. Online time from Activity logs ---
    # Uses ws_connect/ws_disconnect (WebSocket) AND login/logout pairs
    CONNECT_TYPES = ('login', 'ws_connect')
    DISCONNECT_TYPES = ('logout', 'ws_disconnect')
    ALL_PRESENCE_TYPES = CONNECT_TYPES + DISCONNECT_TYPES

    def calc_online_seconds(since):
        activities = list(
            Activity.objects.filter(
                user=agent,
                activity_type__in=ALL_PRESENCE_TYPES,
                timestamp__gte=since
            ).order_by('timestamp').values_list('activity_type', 'timestamp')
        )
        total = timedelta()
        connect_time = None
        for atype, ts in activities:
            if atype in CONNECT_TYPES:
                if connect_time is None:
                    connect_time = ts
            elif atype in DISCONNECT_TYPES and connect_time:
                total += ts - connect_time
                connect_time = None
        # If still connected (no disconnect after last connect)
        if connect_time and agent.is_online:
            total += now - connect_time
        return total.total_seconds()

    online_today_secs = calc_online_seconds(today_start)
    online_week_secs = calc_online_seconds(week_start)

    def fmt_duration(secs):
        secs = int(secs)
        if secs < 60:
            return f"{secs}s"
        h, rem = divmod(secs, 3600)
        m, s = divmod(rem, 60)
        if h > 0:
            return f"{h}h {m}m"
        return f"{m}m {s}s"

    # --- 2. Average response time ---
    # For each agent reply (is_from_me=True), find the last customer message
    # in the same conversation thread and compute the time delta.
    # Only count messages where user=agent so each agent's stats are separate
    # (messages with user=NULL cannot be attributed to a specific agent).
    agent_channels = WhatsAppChannel.objects.filter(
        Q(owner=agent) | Q(assigned_agents=agent)
    ).distinct()

    agent_replies = Message.objects.filter(
        is_from_me=True,
        is_internal=False,
        channel__in=agent_channels,
        user=agent,
        timestamp__gte=week_start,
    ).order_by('timestamp').select_related('channel')

    response_deltas = []

    for reply in agent_replies[:200]:
        last_customer_msg = Message.objects.filter(
            sender=reply.sender,
            is_from_me=False,
            channel=reply.channel,
            timestamp__lt=reply.timestamp,
        ).order_by('-timestamp').values_list('timestamp', flat=True).first()

        if last_customer_msg:
            delta = (reply.timestamp - last_customer_msg).total_seconds()
            if 0 < delta < 86400:
                response_deltas.append(delta)

    avg_response_secs = (sum(response_deltas) / len(response_deltas)) if response_deltas else None

    def fmt_response_time(secs):
        if secs is None:
            return "No data"
        secs = int(secs)
        if secs < 60:
            return f"{secs}s"
        h, rem = divmod(secs, 3600)
        m, s = divmod(rem, 60)
        if h > 0:
            return f"{h}h {m}m"
        return f"{m}m"

    # --- 3. Last seen ---
    last_seen_str = None
    if not agent.is_online and agent.last_seen:
        diff = now - agent.last_seen
        if diff.total_seconds() < 60:
            last_seen_str = "Just now"
        elif diff.total_seconds() < 3600:
            last_seen_str = f"{int(diff.total_seconds() // 60)}m ago"
        elif diff.total_seconds() < 86400:
            last_seen_str = f"{int(diff.total_seconds() // 3600)}h ago"
        else:
            last_seen_str = agent.last_seen.strftime("%b %d, %I:%M %p")

    # --- 4. Messages sent ---
    # Only count messages where user=agent (exclude user=NULL so admin and agents don't share counts)
    agent_msg_base = Message.objects.filter(
        is_from_me=True,
        is_internal=False,
        channel__in=agent_channels,
        user=agent,
    )

    msgs_today = agent_msg_base.filter(timestamp__gte=today_start).count()
    msgs_week = agent_msg_base.filter(timestamp__gte=week_start).count()
    msgs_total = agent_msg_base.count()

    # --- 5. Unique conversations ---
    convos_today = agent_msg_base.filter(
        timestamp__gte=today_start
    ).values('sender').distinct().count()
    convos_week = agent_msg_base.filter(
        timestamp__gte=week_start
    ).values('sender').distinct().count()
    convos_total = agent_msg_base.values('sender').distinct().count()

    # --- 6. Response time rating ---
    if avg_response_secs is None:
        speed_label = "No data"
        speed_color = "gray"
    elif avg_response_secs < 120:
        speed_label = "Excellent"
        speed_color = "green"
    elif avg_response_secs < 300:
        speed_label = "Good"
        speed_color = "blue"
    elif avg_response_secs < 900:
        speed_label = "Average"
        speed_color = "yellow"
    else:
        speed_label = "Slow"
        speed_color = "red"

    return JsonResponse({
        "success": True,
        "agent": {
            "id": agent.id,
            "name": f"{agent.user_name or agent.first_name} {agent.last_name or ''}".strip(),
            "is_online": agent.is_online,
            "role": getattr(agent, 'role', 'Agent') or 'Agent',
        },
        "stats": {
            "online_today": fmt_duration(online_today_secs),
            "online_today_secs": online_today_secs,
            "online_week": fmt_duration(online_week_secs),
            "online_week_secs": online_week_secs,
            "avg_response_time": fmt_response_time(avg_response_secs),
            "avg_response_secs": avg_response_secs,
            "speed_label": speed_label,
            "speed_color": speed_color,
            "last_seen": last_seen_str,
            "messages_today": msgs_today,
            "messages_week": msgs_week,
            "messages_total": msgs_total,
            "conversations_today": convos_today,
            "conversations_week": convos_week,
            "conversations_total": convos_total,
        },
    })


def handle_update_override_rules(channel_id, custom_rules):
    """
    Update ai_override_rules for the given channel (workspace).
    Called when the coaching AI uses the update_override_rules tool.
    """
    try:
        pk = int(channel_id)
    except (TypeError, ValueError):
        return {"success": False, "error": "Invalid channel_id"}
    try:
        channel = WhatsAppChannel.objects.get(pk=pk)
    except WhatsAppChannel.DoesNotExist:
        return {"success": False, "error": "Channel not found"}
    rules = (custom_rules or "").strip()
    if len(rules) > 8000:
        rules = rules[:8000]
    channel.ai_override_rules = rules
    channel.save(update_fields=["ai_override_rules"])
    return {"success": True, "message": "Rules updated."}


@require_http_methods(["GET"])
def api_coach_ai_rules(request):
    """Return current ai_override_rules for the channel. GET ?channel_id=."""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Unauthorized"}, status=401)
    if not (getattr(request.user, "is_team_admin", False) or request.user.is_superuser):
        return JsonResponse({"error": "Forbidden"}, status=403)
    try:
        channel_id = int(request.GET.get("channel_id", 0))
    except (TypeError, ValueError):
        return JsonResponse({"error": "channel_id required"}, status=400)
    try:
        channel = WhatsAppChannel.objects.get(pk=channel_id)
    except WhatsAppChannel.DoesNotExist:
        return JsonResponse({"error": "Channel not found"}, status=404)
    if not channel.has_user_permission(request.user):
        return JsonResponse({"error": "Forbidden"}, status=403)
    rules = (getattr(channel, "ai_override_rules", None) or "").strip()
    return JsonResponse({"success": True, "rules": rules})


@require_http_methods(["POST"])
def api_coach_ai_clear_rules(request):
    """Clear ai_override_rules for the channel. POST body: { "channel_id": int }."""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Unauthorized"}, status=401)
    if not (getattr(request.user, "is_team_admin", False) or request.user.is_superuser):
        return JsonResponse({"error": "Forbidden"}, status=403)
    try:
        body = json.loads(request.body) if request.body else {}
    except Exception:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    try:
        channel_id = int(body.get("channel_id", 0))
    except (TypeError, ValueError):
        return JsonResponse({"error": "channel_id required"}, status=400)
    try:
        channel = WhatsAppChannel.objects.get(pk=channel_id)
    except WhatsAppChannel.DoesNotExist:
        return JsonResponse({"error": "Channel not found"}, status=404)
    if not channel.has_user_permission(request.user):
        return JsonResponse({"error": "Forbidden"}, status=403)
    channel.ai_override_rules = ""
    channel.save(update_fields=["ai_override_rules"])
    return JsonResponse({"success": True, "message": "Rules cleared."})


@require_http_methods(["POST"])
def api_coach_ai_set_rules(request):
    """Set ai_override_rules for the channel. POST body: { "channel_id": int, "rules": str }."""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Unauthorized"}, status=401)
    if not (getattr(request.user, "is_team_admin", False) or request.user.is_superuser):
        return JsonResponse({"error": "Forbidden"}, status=403)
    try:
        body = json.loads(request.body) if request.body else {}
    except Exception:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    try:
        channel_id = int(body.get("channel_id", 0))
    except (TypeError, ValueError):
        return JsonResponse({"error": "channel_id required"}, status=400)
    try:
        channel = WhatsAppChannel.objects.get(pk=channel_id)
    except WhatsAppChannel.DoesNotExist:
        return JsonResponse({"error": "Channel not found"}, status=404)
    if not channel.has_user_permission(request.user):
        return JsonResponse({"error": "Forbidden"}, status=403)
    rules = (body.get("rules") or "").strip()
    if len(rules) > 8000:
        rules = rules[:8000]
    channel.ai_override_rules = rules
    channel.save(update_fields=["ai_override_rules"])
    return JsonResponse({"success": True, "message": "Rules updated."})


@require_http_methods(["GET"])
def api_coach_ai_history(request):
    """
    Get saved coach conversation history for the current user and channel.
    GET ?channel_id=<id>. Returns { "messages": [ {"role": "user"|"assistant", "content": "...", "created_at": "..."} ] }
    """
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Unauthorized"}, status=401)
    if not (getattr(request.user, "is_team_admin", False) or request.user.is_superuser):
        return JsonResponse({"error": "Forbidden"}, status=403)
    channel_id = request.GET.get("channel_id")
    if not channel_id:
        return JsonResponse({"error": "channel_id required"}, status=400)
    try:
        channel = WhatsAppChannel.objects.get(pk=channel_id)
    except WhatsAppChannel.DoesNotExist:
        return JsonResponse({"error": "Channel not found"}, status=404)
    if not channel.has_user_permission(request.user):
        return JsonResponse({"error": "Forbidden"}, status=403)
    qs = CoachConversationMessage.objects.filter(channel=channel, user=request.user).order_by("created_at")
    messages = [
        {"role": m.role, "content": m.content, "created_at": timezone.localtime(m.created_at).isoformat()}
        for m in qs
    ]
    return JsonResponse({"messages": messages})


@require_http_methods(["POST"])
def api_coach_ai(request):
    """
    Admin-to-AI coaching chat. Uses a different system prompt and only the
    update_override_rules tool. POST body: { "channel_id": int, "messages": [{"role":"user"|"assistant","content":"..."}] }
    """
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Unauthorized"}, status=401)
    if not (getattr(request.user, "is_team_admin", False) or request.user.is_superuser):
        return JsonResponse({"error": "Forbidden"}, status=403)
    try:
        body = json.loads(request.body) if request.body else {}
    except Exception:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    channel_id = body.get("channel_id")
    if channel_id is None:
        return JsonResponse({"error": "channel_id required"}, status=400)
    try:
        channel = WhatsAppChannel.objects.get(pk=channel_id)
    except WhatsAppChannel.DoesNotExist:
        return JsonResponse({"error": "Channel not found"}, status=404)
    if not channel.has_user_permission(request.user):
        return JsonResponse({"error": "Forbidden"}, status=403)
    messages = body.get("messages") or []
    if not isinstance(messages, list):
        return JsonResponse({"error": "messages must be a list"}, status=400)
    from ai_assistant.services import generate_reply_coaching
    # Build OpenAI-format messages (no system; we add it in generate_reply_coaching)
    openai_messages = []
    for m in messages:
        role = m.get("role")
        content = m.get("content", "")
        if role in ("user", "assistant") and content is not None:
            openai_messages.append({"role": role, "content": str(content)[:8000]})
    try:
        reply = generate_reply_coaching(openai_messages)
    except Exception as e:
        return JsonResponse({"error": str(e), "reply": None}, status=500)
    # Handle tool calls: update_override_rules
    _coach_log = logging.getLogger(__name__)
    final_content = reply.get("content") or ""
    tool_calls = reply.get("tool_calls") or []
    rules_saved = False
    for tc in tool_calls:
        if tc.get("name") == "update_override_rules":
            try:
                args = json.loads(tc.get("arguments") or "{}")
                custom_rules = args.get("custom_rules", "")
                result = handle_update_override_rules(channel_id, custom_rules)
                if result.get("success"):
                    rules_saved = True
                else:
                    _coach_log.warning("coach-ai: handle_update_override_rules failed: %s", result.get("error"))
            except Exception as e:
                _coach_log.exception("coach-ai: update_override_rules failed: %s", e)
    # Do NOT save the raw user message as rules—only the model's tool call (extracted/validated rule) is saved.
    if tool_calls and not final_content:
        final_content = "Rules updated. Anything else you want to change?"
    # Persist this exchange for conversation history
    last_user_msg = next((m for m in reversed(openai_messages) if m.get("role") == "user"), None)
    if last_user_msg and (last_user_msg.get("content") or "").strip():
        try:
            CoachConversationMessage.objects.create(
                channel=channel,
                user=request.user,
                role="user",
                content=(last_user_msg.get("content") or "").strip()[:10000],
            )
            CoachConversationMessage.objects.create(
                channel=channel,
                user=request.user,
                role="assistant",
                content=(final_content or "").strip()[:10000],
            )
        except Exception as e:
            _coach_log.warning("coach-ai: save conversation failed: %s", e)
    return JsonResponse({"success": True, "reply": final_content})