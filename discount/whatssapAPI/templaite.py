import json
import logging
from datetime import datetime

import requests
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST, require_GET, require_http_methods
from django.db import transaction


from django.views.decorators.csrf import csrf_exempt
# WHATSAPP_SYSTEM_USER_TOKEN = 'YOUR_SYSTEM_USER_ACCESS_TOKEN'  
WHATSAPP_API_VERSION = 'v22.0'  # أو v16.0 أو ما تستخدمه - تأكد من التوافق

WHATSAPP_SYSTEM_USER_TOKEN = getattr(settings, 'ACCESS_TOKEN', "EAALZBubBgmq0BP7ECHmEACY6YMB8nsV8MtxTQKwSexB3RqW9ZB3EkRdDp7MQnjuqCJHQ598lkQ9CQQmXTd2jZAI8NhGKyMLATmJgXbZAWKprwErSjANdMsTtduBBvqURZApEWlAqcYsgckaTLcWgYUHmzfFanu0oZANZC3H5zSj2fGjKZCm4oTTRpsjGbXy7zNwRbQZDZD")

# WHATSAPP_BUSINESS_ACCOUNT_ID = getattr(settings, 'PHONE_NUMBER_ID', "881753951677151")
# VERIFY_TOKEN = getattr(settings, 'VERIFY_TOKEN', "token")

# WABA = getattr(settings, 'PHONE_NUMBER_ID', "1481447496413263")
# TOKEN =  getattr(settings, 'ACCESS_TOKEN', "EAALZBubBgmq0BP7ECHmEACY6YMB8nsV8MtxTQKwSexB3RqW9ZB3EkRdDp7MQnjuqCJHQ598lkQ9CQQmXTd2jZAI8NhGKyMLATmJgXbZAWKprwErSjANdMsTtduBBvqURZApEWlAqcYsgckaTLcWgYUHmzfFanu0oZANZC3H5zSj2fGjKZCm4oTTRpsjGbXy7zNwRbQZDZD")
# API_VER = 'v22.0'


# افترض أن Template موجود في نفس الموديل
from discount.models import Template

logger = logging.getLogger(__name__)

