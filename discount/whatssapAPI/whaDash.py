from discount.user_dash import change_password
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from discount.models import Contact, WhatsAppChannel  , CannedResponse

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
    
    # هنا يمكنك إضافة فلتر القناة إذا كانت الردود مرتبطة بقنوات
    # (حالياً الردود مرتبطة بالمستخدم، لكن سنطبق منطق الفريق)
    
    user = request.user
    responses_query = CannedResponse.objects.none()

    # --- منطق الصلاحيات المعقد ---
    
    # 1. إذا كان المستخدم هو الأدمن (Team Admin)
    if hasattr(user, 'is_team_admin') and user.is_team_admin:
        # يجلب ردوده الخاصة + ردود فريقه بالكامل
        # نفترض أن الموظفين لديهم حقل team_admin يشير لهذا المستخدم
        team_members = user.team_members.all() # الموظفين التابعين له
        
        responses_query = CannedResponse.objects.filter(
            Q(user=user) | Q(user__in=team_members)
        ).select_related('user') # لتحسين الأداء
        
    # 2. إذا كان موظفاً عادياً
    elif user.team_admin:
        # يرى ردوده الخاصة + ردود مديره (الأدمن) فقط
        # (عادة لا يرى ردود زملائه لتجنب الفوضى، إلا لو أردت ذلك)
        responses_query = CannedResponse.objects.filter(
            Q(user=user) | Q(user=user.team_admin)
        ).select_related('user')
        
    # 3. مستخدم مستقل
    else:
        responses_query = CannedResponse.objects.filter(user=user)

    # --- تحويل البيانات لـ JSON ---
    data = []
    for r in responses_query:
        # تحديد من هو الكاتب (للعرض في القائمة)
        author_label = "You"
        if r.user.id != user.id:
            author_label = r.user.first_name or r.user.username

        data.append({
            'id': r.id,
            'shortcut': r.shortcut,
            'message': r.message,
            'file_url': r.attachment.url if r.attachment else None,
            'media_type': r.type,
            'author': author_label, # لنعرض للمستخدم من كتب هذا الرد
            'is_mine': r.user.id == user.id # لتمييز ردودي بلون مختلف
        })

    return JsonResponse({'status': 'success', 'data': data})