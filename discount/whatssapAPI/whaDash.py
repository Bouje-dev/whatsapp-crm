from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from discount.models import Contact, WhatsAppChannel 

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