# ---------- دالة مساعدة لإرسال القالب إلى Meta (Create template on WABA) ----------
def submit_template_to_meta(template , channel , user = None):
    """
    Build payload from Template instance and POST to:
      https://graph.facebook.com/{API_VERSION}/{WABA_ID}/message_templates
    Returns dict: {'ok': True, 'meta_id': '...', 'response': {...}}
    or {'ok': False, 'error': '...'}
    """


    # if not WABA or not TOKEN:
    #     return {'ok': False, 'error': 'WHATSAPP_BUSINESS_ACCOUNT_ID or token not configured.'}
    

    if not channel or not channel.id:
        return {'ok': False, 'error': 'channel id not configured.'}
   
    WABA = channel.business_account_id
    API_VER = channel.api_version
    TOKEN = channel.access_token
    url = f'https://graph.facebook.com/{API_VER}/{WABA}/message_templates'

    # category: try map or uppercase; Meta expects uppercase like 'UTILITY'/'MARKETING'
    category = (template.category or 'utility').upper()

    # language: pass what user set (prefer full code like "ar" or "ar_MA")
    language = template.language or 'ar'

    # Build components list
    components = []

    # Header text (only TEXT header handled here)
    if template.header_type == 'text' and (template.header_text or '').strip():
        components.append({
            "type": "HEADER",
            "format": "TEXT",
            "text": template.header_text
        })

    # Body (required)
    body_text = template.body or ''
    body_comp = {
        "type": "BODY",
        "text": body_text
    }

    # Try to attach example body_text values if template.sample_values / meta stored
    # We expect sample_values to be a dict or template may have meta_body_samples
    example_values = []
    # check common places for samples
    samples = None
    try:
        if hasattr(template, 'sample_values') and template.sample_values:
            # sample_values could be dict { "1":"A", ... } or list; normalize:
            sv = template.sample_values
            if isinstance(sv, dict):
                # produce list order 1..N
                maxn = max([int(k) for k in sv.keys()]) if sv.keys() else 0
                row = []
                for i in range(1, maxn+1):
                    row.append(str(sv.get(str(i), '')))
                example_values.append(row)
            elif isinstance(sv, list):
                # assume list of objects with text fields or list of texts
                # try to flatten
                flat = []
                for it in sv:
                    if isinstance(it, dict) and 'text' in it:
                        flat.append(str(it['text']))
                    else:
                        flat.append(str(it))
                example_values.append(flat)
        else:
            # try meta_body_samples if stored as JSON string
            if hasattr(template, 'meta_body_samples') and template.meta_body_samples:
                raw = template.meta_body_samples
                if isinstance(raw, str):
                    parsed = json.loads(raw)
                else:
                    parsed = raw
                # parsed expected list of {type:'text', text:'...'}
                row = []
                for it in parsed:
                    row.append(str(it.get('text', '')))
                example_values.append(row)
    except Exception:
        # ignore parsing problems; not critical
        logger.exception('error parsing body samples')

    if example_values:
        body_comp['example'] = {'body_text': example_values}

    components.append(body_comp)

    # Footer
    if template.footer:
        components.append({
            "type": "FOOTER",
            "text": template.footer
        })

    # Buttons: template.buttons expected to be a list (JSONField)
    if getattr(template, 'buttons', None):
        try:
            btns = template.buttons
            # if stored as str, parse
            if isinstance(btns, str):
                btns = json.loads(btns)
            # Build the BUTTONS component
            btn_list = []
            for b in btns:
                t = (b.get('type') or '').strip().lower()
                text = b.get('text') or b.get('title') or ''
                if not text:
                    continue
                if t == 'url':
                    btn_list.append({"type": "URL", "text": text, "url": b.get('url', '')})
                elif t == 'call':
                    btn_list.append({"type": "PHONE_NUMBER", "text": text, "phone_number": b.get('phone', '')})
                elif t == 'quick_reply' or t == 'quickreply':
                    btn_list.append({"type": "QUICK_REPLY", "text": text})
                elif t == 'COPY' or t == 'COPY_CODE':
             
                    btn_list.append({"type": "COPY_CODE", "example": text})
                else:
                    # generic fallback
                    btn_list.append({"type": "QUICK_REPLY", "text": text})
            if btn_list:
                components.append({
                    "type": "BUTTONS",
                    "buttons": btn_list
                })
        except Exception:
            logger.exception('error building buttons component')

    payload = {
        "name": template.name,
        "category": category,
        "language": language,
        "components": components
    }

    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json"
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
    except Exception as e:
        logger.exception('error calling meta create template')
        return {'ok': False, 'error': f'HTTP error: {e}'}

    try:
        data = resp.json()
    except Exception:
        data = {'raw_text': resp.text}
     

    if not resp.ok:
        # return meta error details
        err_msg = data.get('error') or data
        return {'ok': False, 'error': err_msg, 'response': data, 'status_code': resp.status_code}

    # Success - parse returned id if any
    meta_id = None
    # Meta may return metaTemplateId or id or id inside data
    if isinstance(data, dict):
        meta_id = data.get('metaTemplateId') or data.get('id') or data.get('template_id') or None
        # Some endpoints return nested 'data' list
        if not meta_id and isinstance(data.get('data'), list) and data['data']:
            meta_id = data['data'][0].get('id') or data['data'][0].get('metaTemplateId')
    return {'ok': True, 'meta_id': meta_id, 'response': data}






from django.http import JsonResponse
from django.shortcuts import get_object_or_404
import requests
from discount.models import WhatsAppChannel, Template  # تأكد من المسار الصحيح

