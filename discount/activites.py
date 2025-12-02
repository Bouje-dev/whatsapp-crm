from .models import Activity
from django.http import JsonResponse
from django.contrib.contenttypes.models import ContentType

def activity_log(request, activity_type=None, description='', related_object=None, ip_address=None, active_time=None):
    """
    دالة لحفظ سلوك المستخدم (نشاط).
    
    المعاملات:
    - user: كائن المستخدم الذي قام بالنشاط (اختياري)
    - activity_type: نوع النشاط من الثوابت المحددة في الموديل (إجباري)
    - description: وصف إضافي للنشاط (اختياري)
    - related_object: الكائن المرتبط بالنشاط مثل Order أو User أو غيره (اختياري)
    - ip_address: عنوان IP للمستخدم (اختياري)
    - active_time: الوقت النشط إذا كان متوفرًا (اختياري)

    ترجع:
    - قام بالتسجيل: True
    - لم يتم التسجيل: False
    """
    user = request.user
    ip = request.META.get('REMOTE_ADDR', None)

    if not activity_type:
        return JsonResponse({'success': False, 'error': 'activity_type is required'}, status=400)

    activity_data = {
        'user': request.user,
        'activity_type': activity_type,
        'description': description,
        'ip_address': ip,
        'active_time': active_time
    }

    if related_object:
        activity_data['content_type'] = ContentType.objects.get_for_model(related_object)
        activity_data['object_id'] = related_object.pk

    try:
        Activity.objects.create(**activity_data)
        return True
    except Exception as e:
        # يمكنك تسجيل الخطأ أو طباعته هنا إن أردت
      
        return JsonResponse({'success': False, 'error': str(e)})

 





def save_activity_tracking(request):

    """
    دالة لحفظ نشاط المستخدم في قاعدة البيانات.
    
    المعاملات:
    - request: كائن الطلب الذي يحتوي على معلومات المستخدم والنشاط.
    
    ترجع:
    - قام بالتسجيل: True
    - لم يتم التسجيل: False
    """
    if request.method == 'POST':
        phone_number = request.POST.get('phone')
            
    user = request.user
    if not user.is_authenticated:
        return False
 

    activity_type = 'tracking :' , phone_number 
    description = 'User accessed tracking page'
    
    send = activity_log(request, activity_type, description)
    if send:
        return JsonResponse({'success': True, 'message': 'Activity logged successfully'})
    else:
        return JsonResponse({'success': False, 'message': 'Failed to log activity'})