def sync_pending_templates(request):
    user = request.user
    
    # 1. استخراج معرف القناة من الرابط
    channel_id = request.GET.get('channel_id')
    
    if not channel_id:
        return JsonResponse({'success': False, 'error': 'Missing channel_id'}, status=400)

    # 2. البحث عن القناة والتحقق من الصلاحيات (Admin vs Agent)
    channel = None
    if user.is_superuser or getattr(user, 'is_team_admin', False):
        channel = WhatsAppChannel.objects.filter(id=channel_id, owner=user).first()
    else:
        channel = WhatsAppChannel.objects.filter(id=channel_id, assigned_agents=user).first()

    if not channel:
        return JsonResponse({'success': False, 'error': 'Channel not found or permission denied'}, status=403)

    # 3. إعداد الاتصال بـ Meta باستخدام بيانات القناة
    API_VER = 'v18.0' # يفضل استخدام نسخة ثابتة
    access_token = channel.access_token 
    
    if not access_token:
        return JsonResponse({'success': False, 'error': 'Channel has no access token'}, status=500)

    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }

    # 4. جلب القوالب المعلقة *الخاصة بهذه القناة فقط*
    # ملاحظة: يجب أن يكون لديك حقل channel في مودل Template
    pending_templates = Template.objects.filter(channel=channel, status__iexact='pending')

    updated = []
    unchanged = []

    print(f"🔄 Syncing {pending_templates.count()} pending templates for channel: {channel.name}")

    for template in pending_templates:
        if not template.template_id:
            continue

        try:
            # رابط API لفحص حالة القالب
            url = f'https://graph.facebook.com/{API_VER}/{template.template_id}'
            params = {'fields': 'name,category,status'}

            resp = requests.get(url, headers=headers, params=params, timeout=20)
            data = resp.json() if resp.text else {}
            
            # طباعة للـ Debugging
            # print(f"Checking template {template.name}: {data.get('status')}")

            if not resp.ok:
                print(f"❌ Error checking template {template.id}: {data}")
                continue

            # استخراج الحالة الجديدة
            new_status = data.get('status') or data.get('approval_status')

            # لو لم تتغير الحالة أو لم تعد القيمة
            if not new_status or new_status == template.status:
                unchanged.append(template.id)
                continue

            # تحديث الحالة في قاعدة البيانات
            old_status = template.status
            template.status = new_status
            template.save(update_fields=['status'])

            updated.append({
                'id': template.id,
                'name': template.name,
                'old': old_status,
                'new': new_status
            })

        except Exception as e:
            print(f"❌ Exception for template {template.id}: {e}")
            continue

    # 5. إرجاع القائمة المحدثة الخاصة بهذه القناة فقط
    all_channel_templates = list(Template.objects.filter(channel=channel).values())
    
    return JsonResponse({
        'success': True, 
        'templates': all_channel_templates, 
        'updated': updated, 
        'unchanged': unchanged
    })


# views.py

# @csrf_exempt
# @require_http_methods(["GET"])
def get_whatsapp_templates(request):


    """
    جلب القوالب المعتمدة (APPROVED) فقط من حساب واتساب

    """
    user = request.user
    channel_id = request.GET.get('channel_id')

    if not channel_id:
        return JsonResponse({'success': False, 'error': 'Missing channel_id'}, status=400)

    channel = None
    if user.is_superuser or getattr(user, 'is_team_admin', False):
        channel = WhatsAppChannel.objects.filter(id=channel_id, owner=user).first()
    else:
        channel = WhatsAppChannel.objects.filter(id=channel_id, assigned_agents=user).first()

    if not channel:
        return JsonResponse({'success': False, 'error': 'Channel not found or permission denied'}, status=403)

    TOKEN = channel.access_token
    WABA = channel.business_account_id
    if not TOKEN or not WABA: # تأكد من وجود WhatsApp Business Account ID
        return JsonResponse({"error": "Missing Config"}, status=500)

    url = f"https://graph.facebook.com/v17.0/{WABA}/message_templates"
    params = {
        'status': 'APPROVED',
        'limit': 100,
        'access_token': TOKEN
    }

    try:
        response = requests.get(url, params=params)
        data = response.json()
        found = False
   
        
        if 'data' not in data:
            return JsonResponse({"error": "Failed to fetch templates", "details": data}, status=400)

        # تنظيف البيانات وإرسال المفيد فقط
        templates = []
        for t in data['data']:
            # نأخذ فقط القوالب التي تحتوي على body
            body_comp = next((c for c in t.get('components', []) if c['type'] == 'BODY'), None)
            if body_comp:
                templates.append({
                    'name': t['name'],
                    'language': t['language'],
                    'body': body_comp.get('text', ''),
                    'status': t['status']
                })

        return JsonResponse({"templates": templates})

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)



def get_target_channel(user, channel_id_param):
    """
    دالة ذكية لجلب القناة:
    1. تعالج حالة النص "null" أو "undefined".
    2. تتأكد من الصلاحيات.
    3. تعيد القناة الافتراضية إذا لم يتم تحديد قناة.
    4. تضمن إرجاع Model Object وليس Dict.
    """
    
    # 1. تنظيف المدخلات (التعامل مع "null" كنص)
    if not channel_id_param or channel_id_param == 'null' or channel_id_param == 'undefined':
        target_id = None
    else:
        target_id = channel_id_param

    # 2. تحديد نطاق البحث (QuerySet) بناءً على الصلاحية
    if user.is_superuser or getattr(user, 'is_team_admin', False):
        qs = WhatsAppChannel.objects.filter(owner=user)
    else:
        qs = WhatsAppChannel.objects.filter(assigned_agents=user)

    channel = None

    # 3. محاولة جلب القناة المحددة
    if target_id:
        # نستخدم filter().first() لضمان إرجاع كائن أو None (لا تستخدم .values هنا أبداً!)
        channel = qs.filter(id=target_id).first()

    # 4. إذا لم نجد قناة (أو لم يتم تحديد ID)، نأخذ الافتراضية (الأولى)
    if not channel:
        channel = qs.first()

    return channel





# from django.views.decorators.http import require_GET
# from django.http import JsonResponse
# import requests
 
# @require_GET

    """
    جلب القوالب المعتمدة (APPROVED) للقناة المحددة
    """
    user = request.user
    channel_id = request.GET.get('channel_id')
    
    # 1. جلب القناة والتحقق من الصلاحيات
    channel = get_target_channel(user, channel_id)
    if not channel:
        return JsonResponse({"error": "Channel not found or permission denied"}, status=403)

    # 2. استخدام بيانات القناة
    waba_id = channel.business_account_id
    access_token = channel.access_token
    api_version = getattr(channel, 'api_version', 'v18.0')

    if not waba_id or not access_token:
        return JsonResponse({"error": "Channel configuration missing (WABA/Token)"}, status=500)

    url = f"https://graph.facebook.com/{api_version}/{waba_id}/message_templates"
    params = {
        'status': 'APPROVED',
        'limit': 100,
        'access_token': access_token
    }

    try:
        response = requests.get(url, params=params)
        data = response.json()

        if 'data' not in data:
            return JsonResponse({"error": "Failed to fetch from Meta", "details": data}, status=400)

        # 3. تنظيف البيانات
        templates = []
        for t in data['data']:
            # استخراج نص الرسالة
            body_comp = next((c for c in t.get('components', []) if c['type'] == 'BODY'), None)
            
            templates.append({
                'name': t['name'],
                'language': t['language'],
                'category': t.get('category', 'UTILITY'),
                'body': body_comp.get('text', '') if body_comp else 'No body text',
                # نحتاج الهيكل لمعرفة إذا كان هناك متغيرات {{1}}
                'components': t.get('components', []) 
            })

        return JsonResponse({"templates": templates})

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)