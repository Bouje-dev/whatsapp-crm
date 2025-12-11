from asyncio.log import logger
import json
import re
import os
import tempfile
import subprocess
import mimetypes
from typing import Type
import requests
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_GET, require_POST
from django.utils import timezone
from django.core.files.base import ContentFile
from django.conf import settings
from django.db.models import Max, Q
from discount.models import Message, Template, Order , Contact, WhatsAppChannel, CustomUser
from django.contrib.auth.decorators import login_required
import logging

logger = logging.getLogger(__name__)
from .templaite import submit_template_to_meta
from .flow import find_automated_response, serialize_autoreply
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
import uuid
from django.core.files.storage import default_storage

 


@csrf_exempt
@require_http_methods(["POST"])
def upload_media_(request):
        # قبول الحقل باسم 'media' أو 'file'
        uploaded = request.FILES.get('media') or request.FILES.get('file')
        print("uploaded files "  , uploaded)
        if not uploaded:
            return JsonResponse({'success': False, 'error': 'No file uploaded'}, status=400)

        # توليد اسم فريد لتجنب التكرار
        filename = f"{uuid.uuid4().hex}_{uploaded.name}"
        subpath = os.path.join('uploads', filename)  # تحزين داخل uploads/

        # حفظ الملف باستخدام default_storage (يحترم إعدادات STORAGE_BACKEND)
        saved_path = default_storage.save(subpath, uploaded)

        # الحصول على URL (قد يكون نسبياً مثل /media/uploads/...)
        file_url = default_storage.url(saved_path)

        # تحويله إلى رابط كامل absolute URL
        absolute_url = request.build_absolute_uri(file_url)
       

        return JsonResponse({'success': True, 'url': absolute_url})

     
# "881753951677151"

# التوكن الخاص بك من Meta
ACCESS_TOKEN = getattr(settings, 'ACCESS_TOKEN', "EAALZBubBgmq0BP7ECHmEACY6YMB8nsV8MtxTQKwSexB3RqW9ZB3EkRdDp7MQnjuqCJHQ598lkQ9CQQmXTd2jZAI8NhGKyMLATmJgXbZAWKprwErSjANdMsTtduBBvqURZApEWlAqcYsgckaTLcWgYUHmzfFanu0oZANZC3H5zSj2fGjKZCm4oTTRpsjGbXy7zNwRbQZDZD")
# -----------test numer -------------- 
PHONE_NUMBER_ID = getattr(settings, 'PHONE_NUMBER_ID', "866281303235440")
VERIFY_TOKEN = getattr(settings, 'VERIFY_TOKEN', "token")


# ACCESS_TOKEN= "EAALZBubBgmq0BQKhYHFnHRhN6Y0UCM2sAwDrT7u2xZA4SJ4tSfFjyyIxFYqQh3HFoRSnxNVZBfIQ7zxqRqcZBNF89LLLTNVqMiPrlGm3SMIq35784XitLZCCMtmyHZB3oKhtsbCU7lI28lTz7idRpZCEgRUHzoH0x8uQ2cjd8ZBXCoTEhUngWnTSUXtT2OqA7ONgN0eTHcj5YeMJFDAhGc0SW8FkVWWZCpkK0K0Qk2gO5wt4jg3VWSX7dh7fpSRyRlqbknoFnj8FibCC0UZAFyT2uQlNV5zCd1dsw31wuJpwZDZD"
# MY_PHONE_ID =  "845008354611698"
# MY_ACCESS_TOKEN=  "EAALZBubBgmq0BP7ECHmEACY6YMB8nsV8MtxTQKwSexB3RqW9ZB3EkRdDp7MQnjuqCJHQ598lkQ9CQQmXTd2jZAI8NhGKyMLATmJgXbZAWKprwErSjANdMsTtduBBvqURZApEWlAqcYsgckaTLcWgYUHmzfFanu0oZANZC3H5zSj2fGjKZCm4oTTRpsjGbXy7zNwRbQZDZD"
# API_VER = 'v22.0'
# ---------------------
# Utility Functions
# ---------------------


def convert_audio_to_ogg(input_path):
    """
    تحويل صارم لملفات الصوت (خاصة القادمة من Safari)
    لضمان قبولها كـ Voice Note في واتساب.
    """
    try:
        # إنشاء مسار للملف الناتج
        fd, output_path = tempfile.mkstemp(suffix='.ogg')
        os.close(fd)
        
        # أمر التحويل (إعدادات مخصصة لواتساب)
        command = [
            'ffmpeg', '-y', 
            '-i', input_path, 
            
            # 1. إجبار الكوديك على OPUS
            '-c:a', 'libopus', 
            
            # 2. إزالة أي مسار فيديو (مهم جداً لملفات Safari mp4)
            '-vn', 
            
            # 3. إزالة الميتاداتا (لتقليل الحجم ومنع المشاكل)
            '-map_metadata', '-1',
            
            # 4. جعل الصوت قناة واحدة (Mono) لأن الملاحظات الصوتية تكون Mono
            '-ac', '1', 
            
            # 5. تحديد تردد العينة (Sample Rate) القياسي
            '-ar', '16000', 
            
            # 6. إعدادات الضغط المناسبة للصوت
            '-b:a', '16k', 
            '-application', 'voip',
            
            output_path
        ]
        
        # تنفيذ الأمر وإخفاء المخرجات
        subprocess.check_call(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            return output_path
        return None
    except Exception as e:
        print(f"❌ Error converting audio: {e}")
        return None
    


def download_whatsapp_media(media_id, access_token):
    """
    تحميل الوسائط من واتساب
    """
    try:
        # الحصول على رابط التحميل
        media_url = f"https://graph.facebook.com/v17.0/{media_id}/"
        headers = {'Authorization': f'Bearer {access_token}'}
        
        response = requests.get(media_url, headers=headers)
        if response.status_code != 200:
            return None
            
        media_data = response.json()
        download_url = media_data.get('url')
        
        if not download_url:
            return None
            
        # تحميل الملف
        download_response = requests.get(download_url, headers=headers)
        if download_response.status_code == 200:
            return download_response.content
        else:
            return None
            
    except Exception as e:
        print(f"Media download error: {e}")
        return None

def process_incoming_media(msg, access_token):
    """
    معالجة الوسائط الواردة من واتساب
    """
    try:
        media_type = None
        media_id = None
        media_content = None
        
        # تحديد نوع الوسائط
        for media_key in ['image', 'audio', 'video', 'document']:
            if media_key in msg:
                media_type = media_key
                media_id = msg[media_key]['id']
                break
        
        if not media_id:
            return None, None, None
            
        # تحميل الوسائط
        media_content = download_whatsapp_media(media_id, access_token)
        if not media_content:
            return None, None, None
            
        # تحديد امتداد الملف
        extensions = {
            'image': '.jpg',
            'audio': '.ogg',
            'video': '.mp4',
            'document': '.pdf'
        }
        
        extension = extensions.get(media_type, '.bin')
        filename = f"{media_id}{extension}"
        
        return media_type, media_content, filename
        
    except Exception as e:
        print(f"Media processing error: {e}")
        return None, None, None

def send_automated_response(recipient, responses):
    """
    إرسال سلسلة ردود تلقائية إلى المستخدم عبر واتساب
    """
    try:
        if not ACCESS_TOKEN or not PHONE_NUMBER_ID:
            print("❌ WhatsApp credentials not configured")
            return False

        if not responses:
            print("❌ No responses to send")
            return False
            
        # إذا كانت responses ليست قائمة، نجعلها قائمة
        if not isinstance(responses, list):
            responses = [responses]

        print(f"📤 Preparing to send {len(responses)} responses to {recipient}")
        
        headers = {
            'Authorization': f'Bearer {ACCESS_TOKEN}',
            'Content-Type': 'application/json'
        }

        for i, response_data in enumerate(responses):
            response_type = response_data.get('type', 'text')
            
            # معالجة التأخير
            if response_type == 'delay':
                delay = response_data.get('duration', 0)
                if delay > 0:
                    print(f"⏳ Delaying for {delay} seconds before next message")
                    import time
                    time.sleep(delay)
                continue
            
            # تطبيق التأخير المحدد في الرد
            delay = response_data.get('delay', 0)
            if delay > 0:
                print(f"⏳ Delaying for {delay} seconds")
                import time
                time.sleep(delay)
            
            if response_type == 'text':
                content = response_data.get('content', '').strip()
                
                if not content:
                    print("❌ Cannot send empty text message")
                    continue
                    
                data = {
                    "messaging_product": "whatsapp",
                    "to": recipient,
                    "text": {"body": content}
                }
                print(f"✅ Prepared text message {i+1}: {content}")
                
            elif response_type in ['image', 'audio', 'video', 'document']:
                media_url = response_data.get('media_url')
                content = response_data.get('content', '').strip()
                
                if not media_url:
                    print("❌ Media URL is required for media messages")
                    continue
                    
                data = {
                    "messaging_product": "whatsapp", 
                    "to": recipient,
                    "type": response_type,
                    response_type: {
                        "link": media_url
                    }
                }
                
                if content:
                    data[response_type]['caption'] = content
                    print(f"✅ Prepared media message {i+1} with caption: {content}")
                else:
                    print(f"✅ Prepared media message {i+1} without caption")
                    
            else:
                print(f"❌ Unknown response type: {response_type}")
                continue

            # إرسال الطلب إلى واتساب API
            print(f"🚀 Sending message {i+1} to WhatsApp API...")
            response = requests.post(
                f'https://graph.facebook.com/v17.0/{PHONE_NUMBER_ID}/messages',
                headers=headers,
                json=data,
                timeout=30
            )

            if response.status_code == 200:
                print(f"✅ Response {i+1} sent successfully to {recipient}")
                
                # حفظ الرسالة المرسلة في قاعدة البيانات
                Message.objects.create(
                    sender=recipient,
                    body=response_data.get('content', ''),
                    is_from_me=True,
                    media_type=response_type if response_type != 'text' else None
                )
                
            else:
                print(f"❌ Failed to send response {i+1}: {response.status_code}")
                print(f"❌ Response details: {response.text}")
                # نستمر في إرسال الردود التالية حتى لو فشل أحدها
                
            # تأخير بسيط بين الرسائل لتجنب rate limiting
            import time
            time.sleep(1)
            
        print(f"✅ All responses sent successfully to {recipient}")
        return True

    except Exception as e:
        print(f"❌ Error sending automated response: {e}")
        return False


def validate_whatsapp_webhook(request):
    """
    التحقق من صحة طلب الويب هوك
    """
    try:
        # التحقق من التوقيع (إذا كان مفعلاً)
        signature = request.META.get('HTTP_X_HUB_SIGNATURE_256', '')
        if signature:
            # تنفيذ التحقق من التوقيع هنا
            pass
            
        # التحقق من بنية البيانات
        data = json.loads(request.body.decode('utf-8'))
        required_fields = ['entry', 'object']
        
        for field in required_fields:
            if field not in data:
                return False, "Invalid webhook structure"
                
        return True, "Valid"
        
    except Exception as e:
        return False, str(e)

def rate_limit_check(phone_number, max_requests=10, time_window=60):
    """
    التحقق من معدل الطلبات لمنع الإساءة
    """
    from django.core.cache import cache
    
    cache_key = f"rate_limit_{phone_number}"
    current_time = timezone.now()
    
    requests = cache.get(cache_key, [])
    
    # إزالة الطلبات القديمة
    requests = [req_time for req_time in requests 
               if (current_time - req_time).seconds < time_window]
    
    if len(requests) >= max_requests:
        return False
        
    requests.append(current_time)
    cache.set(cache_key, requests, time_window)
    return True

def save_incoming_message(msg):
    """
    حفظ الرسالة الواردة في قاعدة البيانات
    """
    try:
        sender = msg["from"]
        message_type = msg.get("type", "text")
        body = msg.get("text", {}).get("body", "")
        message_id = msg.get("id")
        timestamp = msg.get("timestamp")
        
        # معالجة الوسائط
        media_type = None
        media_id = None
        media_file = None
        
        for media_key in ['image', 'audio', 'video', 'document']:
            if media_key in msg:
                media_type = media_key
                media_id = msg[media_key]['id']
                break
                
        # حفظ في قاعدة البيانات
        # Normalize timestamp: convert epoch seconds or ISO string to an aware datetime
        parsed_timestamp = None
        try:
            import datetime as _dt
            if timestamp is not None:
                # numeric epoch seconds (string or int)
                if isinstance(timestamp, (int, float)) or (isinstance(timestamp, str) and re.fullmatch(r'\d+', timestamp)):
                    parsed_timestamp = _dt.datetime.fromtimestamp(int(timestamp), tz=_dt.timezone.utc)
                else:
                    # try ISO format and make it aware if naive
                    try:
                        parsed_timestamp = _dt.datetime.fromisoformat(timestamp)
                        if parsed_timestamp.tzinfo is None:
                            parsed_timestamp = timezone.make_aware(parsed_timestamp, timezone.get_current_timezone())
                    except Exception:
                        parsed_timestamp = None
        except Exception:
            parsed_timestamp = None

        message_obj = Message.objects.create(
            sender=sender,
            body=body,
            is_from_me=False,
            media_type=media_type,
            media_id=media_id,
            message_id=message_id,
            timestamp=parsed_timestamp
        )

        contact_data = msg['entry'][0]['changes'][0]['value']['contacts'][0]
        phone = contact_data.get('wa_id')
        name = contact_data.get('profile', {}).get('name', '')

        # جلب أو إنشاء Contact
        contact, created = Contact.objects.get_or_create(phone=phone)

        # تحديث الاسم فقط إذا كان جديد أو غير موجود سابقاً
        if name and contact.name != name:
            contact.name = name
            contact.profile_picture = 'https://cdn.pixabay.com/photo/2023/02/18/11/00/icon-7797704_640.png'


        # تحديث آخر تفاعل
        contact.last_interaction = timezone.now()

        # تحديث آخر ظهور
        contact.last_seen = timezone.now()

        contact.save()
        
        # معالجة الوسائط إذا وجدت
        if media_id and ACCESS_TOKEN:
            media_content = download_whatsapp_media(media_id, ACCESS_TOKEN)
            if media_content:
                filename = f"{media_id}_{media_type}.{get_media_extension(media_type)}"
                message_obj.media_file.save(filename, ContentFile(media_content))
                message_obj.save()
                
        return message_obj
        
    except Exception as e:
        print(f"❌ Error saving message: {e}")
        return None

def get_media_extension(media_type):
    """
    الحصول على امتداد الملف بناءً على نوع الوسائط
    """
    extensions = {
        'image': 'jpg',
        'audio': 'ogg', 
        'video': 'mp4',
        'document': 'pdf'
    }
    return extensions.get(media_type, 'bin')


def process_messages(messages):
    """
    معالجة الرسائل الواردة - محدثة
    """
    for msg in messages:
        try:
            sender = msg["from"]
            message_type = msg.get("type", "text")
            body = msg.get("text", {}).get("body", "")
            
            print(f"📩 Received message from {sender}: '{body}' (type: {message_type})")
            
            # حفظ الرسالة
            message_obj = save_incoming_message(msg)
            
            # البحث عن رد تلقائي
            # auto_responses = find_automated_response(sender, body, message_type)
            from .flow import get_matching_flow, execute_flow

            flow = get_matching_flow(body)
            output = None

            if flow:
                output = execute_flow(flow, sender)
                if output :

                    for msg in output:
                        send_automated_response(sender, msg)
                print("DEBUG execute_flow output:", output , flow)


            else:
                print("ℹ️ No automated response found")
                
        except Exception as e:
            print(f"❌ Error processing message: {e}")
            import traceback
            traceback.print_exc()


# ---------------------
# Views
# ---------------------
@require_GET
def get_contacts(request):
    contacts = [
        {"name": "John Doe", "phone": "212612638500", "snippet": "Hey, how are you?"},
        {"name": "Jane Smith", "phone": "+0987654321", "snippet": "Let's catch up soon!"},
    ]
    return JsonResponse(contacts, safe=False)

@require_GET
def get_messages(request):
    phone = request.GET.get("phone")
    print("Phone number received:", phone)
    # جلب الرسائل من قاعدة البيانات
    messages = Message.objects.filter(sender=phone).order_by("timestamp")
    print("Messages fetched:", messages)
    # تجهيز البيانات بالشكل المطلوب
    data = {
        "messages": [
            {
                "text": msg.body,
                "time": msg.timestamp.strftime("%H:%M"),
                "fromMe": msg.is_from_me
            }
            for msg in messages
        ]
    }

    return JsonResponse(data)

def whatssap(request):
    messages = Message.objects.all()
    print("message" , messages)
    return render(request, "tracking.html", {"senders": messages})

# صفحة الدردشة
def chat_view(request):
    messages = Message.objects.order_by("timestamp")
    return render(request, "whatssap/chat.html", {"messages": messages})

@csrf_exempt
def whatsapp_webhook(request):
    """
    ويب هوك واتساب محسن
    """
    print("GET webhook verification")
    if request.method == "GET":
        mode = request.GET.get("hub.mode", "subscribe")
        token = request.GET.get("hub.verify_token", "my_verify_token")
        challenge = request.GET.get("hub.challenge")
        if mode == "subscribe" and token == VERIFY_TOKEN:
            return HttpResponse(challenge)
        else:
            return HttpResponse(status=403)
                
        
    elif request.method == "POST":
        try:
   
            data = json.loads(request.body.decode("utf-8"))
            print("📨 Received WhatsApp webhook ," , data)
            
            for entry in data.get("entry", []):
                for change in entry.get("changes", []):
                    value = change.get("value", {})
                    
                    # معالجة الرسائل
                    if 'messages' in value:
                        process_messages(value.get("messages", []))
                            
                    from channels.layers import get_channel_layer
                    from asgiref.sync import async_to_sync 

                    channel_layer = get_channel_layer()
                    async_to_sync(channel_layer.group_send)(
                        "webhook_events",
                        {
                            "type":"broadcast_event",
                            "message":value.get("messages", []),
                            "sender": value.get("phone", [])
                        }
                    )
                    
                    
                    # معالجة حالة الرسائل
                    if 'statuses' in value:
                        process_message_statuses(value.get("statuses", []))
            
            return HttpResponse("EVENT_RECEIVED", status=200)
            
        except Exception as e:
            print(f"❌ Webhook error: {e}")
            return HttpResponse("ERROR", status=500)

def process_message_statuses(statuses):
    """
    معالجة حالات الرسائل (مثل تم التسليم، تم القراءة)
    """
    for status in statuses:
        try:
            message_id = status.get('id')
            status_value = status.get('status')
            recipient_id = status.get('recipient_id')
            timestamp = status.get('timestamp')
            
            print(f"📊 Message status: {message_id} -> {status_value}")
            
            # تحديث حالة الرسالة في قاعدة البيانات إذا لزم الأمر
            if message_id:
                try:
                    message = Message.objects.get(message_id=message_id)
                    message.status = status_value
                    message.status_timestamp = timestamp
                    message.save()
                except Message.DoesNotExist:
                    pass
                    
        except Exception as e:
            print(f"❌ Error processing message status: {e}")
from datetime import timedelta
def can_send_message(to_phone):
    """
    يتحقق إذا كان آخر تواصل مع العميل لم يتجاوز 24 ساعة
    """
    try:
        # جلب آخر رسالة مستلمة من العميل
        last_incoming = Message.objects.filter(sender=to_phone, is_from_me=False).order_by('-created_at').first()
        if not last_incoming:
            return False, "you can not send msg to this user"
        
        
        # التحقق من مرور 24 ساعة
        if timezone.now() - last_incoming.created_at > timedelta(hours=24):
            return False, "Message failed to send because more than 24 hours have passed since the customer last replied to this number."
        
        return True, ""
    except Exception as e:
        print("Error checking last incoming message:", e)
        return False, "Internal error checking last conversation."
    

def get_last_message(request):
    phone = request.GET.get("phone")
    
    # جلب آخر رسالة من قاعدة البيانات
    last_message = Message.objects.filter(sender=phone,is_from_me=False).order_by("-timestamp").first()
  
    if not last_message:
       return JsonResponse({
                    "status": 400,
                    "error": "message not allowed",
                    "reason": "you can not send msg to this user"
                } ,status =400 )
    if timezone.now() - last_message.created_at > timedelta(hours=24):
        return JsonResponse({
                    "status": 400,
                    "error": "message not allowed",
                    "reason": "Message failed to send because more than 24 hours have passed since the customer last replied to this number."
                } ,status =400 )
    
    
    else:
        return JsonResponse({"status": 200,})

# @csrf_exempt
# def send_message(request):
#     """
#     إرسال رسالة (نص أو ميديا) مع معالجة خاصة للصوت القادم من Safari/iPhone.
#     """
#     if request.method != "POST":
#         return JsonResponse({"error": "Method not allowed"}, status=405)

#     if not ACCESS_TOKEN or not PHONE_NUMBER_ID:
#         return JsonResponse({"error": "Server configuration error: Missing Token or Phone ID"}, status=500)

#     # تهيئة المتغيرات
#     media_id = None
#     media_type = "text"
#     body = ""
#     to = None
#     uploaded_file = None
#     temp_input_path = None
#     temp_converted_path = None
#     saved_local_bytes = None
#     saved_mime = None
#     saved_filename = None

#     # دالة تنظيف المسارات المؤقتة
#     def _cleanup_paths(*paths):
#         for p in paths:
#             try:
#                 if p and os.path.exists(p):
#                     os.remove(p)
#             except Exception:
#                 pass

#     try:
#         content_type = request.META.get("CONTENT_TYPE", "") or ""
        
#         # ---------------------------------------------------
#         # 1. حالة رفع ملف (Multipart/Form-Data) - هنا التعديل
#         # ---------------------------------------------------
#         if content_type.startswith("multipart/form-data"):
#             body = request.POST.get("body", "") or ""
#             to = request.POST.get("to") or request.POST.get("phone")
#             media_type = request.POST.get("type", "text")
#             uploaded_file = request.FILES.get("file")

#             # التحقق من الصلاحية (الدالة الخاصة بك)
#             # can_send, reason = can_send_message(to)
#             # if not can_send:
#             #     return JsonResponse({"status": 400, "error": reason}, status=400)

#             if not to:
#                 return JsonResponse({"error": "missing 'to' field"}, status=400)

#             if uploaded_file:
#                 saved_filename = uploaded_file.name
#                 saved_mime = uploaded_file.content_type or mimetypes.guess_type(saved_filename)[0]
                
#                 # حفظ الملف الخام القادم من المتصفح مؤقتاً
#                 try:
#                     if hasattr(uploaded_file, "temporary_file_path"):
#                         temp_input_path = uploaded_file.temporary_file_path()
#                     else:
#                         fd, temp_path = tempfile.mkstemp(suffix=os.path.splitext(saved_filename)[1] or "")
#                         os.close(fd)
#                         with open(temp_path, "wb") as out_f:
#                             for chunk in uploaded_file.chunks():
#                                 out_f.write(chunk)
#                         temp_input_path = temp_path
#                 except Exception as e:
#                     _cleanup_paths(temp_input_path)
#                     return JsonResponse({"error": "failed to save uploaded file"}, status=500)

#                 # ------------------------------------------------------
#                 # [الحل الجذري] معالجة الصوت (Safari Fix)
#                 # ------------------------------------------------------
#                 if media_type == "audio":
#                     print(f"🎤 Audio detected ({saved_filename}). Forcing conversion to OGG...")
                    
#                     # لا نثق في الامتداد القادم من المتصفح، نحول دائماً
#                     temp_converted_path = convert_audio_to_ogg(temp_input_path)
                    
#                     if temp_converted_path:
#                         # نجح التحويل: نعتمد الملف الجديد
#                         temp_input_path = temp_converted_path 
#                         saved_filename = "voice_message.ogg" # اسم جديد ونظيف
#                         saved_mime = "audio/ogg"             # النوع الصحيح
#                         print("✅ Conversion successful.")
#                     else:
#                         print("⚠️ Conversion failed, falling back to original file.")
#                 # ------------------------------------------------------

#                 # رفع الملف إلى WhatsApp Media Endpoint
#                 fb_upload_url = f"https://graph.facebook.com/v22.0/{PHONE_NUMBER_ID}/media"
#                 params = {"messaging_product": "whatsapp", "access_token": ACCESS_TOKEN}
                
#                 # تخمين MIME إذا لم يكن محدداً
#                 if not saved_mime:
#                     saved_mime = mimetypes.guess_type(saved_filename)[0] or "application/octet-stream"

#                 try:
#                     with open(temp_input_path, "rb") as fh:
#                         files = {"file": (saved_filename, fh, saved_mime)}
#                         fb_res = requests.post(fb_upload_url, params=params, files=files, timeout=80)
#                 except Exception as e:
#                     _cleanup_paths(temp_input_path, temp_converted_path)
#                     return JsonResponse({"error": "failed to upload media to whatsapp", "details": str(e)}, status=502)

#                 if fb_res.status_code not in (200, 201):
#                     _cleanup_paths(temp_input_path, temp_converted_path)
#                     return JsonResponse({"error": "failed upload to whatsapp media", "details": fb_res.text}, status=502)

#                 fb_json = fb_res.json()
#                 media_id = fb_json.get("id")
                
#                 if not media_id:
#                     _cleanup_paths(temp_input_path, temp_converted_path)
#                     return JsonResponse({"error": "no media_id returned by whatsapp"}, status=502)

#                 # قراءة البايتات للحفظ المحلي لاحقاً (في قاعدة البيانات)
#                 try:
#                     with open(temp_input_path, "rb") as fh:
#                         saved_local_bytes = fh.read()
#                 except:
#                     saved_local_bytes = None

#         # ---------------------------------------------------
#         # 2. حالة JSON (بدون رفع ملف، فقط إرسال)
#         # ---------------------------------------------------
#         elif media_type == "template":
#             # { "type": "template", "template": { "name": "...", "language": "...", "components": [...] } }
#             template_data = payload.get("template", {})
#             send_payload["type"] = "template"
#             send_payload["template"] = {
#                 "name": template_data.get("name"),
#                 "language": {"code": template_data.get("language", "ar")},
#                 "components": template_data.get("components", [])
#             }
#         else:
#             payload = json.loads(request.body.decode("utf-8") or "{}")
#             body = payload.get("body", "") or ""
#             to = payload.get("to")
#             media_type = payload.get("media_type", "text")
#             media_id = payload.get("media_id")
            
#             if not to:
#                 return JsonResponse({"error": "missing 'to' field"}, status=400)
            
#             # can_send, reason = can_send_message(to)
#             # if not can_send:
#             #     return JsonResponse({"status": 400, "error": reason}, status=400)

#     except Exception as e:
#         _cleanup_paths(temp_input_path, temp_converted_path)
#         return JsonResponse({"error": "bad request", "details": str(e)}, status=400)

#     # ---------------------------------------------------
#     # 3. إرسال الرسالة النهائية إلى العميل
#     # ---------------------------------------------------
#     try:
#         send_payload = {"messaging_product": "whatsapp", "to": to}

#         if (not media_type) or media_type == "text":
#             send_payload["type"] = "text"
#             send_payload["text"] = {"body": body or ""}
            
#         elif media_type in ("image", "audio", "video", "document"):
#             if not media_id:
#                 _cleanup_paths(temp_input_path, temp_converted_path)
#                 return JsonResponse({"error": "missing media_id"}, status=400)
                
#             send_payload["type"] = media_type
#             send_payload[media_type] = {"id": media_id}
            
#             # هام: الصوت لا يقبل caption
#             if body and media_type != "audio":
#                 send_payload[media_type]["caption"] = body
#         else:
#             _cleanup_paths(temp_input_path, temp_converted_path)
#             return JsonResponse({"error": "unsupported media_type"}, status=400)

#         # تنفيذ الإرسال
#         url = f"https://graph.facebook.com/v22.0/{PHONE_NUMBER_ID}/messages"
#         headers = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}
#         r = requests.post(url, headers=headers, json=send_payload, timeout=30)
        
#         print("WhatsApp API response:", r.status_code)

#     except Exception as e:
#         _cleanup_paths(temp_input_path, temp_converted_path)
#         return JsonResponse({"error": "failed to contact whatsapp api", "details": str(e)}, status=502)

#     # ---------------------------------------------------
#     # 4. حفظ السجل في قاعدة البيانات (Message Model)
#     # ---------------------------------------------------
#     saved_message = None
#     try:
#         if r.status_code in (200, 201):
#             msg_kwargs = {
#                 "sender": to,
#                 "body": body or "",
#                 "is_from_me": True,
#             }
#             if media_type and media_type != "text":
#                 msg_kwargs["media_type"] = media_type
#             if media_id:
#                 msg_kwargs["media_id"] = media_id

#             saved_message = Message.objects.create(**msg_kwargs)

#             # حفظ الملف محلياً إذا كان متوفراً (حالة الرفع)
#             if saved_local_bytes and hasattr(saved_message, "media_file"):
#                 try:
#                     # تحديد الامتداد الصحيح للحفظ
#                     ext = ""
#                     if saved_mime:
#                         if "ogg" in saved_mime: ext = ".ogg"
#                         elif "mp4" in saved_mime: ext = ".mp4"
#                         elif "jpeg" in saved_mime or "jpg" in saved_mime: ext = ".jpg"
#                         elif "png" in saved_mime: ext = ".png"
#                         elif "pdf" in saved_mime: ext = ".pdf"
                    
#                     final_filename = f"{media_id or 'media'}{ext}"
#                     saved_message.media_file.save(final_filename, ContentFile(saved_local_bytes), save=True)
#                 except Exception as ex_save:
#                     print("Failed to save local media file:", ex_save)

#             # تحديث وقت الإنشاء
#             if hasattr(saved_message, "created_at") and not saved_message.created_at:
#                 saved_message.created_at = timezone.now()
#                 saved_message.save(update_fields=["created_at"])

#     except Exception as e:
#         print("Error saving Message record:", e)

#     # تنظيف نهائي
#     _cleanup_paths(temp_input_path, temp_converted_path)

#     return JsonResponse({
#         "status": getattr(r, "status_code", 500),
#         "whatsapp_response": r.text if hasattr(r, "text") else str(r),
#         "saved_message_id": getattr(saved_message, "id", None),
#         "media_id": media_id
#     }, status=200 if getattr(r, "status_code", 500) in (200, 201) else 500)


# def send_message(request):
#     """
#     نقطة النهاية الموحدة لإرسال الرسائل عبر واتساب.
#     تدعم: النصوص، الوسائط (مع التحويل)، والقوالب.
#     """
#     if request.method != "POST":
#         return JsonResponse({"error": "Method not allowed"}, status=405)
#     channel_id = request.POST.get("channel_id")
#     right_channe = get_target_channel( request.user , channel_id)
#     ACCESS_TOKEN = right_channe.access_token
#     PHONE_NUMBER_ID = right_channe.phone_number_id
#     business_account_id = right_channe.business_account_id
#     if not ACCESS_TOKEN or not PHONE_NUMBER_ID:
#         return JsonResponse({"error": "Server configuration error: Missing Token or ID"}, status=500)

#     # --- تعريف المتغيرات لضمان عدم حدوث UnboundLocalError ---
#     media_id = None
#     media_type = "text"
#     body = ""
#     to = None 
#     uploaded_file = None
#     temp_input_path = None
#     temp_converted_path = None
#     saved_local_bytes = None
#     saved_mime = None
#     saved_filename = None
#     template_data = None
#     r = None # استجابة واتساب

#     # دالة تنظيف محلية
#     def _cleanup_paths(*paths):
#         for p in paths:
#             try:
#                 if p and os.path.exists(p):
#                     os.remove(p)
#             except Exception:
#                 pass

#     try:
#         content_type = request.META.get("CONTENT_TYPE", "") or ""
        
#         # ---------------------------------------------------
#         # الحالة الأولى: رفع ملف (Multipart/Form-Data)
#         # ---------------------------------------------------
#         if content_type.startswith("multipart/form-data"):
#             body = request.POST.get("body", "")
#             to = request.POST.get("to") or request.POST.get("phone")
#             media_type = request.POST.get("type", "text")
#             uploaded_file = request.FILES.get("file")

#             if not to:
#                 return JsonResponse({"error": "missing 'to' field"}, status=400)

#             if uploaded_file:
#                 saved_filename = uploaded_file.name
#                 saved_mime = uploaded_file.content_type or mimetypes.guess_type(saved_filename)[0]
                
#                 # حفظ الملف مؤقتاً
#                 try:
#                     if hasattr(uploaded_file, "temporary_file_path"):
#                         temp_input_path = uploaded_file.temporary_file_path()
#                     else:
#                         fd, temp_path = tempfile.mkstemp(suffix=os.path.splitext(saved_filename)[1] or "")
#                         os.close(fd)
#                         with open(temp_path, "wb") as out_f:
#                             for chunk in uploaded_file.chunks():
#                                 out_f.write(chunk)
#                         temp_input_path = temp_path
#                 except Exception as e:
#                     _cleanup_paths(temp_input_path)
#                     return JsonResponse({"error": "failed to save uploaded file"}, status=500)

#                 # --- معالجة الصوت (Safari Fix) ---
#                 if media_type == "audio":
#                     print(f"🎤 Audio detected ({saved_filename}). Converting...")
#                     temp_converted_path = convert_audio_to_ogg(temp_input_path)
                    
#                     if temp_converted_path:
#                         temp_input_path = temp_converted_path 
#                         saved_filename = "voice_message.ogg"
#                         saved_mime = "audio/ogg"
#                     else:
#                         print("⚠️ Conversion failed, using original file.")

#                 # --- رفع الملف لواتساب ---
#                 fb_upload_url = f"https://graph.facebook.com/v22.0/{PHONE_NUMBER_ID}/media"
#                 params = {"messaging_product": "whatsapp", "access_token": ACCESS_TOKEN}
                
#                 if not saved_mime:
#                     saved_mime = mimetypes.guess_type(saved_filename)[0] or "application/octet-stream"

#                 try:
#                     with open(temp_input_path, "rb") as fh:
#                         files = {"file": (saved_filename, fh, saved_mime)}
#                         fb_res = requests.post(fb_upload_url, params=params, files=files, timeout=80)
#                 except Exception as e:
#                     _cleanup_paths(temp_input_path, temp_converted_path)
#                     return JsonResponse({"error": "upload connection failed", "details": str(e)}, status=502)

#                 if fb_res.status_code not in (200, 201):
#                     _cleanup_paths(temp_input_path, temp_converted_path)
#                     return JsonResponse({"error": "whatsapp upload rejected", "details": fb_res.text}, status=502)

#                 fb_json = fb_res.json()
#                 media_id = fb_json.get("id")
                
#                 # قراءة الملف للحفظ المحلي
#                 try:
#                     with open(temp_input_path, "rb") as fh:
#                         saved_local_bytes = fh.read()
#                 except:
#                     saved_local_bytes = None

#         # ---------------------------------------------------
#         # الحالة الثانية: JSON (نصوص أو قوالب)
#         # ---------------------------------------------------
#         else:
#             payload = json.loads(request.body.decode("utf-8") or "{}")
#             to = payload.get("to")
#             media_type = payload.get("media_type", "text")
#             print('😐👀 ,' , payload)
            
#             if not to:
#                 return JsonResponse({"error": "missing 'to' field"}, status=400)

#             if media_type == "template":
#                 template_data = payload.get("template")
                
#             else:
#                 body = payload.get("body", "")
#                 media_id = payload.get("media_id")

#     except Exception as e:
#         _cleanup_paths(temp_input_path, temp_converted_path)
#         return JsonResponse({"error": "request processing error", "details": str(e)}, status=400)

#     # ---------------------------------------------------
#     # 3. بناء بايلود الإرسال النهائي (WhatsApp Payload)
#     # ---------------------------------------------------
#     try:
#         send_payload = {"messaging_product": "whatsapp", "to": to}

#         # أ. نص
#         if (not media_type) or media_type == "text":
#             send_payload["type"] = "text"
#             send_payload["text"] = {"body": body or ""}
            
#         # ب. وسائط
#         elif media_type in ("image", "audio", "video", "document"):
#             if not media_id:
#                 _cleanup_paths(temp_input_path, temp_converted_path)
#                 return JsonResponse({"error": "missing media_id"}, status=400)
                
#             send_payload["type"] = media_type
#             send_payload[media_type] = {"id": media_id}
            
#             # الصوت لا يقبل caption
#             if body and media_type != "audio":
#                 send_payload[media_type]["caption"] = body

#         # ج. قوالب (Templates) - [مصححة]
#         elif media_type == "template":
#             print('template_data' , template_data)
#             if not template_data:
#                 return JsonResponse({"error": "missing template data"}, status=400)
            
#             # معالجة اللغة (تحويل النص إلى كائن)
#             raw_lang = template_data.get("language")
#             lang_code = "en" # افتراضي
#             print('to' , to)

#             if isinstance(raw_lang, str):
#                 lang_code = raw_lang
#             elif isinstance(raw_lang, dict):
#                 lang_code = raw_lang.get("code", "en")
            
#             send_payload["type"] = "template"
#             send_payload["template"] = {
#                 "name": template_data.get("name"),
#                 "language": {
#                     "code": lang_code,
#                     "policy": "deterministic"
#                 },
#                 "components": template_data.get("components", [])
#             }

#         else:
#             _cleanup_paths(temp_input_path, temp_converted_path)
#             return JsonResponse({"error": f"unsupported type: {media_type}"}, status=400)

#         # ---------------------------------------------------
#         # 4. إرسال الطلب إلى واتساب
#         # ---------------------------------------------------
#         url = f"https://graph.facebook.com/v22.0/{PHONE_NUMBER_ID}/messages"
#         headers = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}
        
#         r = requests.post(url, headers=headers, json=send_payload, timeout=30)
        
#         print(f"WhatsApp Response: {r.status_code} - {r.text}")

#     except Exception as e:
#         _cleanup_paths(temp_input_path, temp_converted_path)
#         return JsonResponse({"error": "api connection failed", "details": str(e)}, status=502)

#     # ---------------------------------------------------
#     # 5. حفظ السجل في قاعدة البيانات
#     # ---------------------------------------------------
#     saved_message_id = None
    
#     # نتحقق من نجاح الإرسال قبل الحفظ
#     status_code = getattr(r, "status_code", 500)
    
#     if status_code in (200, 201):
#         try:
#             msg_kwargs = {
#                 "sender": to,
#                 "is_from_me": True,
#             }
            
#             # تحديد محتوى الرسالة للحفظ
#             if media_type == "template":
#                 tpl_name = template_data.get('name', 'Template')
#                 msg_kwargs["body"] = f"[Template: {tpl_name}]"
#                 # إذا كان الموديل يقبل نوع 'template' ضعه، وإلا ضعه 'text'
#                 # msg_kwargs["media_type"] = "template" 
#             else:
#                 msg_kwargs["body"] = body or ""
#                 if media_type != "text":
#                     msg_kwargs["media_type"] = media_type
#                 if media_id:
#                     msg_kwargs["media_id"] = media_id

#             # إنشاء الرسالة
#             saved_message = Message.objects.create(**msg_kwargs)
#             saved_message_id = saved_message.id

#             # حفظ الملف محلياً إذا وجد
#             if saved_local_bytes and hasattr(saved_message, "media_file"):
#                 try:
#                     ext = ""
#                     if saved_mime:
#                         if "ogg" in saved_mime: ext = ".ogg"
#                         elif "mp4" in saved_mime: ext = ".mp4"
#                         elif "jpeg" in saved_mime or "jpg" in saved_mime: ext = ".jpg"
#                         elif "png" in saved_mime: ext = ".png"
#                         elif "pdf" in saved_mime: ext = ".pdf"
                    
#                     fname = f"{media_id or 'file'}{ext}"
#                     saved_message.media_file.save(fname, ContentFile(saved_local_bytes), save=True)
#                 except Exception as ex_save:
#                     print("Error saving local file:", ex_save)

#             # تحديث الوقت
#             if hasattr(saved_message, "created_at") and not saved_message.created_at:
#                 saved_message.created_at = timezone.now()
#                 saved_message.save()

#         except Exception as e:
#             print("Error saving to DB:", e)
#             # لا نوقف الرد لأن الرسالة أرسلت بالفعل للعميل

#     # تنظيف نهائي
#     _cleanup_paths(temp_input_path, temp_converted_path)

#     # الرد النهائي للفرونت اند
#     return JsonResponse({
#         "status": status_code,
#         "whatsapp_response": r.text if hasattr(r, "text") else str(r),
#         "saved_message_id": saved_message_id,
#         "media_id": media_id
#     }, status=200 if status_code in (200, 201) else 500)




import json
import requests
import mimetypes
import os
import tempfile
from django.http import JsonResponse
from django.core.files.base import ContentFile
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
 
 

@csrf_exempt # إذا كنت تستخدمها كـ API خارجي أحياناً
def send_message(request):
    """
    نقطة نهاية متخصصة لإرسال القوالب (Templates) ورفع الوسائط (Media).
    الرسائل النصية العادية يجب أن تمر عبر WebSocket.
    """
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    # 1. استخراج البيانات الأساسية
    try:
        # دعم FormData (للملفات) و JSON
        if request.content_type.startswith('multipart/form-data'):
            data = request.POST.dict()
            files = request.FILES
        else:
            data = json.loads(request.body)
            files = {}

        channel_id = data.get("channel_id")
        to_number = data.get("to") or data.get("phone")
        msg_type = data.get("type", "template") # الافتراضي قالب

        # 2. التحقق من القناة والصلاحيات
        channel = get_target_channel(request.user, channel_id)
        if not channel:
            return JsonResponse({"error": "Channel not found or permission denied"}, status=403)

        if not to_number:
            return JsonResponse({"error": "Missing recipient phone number"}, status=400)

        # إعدادات الاتصال بـ Meta
        access_token = channel.access_token
        phone_id = channel.phone_number_id
        api_version = getattr(channel, 'api_version', 'v24.0')
        
        if not access_token or not phone_id:
            return JsonResponse({"error": "Invalid channel configuration"}, status=500)

        url = f"https://graph.facebook.com/{api_version}/{phone_id}/messages"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        # ============================================================
        # مسار 1: إرسال قالب (Template)
        # ============================================================
        if msg_type == "template":
            template_name = data.get("template_name")
            language_code = data.get("language", "ar")
            
            # معالجة المتغيرات (Components)
            # تأتي أحياناً كـ JSON String من FormData
            components_raw = data.get("components")
             

            components = []
         
            if components_raw:
                if isinstance(components_raw, str):
                    try:
                        components = json.loads(components_raw)
                    except json.JSONDecodeError:
                        return JsonResponse({"error": "Invalid components JSON"}, status=400)
                else:
                    components = components_raw

            # معالجة ملف الهيدر (إذا وجد)
            header_file = files.get('header_file')
            if header_file:
                # يجب رفع الملف أولاً والحصول على Handle ID
                # (للاختصار: سنفترض وجود دالة مساعدة upload_media_to_meta)
                # media_id = upload_media_to_meta(header_file, channel)
                # ثم نضيفه للـ components
                pass 

            payload = {
                "messaging_product": "whatsapp",
                "to": to_number,
                "type": "template",
                "template": {
                    "name": template_name,
                    "language": {"code": language_code},
                    "components": components
                }
            }
            

            # الإرسال الفعلي
            response = requests.post(url, headers=headers, json=payload)
            res_data = response.json()

            if response.status_code not in [200, 201]:
                print(res_data)
                return JsonResponse({"error": "Meta API Error", "details": res_data}, status=400)

            # الحفظ في قاعدة البيانات
            # نستخرج wamid
            wamid = res_data.get('messages', [{}])[0].get('id')
            
            Message.objects.create(
                channel=channel,
                sender=to_number,
                is_from_me=True,
                body=f"[Template: {template_name}]",
                message_id=wamid,
                status='sent',
                media_type='template' # نوع جديد للتمييز
            )

            return JsonResponse({"success": True, "wamid": wamid})

        # ============================================================
        # مسار 2: إرسال وسائط (Media Upload)
        # ============================================================
        elif msg_type in ["image", "video", "document", "audio"]:
            # (يمكنك نقل كود رفع الوسائط القديم هنا إذا أردت الاحتفاظ به)
            # لكنك طلبت التركيز على القوالب الآن.
            pass

        return JsonResponse({"error": "Unsupported message type for this endpoint"}, status=400)

    except Exception as e:
        print(f"❌ Error in send_message: {e}")
        return JsonResponse({"error": str(e)}, status=500)




@require_GET
def get_messages1(request):
    """
    GET /api/get_messages/?phone=<phone>&since_id=<id>
    Returns JSON: { messages: [{ id, body, fromMe, time }] }
    """
    channel_id = request.GET.get('channel_id')

    phone = request.GET.get('phone')
    since_id = request.GET.get('since_id')
    if not phone:
        return JsonResponse({"messages": []})
    qs = Message.objects.filter(sender=phone).order_by('id')
    if since_id:
        try:
            since_id = int(since_id)
            qs = qs.filter(id__gt=since_id)
        except ValueError:
            pass

    messages = []
   
    contact = Contact.objects.filter(channel=WhatsAppChannel.objects.get(id=channel_id), phone=phone).first()

     
    contact_crm_data = {
        'pipeline_stage': contact.pipeline_stage ,          
        'assigned_agent_id': contact.assigned_agent_id,  
        'tags': [                                         
            {'name': tag.name, 'color': tag.color} 
            for tag in contact.tags.all()
        ]
    }
    

    for m in qs:
        msg_type = ''
        Type = getattr(m, 'type' , None)
        if Type :
            msg_type = Type
        else : 
            msg_type = getattr(m, 'media_type', 'text')

        # msg_type = getattr(m, 'media_type', 'text')
        media_file = getattr(m, 'media_file', None)  
        media_url = None
        m.is_read=True
        m.save()
        status = getattr(m,'status' , None)
        if media_file:
            try:
                # Prefer FileField/FieldFile .url when available
                url_attr = getattr(media_file, 'url', None)
                if url_attr:
                    media_url = request.build_absolute_uri(url_attr)
                     
                else:
                    media_name = str(media_file).strip()
                    if not media_name:
                        media_url = None
                    elif media_name.startswith('http://') or media_name.startswith('https://'):
                        # Already a full URL stored in the database
                        media_url = media_name
                    else:
                        # Treat as relative path under MEDIA_URL
                        media_path = media_name.lstrip('/')
                        base = settings.MEDIA_URL or '/media/'
                        if not base.endswith('/'):
                            base = base + '/'
                        # If media_path already contains the base, avoid duplicating
                        if media_path.startswith(base.lstrip('/')):
                            media_url = request.build_absolute_uri('/' + media_path)
                        else:
                            media_url = request.build_absolute_uri(base + media_path)
            except Exception:
                media_url = None
        else:
            media_url = getattr(m, 'media_url', None)
    
        messages.append({
            "id": m.id,
            "body": m.body,
            "fromMe": bool(m.is_from_me),
            "time": m.created_at.strftime("%H:%M"),
            "type": msg_type,
            "url": media_url,
            "status":status
        })
         

    return JsonResponse({"messages": messages , "crm_data": contact_crm_data})


from django.db.models import Max, OuterRef, Subquery, Count, Q

from django.core.paginator import Paginator
from django.db.models import Max, Count, Q, F
from django.http import JsonResponse
 
 
def api_contacts2(request):
    try:
        user = request.user
        if not user.is_authenticated:
            return JsonResponse({"error": "Auth required"}, status=401)

        # 1. تحديد القناة (Logic)
        req_channel_id = request.GET.get('channel_id')
        target_channel = None
        
        if req_channel_id == 'null' or req_channel_id == 'undefined':
            req_channel_id = None

        if user.is_superuser or getattr(user, 'is_team_admin', False):
            qs = WhatsAppChannel.objects.filter(owner=user)
        else:
            qs = WhatsAppChannel.objects.filter(assigned_agents=user)
            
        if req_channel_id:
            target_channel = qs.filter(id=req_channel_id).first()
        if not target_channel:
            target_channel = qs.first()
            
        if not target_channel:
            return JsonResponse({'contacts': [], 'total_pages': 0})

        # 2. الاستعلام الأساسي للرسائل (Aggregation)
        # تجميع الرسائل حسب المرسل لحساب عدد غير المقروء وآخر رسالة
        conversations = Message.objects.filter(channel=target_channel)\
            .values('sender')\
            .annotate(
                last_msg_id=Max('id'),
                last_msg_time=Max('created_at'),
                unread_count=Count('id', filter=Q(is_read=False, is_from_me=False))
            )\
            .order_by('-last_msg_id')

        # 3. استقبال بارامترات الفلترة والبحث
        search_query = request.GET.get('q', '').strip()
        
        filter_assigned = request.GET.get('assigned', 'all')
        filter_stage = request.GET.get('stage', 'all')
        filter_tags = request.GET.get('tags', '').strip()
        unread_only = request.GET.get('unread_only') == 'true'

        # 4. تطبيق الفلاتر المعقدة (Assigned, Stage, Tags)
        # بما أن هذه المعلومات موجودة في جدول Contact وليس Message،
        # يجب أن نفلتر جهات الاتصال أولاً ثم نستخدم أرقامهم لفلترة المحادثات.
        
        contact_filters = Q(channel=target_channel)
        has_contact_filters = False

        # أ) فلتر الموظف المسؤول
        if filter_assigned != 'all':
            has_contact_filters = True
            if filter_assigned == 'me':
                contact_filters &= Q(assigned_agent=user)
            elif filter_assigned == 'unassigned':
                contact_filters &= Q(assigned_agent__isnull=True)
            else:
                contact_filters &= Q(assigned_agent_id=filter_assigned)

        # ب) فلتر المرحلة (Pipeline)
        if filter_stage != 'all':
            has_contact_filters = True
            # تأكد أن اسم الحقل في المودل هو pipeline_stage
            contact_filters &= Q(pipeline_stage=filter_stage)

        # ج) فلتر التاجات
        if filter_tags:
            has_contact_filters = True
            # البحث الجزئي في اسم التاج (ManyToMany)
            contact_filters &= Q(tags__name__icontains=filter_tags)

        # د) تطبيق فلاتر جهات الاتصال إذا وجدت
        if has_contact_filters:
            matching_phones = Contact.objects.filter(contact_filters).values_list('phone', flat=True)
            conversations = conversations.filter(sender__in=matching_phones)

        # 5. تطبيق البحث (Search)
        # نبحث في رقم الهاتف (sender) أو في اسم جهة الاتصال
        if search_query:
            # البحث عن الأرقام التي تحمل هذا الاسم في جهات الاتصال
            matching_names = Contact.objects.filter(
                channel=target_channel, 
                name__icontains=search_query
            ).values_list('phone', flat=True)
            
            conversations = conversations.filter(
                Q(sender__icontains=search_query) | Q(sender__in=matching_names)
            )

        # 6. فلتر غير المقروء (Unread Only)
        if unread_only:
            conversations = conversations.filter(unread_count__gt=0)

        # 7. الترقيم (Pagination)
        paginator = Paginator(conversations, 20) 
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        # 8. تجهيز البيانات (تحسين الأداء - Bulk Fetch)
        msg_ids = [c['last_msg_id'] for c in page_obj]
        senders_phones = [c['sender'] for c in page_obj]

        # جلب نصوص الرسائل دفعة واحدة
        messages_map = Message.objects.filter(id__in=msg_ids).in_bulk()

        # جلب بيانات جهات الاتصال دفعة واحدة (بما في ذلك الموظف المسؤول)
        contacts_map = {
            c.phone: {
                'name': c.name, 
                'pic': c.profile_picture.url if c.profile_picture else None,
                'agent_id': c.assigned_agent_id # 🔥 جلبنا الموظف هنا لتقليل الاستعلامات
            }
            for c in Contact.objects.filter(phone__in=senders_phones, channel=target_channel)
        }

        final_data = []
        for item in page_obj:
            phone = item['sender']
            msg = messages_map.get(item['last_msg_id'])
            
            # استخراج بيانات الاتصال من الذاكرة (Map)
            contact_info = contacts_map.get(phone, {})
            name = contact_info.get('name', phone)
            pic = contact_info.get('pic', None)
            assigned_agent_id = contact_info.get('agent_id', None)

            # تجهيز المقتطف
            snippet = ''
            if msg:
                if msg.media_type == 'audio': snippet = '🎤 صوت'
                elif msg.media_type == 'image': snippet = '📷 صورة'
                elif msg.media_type == 'video': snippet = '🎥 فيديو'
                else: snippet = msg.body[:50] if msg.body else ''

            final_data.append({
                "phone": phone,
                "name": name,
                "profile_picture": pic,
                "snippet": snippet,
                "unread": item['unread_count'],
                "last_status": msg.status if msg else '',
                "fromMe": msg.is_from_me if msg else False,
                "timestamp": item['last_msg_time'].strftime("%H:%M") if item['last_msg_time'] else "",
                "channel_id": target_channel.id,
                "assigned_agent_id": assigned_agent_id 
            })

        return JsonResponse({
            'contacts': final_data,
            'current_channel_id': target_channel.id,
            'has_next': page_obj.has_next(),
            'total_pages': paginator.num_pages,
            'current_page': page_obj.number
        })

    except Exception as e:
        print(f"❌ Error in api_contacts2: {e}")
        return JsonResponse({"error": str(e)}, status=500)

 
 

from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from discount.models import WhatsAppChannel, Contact # تأكد من المسارات

def api_contactsList(request):
    user = request.user
    
    # 1. التحقق من تسجيل الدخول
    if not user.is_authenticated:
        return JsonResponse({"contacts": [], "error": "Auth required"}, status=401)

    # 2. تحديد القنوات التي يملك المستخدم صلاحية عليها
    if user.is_team_admin or user.is_superuser:
        allowed_channels = WhatsAppChannel.objects.filter(owner=user)
    else:
        allowed_channels = WhatsAppChannel.objects.filter(assigned_agents=user)

    # 3. الحصول على معرف القناة من الرابط
    req_channel_id = request.GET.get('channel_id')
    target_channel = None

    # تنظيف المدخل (في حال جاء null كنص)
    if req_channel_id == 'null': req_channel_id = None

    if req_channel_id:
        target_channel = allowed_channels.filter(id=req_channel_id).first()
    else:
        target_channel = allowed_channels.first()

    # إذا لم يتم العثور على قناة
    if not target_channel:
        return JsonResponse({"contacts": [], "total_pages": 0})

    # ============================================================
    # 4. بناء الاستعلام (Query Building)
    # ============================================================
    
    # نبدأ بكل جهات الاتصال في هذه القناة
    contacts_qs = Contact.objects.filter(channel=target_channel)

    # أ) البحث (Search)
    search_query = request.GET.get('q', '').strip()
    if search_query:
        contacts_qs = contacts_qs.filter(
            Q(name__icontains=search_query) | 
            Q(phone__icontains=search_query)
        )

    # ب) الفلترة (Filter)
    filter_type = request.GET.get('filter', 'all')
    
    if filter_type == 'important':
        # نفترض وجود حقل is_important في المودل
        if hasattr(Contact, 'is_important'):
            contacts_qs = contacts_qs.filter(is_important=True)
            
    elif filter_type == 'recent':
        contacts_qs = contacts_qs.order_by('-last_interaction')
    else:
        # الترتيب الافتراضي
        contacts_qs = contacts_qs.order_by('-last_interaction')

    # ============================================================
    # 5. التقسيم (Pagination)
    # ============================================================
    
    page_number = request.GET.get('page', 1)
    page_size = 20 # عدد العناصر في الصفحة
    paginator = Paginator(contacts_qs, page_size)
    page_obj = paginator.get_page(page_number)

    # ============================================================
    # 6. تجهيز البيانات (Serialization)
    # ============================================================
    
    contacts_list = []
    for contact in page_obj:
        contacts_list.append({
            'id': contact.id,
            'phone': contact.phone,
            'name': contact.name or contact.phone,
            
            # تواريخ مهيأة
            'last_interaction': contact.last_interaction.strftime("%Y-%m-%d %H:%M") if contact.last_interaction else "-",
            'created_at': contact.created_at.strftime("%Y-%m-%d") if hasattr(contact, 'created_at') else None,
            
            # الصورة
            'profile_picture': contact.profile_picture.url if contact.profile_picture else None,
            
            # بيانات إضافية مفيدة للجدول
            'is_important': getattr(contact, 'is_important', False),
            'channel_name': target_channel.name,
            # يمكنك إضافة عدد الطلبات هنا إذا كان لديك علاقة عكسية
            # 'orders_count': contact.orders.count() 
        })
    
    # إرجاع البيانات مع معلومات الصفحات
    return JsonResponse({
        "contacts": contacts_list,
        "has_next": page_obj.has_next(),
        "total_pages": paginator.num_pages,
        "current_page": page_obj.number,
        "total_count": paginator.count
    })
# ---------------templates---------------------
 

import json
import re
from datetime import datetime

from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.db import transaction
from django.core.exceptions import ValidationError

 

# ----- إعدادات تحقق افتراضية (عدلها حسب حاجتك) -----
MAX_BODY_LENGTH = 1098
MAX_NAME_LENGTH = 255
MAX_PLACEHOLDERS = 20
MAX_BUTTONS = 3
ALLOWED_HEADER_TYPES = {'text', 'image', 'video', 'document'}
MAX_UPLOAD_SIZE = 5 * 1024 * 1024  # 5 MB (قيمة افتراضية، غيّرها إن أردت)
ALLOWED_IMAGE_CONTENT_TYPES = ('image/jpeg', 'image/png', 'image/webp', 'image/gif')
ALLOWED_VIDEO_CONTENT_TYPES = ('video/mp4', 'video/quicktime', 'video/webm')
ALLOWED_DOC_CONTENT_TYPES = ('application/pdf',
                             'application/msword',
                             'application/vnd.openxmlformats-officedocument.wordprocessingml.document')


# ----- دوال مساعدة -----
_PLACEHOLDER_RE = re.compile(r'(?:\{\{\s*(\d+)\s*\}\}|\[\[\s*(\d+)\s*\]\])')
_BRACKET_NORMALIZE_RE = re.compile(r'\[\[\s*(\d+)\s*\]\]')

def extract_placeholders(body_text):
    """Return sorted list of unique ints found as placeholders either {{n}} or [[n]]."""
    nums = set()
    for m in _PLACEHOLDER_RE.finditer(body_text or ''):
        a = m.group(1)
        b = m.group(2)
        num = a or b
        if num:
            nums.add(int(num))
    return sorted(nums)

def placeholders_are_sequential(nums):
    """Return True if nums form 1..max with no gaps (or empty list)."""
    if not nums:
        return True
    mx = max(nums)
    return nums == list(range(1, mx + 1))

def normalize_body_placeholders(body_text):
    """Convert any [[n]] => {{n}} for storage/WhatsApp usage."""
    return _BRACKET_NORMALIZE_RE.sub(lambda m: '{{%s}}' % m.group(1), body_text or '')

def parse_json_field(post, key):
    """Parse JSON string from POST field; return (value, error)"""
    raw = post.get(key)
    if not raw:
        return None, None
    try:
        return json.loads(raw), None
    except Exception as e:
        return None, f'Invalid JSON for {key}: {e}'

def validate_buttons(buttons):
    """Validate buttons array structure; return (clean_buttons, error_message_or_None)"""
    if not isinstance(buttons, list):
        return None, 'buttons must be an array'
    if len(buttons) > MAX_BUTTONS:
        return None, f'Max {MAX_BUTTONS} buttons are allowed'
    allowed_types = {'quick_reply', 'url', 'call', 'copy', 'custom'}
    clean = []
    for idx, b in enumerate(buttons, 1):
        if not isinstance(b, dict):
            return None, f'button #{idx} must be an object'
        t = b.get('type')
        text = (b.get('text') or '').strip()
        if not t or t not in allowed_types:
            return None, f'button #{idx}: invalid or missing type'
        if not text:
            return None, f'button #{idx}: text is required'
        item = {'type': t, 'text': text}
        if t == 'url':
            url = (b.get('url') or '').strip()
            if not url:
                return None, f'button #{idx}: url is required for type "url"'
            # basic URL validation
            if not (url.startswith('http://') or url.startswith('https://')):
                return None, f'button #{idx}: url must start with http:// or https://'
            item['url'] = url
        elif t == 'call':
            phone = (b.get('phone') or '').strip()
            if not phone:
                return None, f'button #{idx}: phone is required for type "call"'
            # basic phone length check (you can enhance)
            if len(re.sub(r'\D', '', phone)) < 6:
                return None, f'button #{idx}: phone looks invalid'
            item['phone'] = phone
        elif t in ('quick_reply', 'copy'):
            payload = (b.get('payload') or '').strip()
            # payload can be optional for quick_reply but we allow it
            item['payload'] = payload
        elif t == 'custom':
            # custom may accept url or payload optionally
            item['url'] = (b.get('url') or '').strip()
            item['payload'] = (b.get('payload') or '').strip()
        clean.append(item)
    return clean, None

def validate_uploaded_file(f, header_type):
    """Basic validation for uploaded header file based on header_type."""
    if not f:
        return None  # nothing to validate
    # size
    if f.size > MAX_UPLOAD_SIZE:
        return f'Uploaded file too large (max {MAX_UPLOAD_SIZE} bytes)'
    ct = getattr(f, 'content_type', '') or ''
    if header_type == 'image' and ct not in ALLOWED_IMAGE_CONTENT_TYPES:
        return f'Invalid image content type: {ct}'
    if header_type == 'video' and ct not in ALLOWED_VIDEO_CONTENT_TYPES:
        return f'Invalid video content type: {ct}'
    if header_type == 'document' and ct not in ALLOWED_DOC_CONTENT_TYPES:
        return f'Invalid document content type: {ct}'
    return None


from discount.models import WhatsAppChannel
# ----- العرض: create_template view محسنة -----
@require_POST
def create_template(request):
    try:
        # قراءة الحقول الأساسية
        user = request.user 
        name = (request.POST.get('name') or '').strip()
        category = (request.POST.get('category') or '').strip()
        language = (request.POST.get('language') or '').strip()
        status = (request.POST.get('status') or '').strip()
        updated_raw = (request.POST.get('updated') or '').strip()
        body = (request.POST.get('body') or '').strip()
        footer = (request.POST.get('footer') or '').strip()
        header_type = (request.POST.get('header_type') or 'text').strip()

        # ملفات رأس مرفوعة
        header_image = request.FILES.get('header_image')
        header_video = request.FILES.get('header_video')
        header_document = request.FILES.get('header_document')
        channel_id = request.POST.get('channel_id')
        if not channel_id: return JsonResponse({'success': False, 'errors': 'channel_id is required'}, status=400) # 
        
        if  user.is_superuser or user.is_team_admin or user.is_staff :
            channel = WhatsAppChannel.objects.get( id=channel_id)
        else :
            channel = WhatsAppChannel.objects.get(assigned_agents = user , id=channel_id)
        if not channel : return JsonResponse({'success': False, 'errors': 'channel not found'}, status=400)




        # تحقق أولي للحقلين الهامين
        errors = []
        if not name:
            errors.append('name is required')
        elif len(name) > MAX_NAME_LENGTH:
            errors.append(f'name max length is {MAX_NAME_LENGTH}')
        if not body:
            errors.append('body is required')
        elif len(body) > MAX_BODY_LENGTH:
            errors.append(f'body max length is {MAX_BODY_LENGTH}')

        if header_type not in ALLOWED_HEADER_TYPES:
            errors.append('invalid header_type')

        # parse JSON fields
        body_samples_raw, err = parse_json_field(request.POST, 'body_samples')
        if err:
            errors.append(err)
        buttons_raw, err2 = parse_json_field(request.POST, 'buttons')
        if err2:
            errors.append(err2)

        if errors:
            return JsonResponse({'success': False, 'errors': errors}, status=400)

        # استخراج المتغيرات من body (يدعم {{n}} أو [[n]])
        placeholders = extract_placeholders(body)  # e.g. [1,2,3]
        if len(placeholders) > MAX_PLACEHOLDERS:
            return JsonResponse({'success': False, 'error': f'too many placeholders, max {MAX_PLACEHOLDERS}'}, status=400)
        if not placeholders_are_sequential(placeholders):
            return JsonResponse({'success': False, 'error': 'placeholders must be sequential 1..N without gaps'}, status=400)

        max_placeholder = max(placeholders) if placeholders else 0

        # validate body_samples: expected array of {type:'text', text:'...'} in order
        samples = []
        if max_placeholder > 0:
            if body_samples_raw is None:
                # not provided — accept (maybe admin didn't fill samples) but warn
                return JsonResponse({'success': False, 'error': 'body_samples missing for placeholders'}, status=400)
            if not isinstance(body_samples_raw, list):
                return JsonResponse({'success': False, 'error': 'body_samples must be an array'}, status=400)
            if len(body_samples_raw) != max_placeholder:
                return JsonResponse({'success': False, 'error': f'body_samples length must equal number of placeholders ({max_placeholder})'}, status=400)
            # basic shape check
            for i, s in enumerate(body_samples_raw, 1):
                if not isinstance(s, dict) or s.get('type') != 'text':
                    return JsonResponse({'success': False, 'error': f'body_samples[{i-1}] must be an object with type \"text\"'}, status=400)
                # allow empty sample text but coerce to string
                samples.append({'type': 'text', 'text': str(s.get('text') or '')})

        # validate buttons
        clean_buttons = []
        if buttons_raw:
            clean_buttons, btn_err = validate_buttons(buttons_raw)
            if btn_err:
                return JsonResponse({'success': False, 'error': btn_err}, status=400)

        # validate uploaded header file according to header_type
        if header_type == 'image':
            err = validate_uploaded_file(header_image, 'image')
            if err:
                return JsonResponse({'success': False, 'error': err}, status=400)
        elif header_type == 'video':
            err = validate_uploaded_file(header_video, 'video')
            if err:
                return JsonResponse({'success': False, 'error': err}, status=400)
        elif header_type == 'document':
            err = validate_uploaded_file(header_document, 'document')
            if err:
                return JsonResponse({'success': False, 'error': err}, status=400)

        # تحويل [[n]] الى {{n}} قبل الحفظ (الواجهة قد تستعمل [[n]] لتجنب تعارض Django)
        body_normalized = normalize_body_placeholders(body)

        # محاولة تحويل تاريخ 'updated' إن وُجد
        updated_date = None
        if updated_raw:
            try:
                # تقبل YYYY-MM-DD
                updated_date = datetime.strptime(updated_raw, '%Y-%m-%d').date()
            except Exception:
                # ليس حرجا — لكن نُرجع خطأ واضح
                return JsonResponse({'success': False, 'error': 'updated must be in YYYY-MM-DD format'}, status=400)

        # كل شيء تم التحقق منه — نحفظ داخل معاملة
        with transaction.atomic():

            template = Template.objects.create(
                channel = channel,
                user = user ,
                name=name,
                category=category,
                language=language,
                status=status,
                updated_at=updated_date,
                body=body_normalized,
                footer=footer,
                header_type=header_type,
                header_text=(request.POST.get('header_text') or '').strip(),
            )
            # احفظ الملفات (إن وُجدت) إلى حقل الملف الخاص بالنموذج
            if header_image:
                template.header_image = header_image
            if header_video:
                template.header_video = header_video
            if header_document:
                template.header_document = header_document

            # احفظ بيانات مساعدة مثل body_samples و buttons في حقول JSON أو حقول نصية
            # افتراض أن الحقلين موجودين في النموذج (jsonfields أو TextField)
            try:
                # إذا كان نموذجك يحتوي على JSONField يمكنك وضع القيم مباشرة
                if hasattr(template, 'body_samples'):
                    template.body_samples = samples
                else:
                    template.meta_body_samples = json.dumps(samples, ensure_ascii=False)
            except Exception:
                # إذا النموذج لا يحتوي، يمكنك إنشاء حقل نصي مؤقت بدلاً من ذلك
                template.meta_body_samples = json.dumps(samples, ensure_ascii=False)

            try:
                if hasattr(template, 'buttons'):
                    template.buttons = clean_buttons
                else:
                    template.meta_buttons = json.dumps(clean_buttons, ensure_ascii=False)
            except Exception:
                template.meta_buttons = json.dumps(clean_buttons, ensure_ascii=False)
            
            # إرسال القالب إلى Meta للمراجعة
            try:
                meta_result = submit_template_to_meta(template ,channel ,user)
                if meta_result.get('ok'):
                    # ضع حالة قيد الانتظار (pending) واغتنم المعرف إن وُجد
                    template.status = 'pending'
                    meta_id = meta_result.get('meta_id')
                    if meta_id:
                        template.template_id = meta_id
                    # حفظ الـ components payload محلياً لمرجعية لاحقة
                    try:
                        template.components = meta_result.get('response') or {}
                    except Exception:
                        # fallback to string
                        template.components = {}
                    template.save()
                    return JsonResponse({'success': True, 'id': template.id, 'meta_id': template.template_id})
                else:
                    # فشل في إرسال القالب إلى Meta
                    template.status = 'draft'
                    template.save()
                    return JsonResponse({
                        'success': False,
                        'error': 'Failed to submit template to Meta: ' + str(meta_result.get('error')),
                        'detail': meta_result.get('response')
                    }, status=400)
            except Exception as e:
                logger.exception('unexpected error while submitting template to meta')
                # لا نوقف الخط العام، نرجع خطأ مناسب
                return JsonResponse({'success': False, 'error': 'Internal error when submitting to Meta'}, status=500)

    except Exception as e:
        # لا تكشف استثناء داخلي مفصّل في الإنتاج — استخدم تسجيل (logger) بدلًا من ذلك
        import traceback, logging
        logging.exception('create_template error')
        return JsonResponse({'success': False, 'error': str(e)}, status=400)




from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST
from datetime import datetime
import re

@require_POST
def update_template(request, pk):
    try:
        template = get_object_or_404(Template, pk=pk)

        # تنظيف البيانات
        name = (request.POST.get('name') or '').strip()
        category = (request.POST.get('category') or '').strip()
        language = (request.POST.get('language') or '').strip()
        status = (request.POST.get('status') or '').strip()
        updated_raw = (request.POST.get('updated') or '').strip()
        body = (request.POST.get('body') or '').strip()
        footer = (request.POST.get('footer') or '').strip()
        header_type = (request.POST.get('header_type') or 'text').strip()
        header_text = (request.POST.get('header_text') or '').strip()
        buttons_raw = request.POST.get('buttons', '[]')

        try:
            buttons = json.loads(buttons_raw)
        except json.JSONDecodeError:
            buttons = []

        # التحقق من الاسم (إجباري)
        if not name:
            return JsonResponse({
                'success': False,
                'error': 'اسم القالب مطلوب'
            }, status=400)

        # التحقق من تسلسل المتغيرات {{1}} {{2}} {{3}}
        pattern = r'{{\s*(\d+)\s*}}'
        matches = re.findall(pattern, body)

        if matches:
            nums = [int(n) for n in matches]
            expected = list(range(1, len(nums) + 1))
            if nums != expected:
                return JsonResponse({
                    'success': False,
                    'error': 'تسلسل المتغيرات غير صحيح، يجب أن يكون {{1}} ثم {{2}} ثم {{3}} بدون تخطي'
                }, status=400)

        # التحقق من التاريخ
        if updated_raw:
            try:
                datetime.strptime(updated_raw, '%Y-%m-%d')
                template.updated = updated_raw
            except ValueError:
                return JsonResponse({
                    'success': False,
                    'error': 'صيغة التاريخ يجب أن تكون YYYY-MM-DD'
                }, status=400)

        # الملفات
        header_image = request.FILES.get('header_image')
        header_video = request.FILES.get('header_video')
        header_audio = request.FILES.get('header_audio')

        # تحديث القيم النصية
        template.name = name
        template.category = category
        template.language = language
        template.status = status
        template.body = body
        template.footer = footer
        template.header_type = header_type
        template.header_text = header_text
        template.buttons = buttons

        # تحديث الملفات فقط إذا تم إرسالها
        if header_image:
            template.header_image = header_image

        if header_video:
            template.header_video = header_video

        if header_audio:
            template.header_audio = header_audio

        template.save()

        return JsonResponse({'success': True, 'id': template.id})

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': 'خطأ داخلي: ' + str(e)
        }, status=500)




@require_GET
def api_template(request, pk=None):
    if pk:
        print("Fetching template with ID:", pk)
        template = get_object_or_404(Template, pk=pk)
        data = {
            'id': template.id,
            'name': template.name,
            'category': template.category,
            'language': template.language,
            'status': template.status,
            'updated': template.updated_at.isoformat() if template.updated_at else None,
            'body': template.body,
            'footer': template.footer,
            'header_type': template.header_type,
            'header_text': template.header_text,
            'created_at': template.created_at.isoformat() if template.created_at else None,
            'buttons': template.buttons
        }

        return JsonResponse({'template': data})

    return JsonResponse({'error': 'template id required'}, status=400)


# في views.py أو utils.py 

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



@require_GET
def api_templates(request):
    """
    Retrieve all templates or a specific template by ID.
    """
    try:
        user = request.user
        channel_id = request.GET.get('channel_id')

        if not channel_id or channel_id == 'null':
             return JsonResponse({'error': 'Channel ID required'}, status=400)

        # 1. جلب القناة (استخدمنا المنطق الآمن)
        if user.is_superuser or getattr(user, 'is_team_admin', False):
            channel = WhatsAppChannel.objects.filter(id=channel_id, owner=user).first()
        else:
            channel = WhatsAppChannel.objects.filter(id=channel_id, assigned_agents=user).first()

        if not channel:
            return JsonResponse({'error': 'Permission denied or channel not found'}, status=403)

        # 2. 🔥 التصحيح هنا: حذفنا .values() 🔥
        # الآن templates تحتوي على كائنات (Objects)
        templates = Template.objects.filter(channel=channel)

        if 'id' in request.GET:
            # منطق جلب قالب واحد
            template_id = request.GET.get('id')
            # نستخدم filter().first() لتجنب crash لو لم يوجد
            template = templates.filter(id=template_id).first()
            
            if not template:
                return JsonResponse({'error': 'Template not found'}, status=404)

            data = {
                'id': template.id,
                'name': template.name,
                'category': template.category,
                'language': template.language,
                'status': template.status,
                'updated': template.updated_at.isoformat() if template.updated_at else None,
                'body': template.body,
                'footer': template.footer,
                'header_type': template.header_type,
                'header_text': template.header_text,
                'created_at': template.created_at.isoformat() if template.created_at else None,
            }
            return JsonResponse({'template': data})
        else:
            # منطق جلب الكل (الذي كان يسبب الخطأ)
            data = [
                {
                    'id': template.id, # ✅ الآن يعمل لأن template كائن
                    'name': template.name,
                    'category': template.category,
                    'language': template.language,
                    'status': template.status,
                    'updated': template.updated_at.isoformat() if template.updated_at else None,
                    'body': template.body,
                    'footer': template.footer,
                    'header_type': template.header_type,
                    'header_text': template.header_text,
                    'created_at': template.created_at.isoformat() if template.created_at else None,
                }
                for template in templates
            ]
            return JsonResponse({'templates': data}, safe=False)

    except Exception as e:
        # طباعة الخطأ في التيرمينال لنعرف السبب لو تكرر
        print(f"❌ Error in api_templates: {e}")
        return JsonResponse({'error': str(e)}, status=500)





  
@require_GET
def api_orders(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return JsonResponse({"orders": []}, status=401)

    # 1. تحديد القناة المستهدفة (باستخدام دالة المساعدة الآمنة)
    # هذه الدالة تتكفل بفحص هل المستخدم (سواء أدمن أو موظف) لديه صلاحية رؤية هذه القناة
    target_channel = get_target_channel(user, request.GET.get('channel_id'))
    

    # إذا لم نجد قناة أو ليست لديه صلاحية
    if not target_channel:
        return JsonResponse({"orders": []})

    # 2. جلب الطلبات بناءً على القناة 🔥
    # هذا هو التغيير الجوهري: نفلتر بالقناة وليس بالمستخدم فقط
    qs = Order.objects.filter(channel=target_channel).select_related('user').order_by("-created_at")

    # (اختياري) إذا كنت تريد أن يرى الموظف العادي طلباته هو فقط داخل القناة،
    # بينما يرى الأدمن طلبات الجميع داخل القناة، أضف هذا الشرط:
    # if not (user.is_superuser or getattr(user, 'is_team_admin', False)):
    #     qs = qs.filter(user=user)
    
    # لكن المنطق السائد في الـ CRM هو أن يرى الجميع طلبات القناة للتعاون.

    data = []
    for o in qs:
        data.append({
            "id": o.id,
            "customer_name": getattr(o, "customer_name", "") or "Unknown",
            "total_amount": getattr(o, "product_price", 0),
            "customer_phone": getattr(o, "customer_phone", ""),
            "customer_city": getattr(o, "customer_city", ""),
            "status": getattr(o, "confirmed", False), # مثال للحالة
            "product": getattr(o, "product", ""),
            "created_by": o.user.email, # لنعرف من أنشأ الطلب
            "created_at": o.created_at.isoformat() if o.created_at else None,
        })
   
    return JsonResponse({"orders": data})



@require_GET
def api_order_details(request, order_id):
    """
    الحصول على تفاصيل طلب معين
    """
    try:
        user = request.user
        if not user.is_authenticated:
            return JsonResponse({'error': 'Authentication required'}, status=401)
            
        order = get_object_or_404(Order, id=order_id, user=user)
        
        order_data = {
            "id": order.id,
            "customer_name": order.customer_name,
            "customer_phone": order.customer_phone,
            "customer_city": order.customer_city,
            "product_name": order.product_name,
            "product_price": order.product_price,
            "status": order.status,
            "notes": order.notes,
            "created_at": order.created_at.isoformat() if order.created_at else None,
            "updated_at": order.updated_at.isoformat() if order.updated_at else None
        }
        
        return JsonResponse({"order": order_data})
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
@require_http_methods(["POST"])
def api_update_order_status(request, order_id):
    """
    تحديث حالة الطلب
    """
    try:
        user = request.user
        if not user.is_authenticated:
            return JsonResponse({'error': 'Authentication required'}, status=401)
            
        order = get_object_or_404(Order, id=order_id, user=user)
        payload = json.loads(request.body.decode('utf-8'))
        new_status = payload.get('status')
        
        if new_status:
            order.status = new_status
            order.save()
            
            return JsonResponse({'success': True, 'order': {
                'id': order.id,
                'status': order.status,
                'updated_at': order.updated_at.isoformat() if order.updated_at else None
            }})
        else:
            return JsonResponse({'error': 'Status is required'}, status=400)
            
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
@require_http_methods(["POST"])
def api_send_template(request):
    """
    إرسال قالب واتساب
    """
    try:
        payload = json.loads(request.body.decode('utf-8'))
        to = payload.get('to')
        template_name = payload.get('template_name')
        language_code = payload.get('language', 'ar')
        components = payload.get('components', [])
        
        if not to or not template_name:
            return JsonResponse({'error': 'Missing required fields'}, status=400)
            
        url = f"https://graph.facebook.com/v17.0/{PHONE_NUMBER_ID}/messages"
        headers = {
            'Authorization': f'Bearer {ACCESS_TOKEN}',
            'Content-Type': 'application/json'
        }
        
        data = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {
                    "code": language_code
                }
            }
        }
        
        if components:
            data["template"]["components"] = components
            
        response = requests.post(url, headers=headers, json=data)
        
        if response.status_code == 200:
            Message.objects.create(
                sender=to,
                body=f"Template: {template_name}",
                is_from_me=True,
                template_name=template_name
            )
            return JsonResponse({'success': True, 'message_id': response.json().get('messages', [{}])[0].get('id')})
        else:
            return JsonResponse({'error': response.text}, status=response.status_code)
            
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@require_GET
def api_template_analytics(request):
    """
    إحصائيات القوالب
    """
    try:
        templates = Template.objects.all()
        analytics = []
        
        for template in templates:
            sent_count = Message.objects.filter(
                template_name=template.name,
                is_from_me=True
            ).count()
            
            analytics.append({
                'id': template.id,
                'name': template.name,
                'category': template.category,
                'status': template.status,
                'sent_count': sent_count,
                'created_at': template.created_at
            })
            
        return JsonResponse({'analytics': analytics})
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

def upload_media(request):
    if request.method == "POST" and request.FILES.get("media"):
        media = request.FILES["media"]

        filepath = os.path.join(settings.MEDIA_ROOT, media.name)
        with open(filepath, "wb") as f:
            for chunk in media.chunks():
                f.write(chunk)
        media_url = request.build_absolute_uri(settings.MEDIA_URL + media.name)
        return JsonResponse({"status": "success", "media_url": media_url})
    return JsonResponse({"status": "error", "message": "Invalid request"}, status=400)





















def privacy(request):
    return render( request ,'whatssap/privecy.html')







 
from django.views.decorators.http import require_POST
 

@require_POST
def create_channel_api(request):
    
    try:
        data = json.loads(request.body)
        user = request.user
        
        # إنشاء القناة
        new_channel = WhatsAppChannel.objects.create(
            owner=user, # أو assigned_agents.add(user)
            name=data.get('name'),
            phone_number=data.get('phone_number'),
            phone_number_id=data.get('phone_number_id'),
            business_account_id=data.get('business_account_id'),
            access_token=data.get('access_token')
        )
        
        # إضافة المستخدم الحالي كمدير للقناة لكي يراها فوراً
        new_channel.assigned_agents.add(user)
        
        return JsonResponse({'success': True, 'id': new_channel.id})
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)












import json
import requests
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
 

@csrf_exempt
@require_POST
def exchange_token_and_create_channel(request):
    try:
        data = json.loads(request.body)
        short_lived_token = data.get('access_token')
        channel_name = data.get('name')

        if not short_lived_token:
            return JsonResponse({'success': False, 'error': 'No access token provided'}, status=400)

        # ---------------------------------------------------------
        # الخطوة 1: استبدال التوكن بآخر طويل الأمد (Long-Lived Token)
        # ---------------------------------------------------------
        exchange_url = (
            f"https://graph.facebook.com/{settings.META_API_VERSION}/oauth/access_token"
            f"?grant_type=fb_exchange_token"
            f"&client_id={settings.META_APP_ID}"
            f"&client_secret={settings.META_APP_SECRET}"
            f"&fb_exchange_token={short_lived_token}"
        )
        
        exchange_resp = requests.get(exchange_url).json()
        
        if 'access_token' not in exchange_resp:
            return JsonResponse({'success': False, 'error': 'Failed to exchange token', 'details': exchange_resp}, status=400)
            
        long_lived_token = exchange_resp['access_token']

        # ---------------------------------------------------------
        # الخطوة 2: جلب معرفات WABA وأرقام الهواتف
        # ---------------------------------------------------------
        # نستعلم عن المستخدم لنعرف ما هي حسابات الأعمال المرتبطة به
        debug_url = f"https://graph.facebook.com/{settings.META_API_VERSION}/me?fields=id,name,accounts&access_token={long_lived_token}"
        
        # ملاحظة: في Embedded Signup، الأفضل هو استخدام Endpoint خاص لجلب الأرقام المشتركة
        # Endpoint: GET /<WABA_ID>/phone_numbers
        # لكن بما أننا لا نعرف WABA_ID، سنستخدم حيلة "debug_token" أو "shared_waba"
        
        # الطريقة الأضمن في Embedded Signup هي استخراج WABA من "Granular Scopes" 
        # لكن للتبسيط، سنجلب أرقام الواتساب المرتبطة بحساب المستخدم مباشرة
        
        # أ) جلب حسابات الواتساب (WABA) التي يملكها المستخدم
        waba_req_url = f"https://graph.facebook.com/{settings.META_API_VERSION}/me/businesses?fields=id,name,owned_whatsapp_business_accounts&access_token={long_lived_token}"
        waba_resp = requests.get(waba_req_url).json()
        
        target_waba_id = None
        target_phone_obj = None

        # بحث معقد قليلاً للعثور على أول حساب واتساب متاح
        if 'data' in waba_resp:
            for business in waba_resp['data']:
                if 'owned_whatsapp_business_accounts' in business:
                    for waba in business['owned_whatsapp_business_accounts']['data']:
                        waba_id = waba['id']
                        
                        # ب) جلب أرقام الهواتف داخل هذا الـ WABA
                        phones_url = f"https://graph.facebook.com/{settings.META_API_VERSION}/{waba_id}/phone_numbers?access_token={long_lived_token}"
                        phones_resp = requests.get(phones_url).json()
                        
                        if 'data' in phones_resp and len(phones_resp['data']) > 0:
                            target_phone_obj = phones_resp['data'][0] # نأخذ أول رقم
                            target_waba_id = waba_id
                            break
                if target_phone_obj: break
        
        # إذا لم نجد بالطريقة أعلاه (لأن المستخدم قد لا يكون Owner بل Admin)، نجرب طريقة Granular Permissions
        if not target_phone_obj:
             return JsonResponse({'success': False, 'error': 'Could not find any WhatsApp Business Account linked to this user.'}, status=404)

        phone_number = target_phone_obj.get('display_phone_number') or target_phone_obj.get('verified_name')
        phone_id = target_phone_obj.get('id')

        # ---------------------------------------------------------
        # الخطوة 3: الاشتراك في الويب هوك (Subscribe App)
        # ---------------------------------------------------------
        # هذا يربط WABA بتطبيقك لتصلك الإشعارات
        subscribe_url = f"https://graph.facebook.com/{settings.META_API_VERSION}/{target_waba_id}/subscribed_apps"
        sub_resp = requests.post(subscribe_url, data={'access_token': long_lived_token})
        
        if sub_resp.status_code != 200:
             print(f"⚠️ Warning: Could not subscribe to webhook automatically: {sub_resp.json()}")

        # ---------------------------------------------------------
        # الخطوة 4: الحفظ في قاعدة البيانات
        # ---------------------------------------------------------
        channel = WhatsAppChannel.objects.create(
            owner=request.user,
            name=channel_name,
            phone_number=phone_number,
            phone_number_id=phone_id,
            business_account_id=target_waba_id,
            access_token=long_lived_token
        )
        
        # منح الصلاحية للمنشئ
        channel.assigned_agents.add(request.user)

        return JsonResponse({
            'success': True, 
            'channel_id': channel.id,
            'phone_number': phone_number
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'success': False, 'error': str(e)}, status=500)








# dashboard 
from django.utils import timezone
from datetime import timedelta
from django.db.models import Count, Q
from django.http import JsonResponse
 # تأكد من المسارات
 

def api_dashboard_stats(request):
    try:
        user = request.user
        channel = get_target_channel(user, request.GET.get('channel_id'))
        
        if not channel:
            return JsonResponse({'error': 'Channel not found'}, status=404)

        # 1. إحصائيات عامة (Cards)
        total_contacts = Contact.objects.filter(channel=channel).count()
        total_messages = Message.objects.filter(channel=channel).count()

        # يمكن إضافة Campaigns لاحقاً
        
        # 2. بيانات الحساب (من مودل القناة)
        account_info = {
            'display_name': channel.name,
            'phone_number': channel.phone_number,
            'waba_id': channel.business_account_id,
            'status': 'CONNECTED', # يمكن تحديثها لاحقاً بفحص حقيقي
            'quality': 'GREEN',    # قيمة افتراضية حالياً
            'limit': 'TIER_250'    # قيمة افتراضية
        }

        # 3. بيانات الرسم البياني (آخر 7 أيام)
        # نحتاج مصفوفتين: واحدة للأيام، وواحدة للأرقام
        today = timezone.now().date()
        labels = []
        sent_data = []
        received_data = []

        for i in range(6, -1, -1): # لوب لآخر 7 أيام
            day = today - timedelta(days=i)
            day_label = day.strftime("%a") # Mon, Tue...
            
            # حساب رسائل هذا اليوم
            # ملاحظة: استخدم created_at__date للتصفية بالتاريخ فقط

            daily_msgs = Message.objects.filter(channel=channel, created_at__date=day)
            # الرسائل (إجمالي + تفصيل)
            all_msgs = Message.objects.filter(channel=channel)
            total_messages = all_msgs.count() # العدد الكلي (62)
            
            sent_count = all_msgs.filter(is_from_me=True).count()      # رسائلنا
            received_count = all_msgs.filter(is_from_me=False).count() # رسائل العملاء
                


            sent_count = daily_msgs.filter(is_from_me=True).count()
            received_count = daily_msgs.filter(is_from_me=False).count()
            
            labels.append(day_label)
            sent_data.append(sent_count)
            received_data.append(received_count)

        return JsonResponse({
            'success': True,
            'stats': {
                'contacts': total_contacts,
                'messages': total_messages,
                'campaigns': 0,
                'sent': sent_count,         # تفصيل
                'received': received_count, # تفصيل
            },
            'account': account_info,
            'chart': {
                'labels': labels,
                'sent': sent_data,
                'received': received_data
            }
        })

    except Exception as e:
        print(f"Dashboard Error: {e}")
        return JsonResponse({'error': str(e)}, status=500)






# path('privacy-policy/', views.privacy_policy, name='privacy_policy'),
# path('terms/', views.terms, name='terms'),
# path('data-deletion/', views.data_deletion, name='data_deletion'),
# path('contact/', views.contact, name='contact'),

 



from django.db.models import Count, Q, F, FloatField, Case, When, Value
from django.http import JsonResponse





from django.db.models import Count, Q, F, FloatField, Case, When, Value
from django.http import JsonResponse

from discount.models import CustomUser  # تأكد من استيراد مودل المستخدم الصحيح

def api_team_stats(request):
    user = request.user
    channel_id = request.GET.get('channel_id')
    
    # 1. تحديد القناة (مع التحقق من الصلاحيات)
    target_channel = get_target_channel(user, channel_id)
    
    if not target_channel:
        return JsonResponse({'stats': []})

    # 2. بناء الاستعلام (Query)
    # نريد الموظفين الذين ينطبق عليهم أحد الشروط التالية:
    # أ) هو مالك القناة (Owner)
    # ب) هو وكيل مضاف في القناة (Assigned Agent) -> نستخدم related_name="channels"
    # ج) لديه طلبات سابقة في هذه القناة (حتى لو تم حذفه من الوكلاء لاحقاً)
    
    users_qs = CustomUser.objects.filter(
        Q(id=target_channel.owner_id) |             # المالك
        Q(channels=target_channel) |                # الوكلاء (التصحيح هنا)
        Q(simple_orders__channel=target_channel)    # من لديهم طلبات
    ).distinct()

    # 3. الحسابات (Aggregation)
    # نحسب فقط الطلبات التابعة لهذه القناة (target_channel)
    confirmed_statuses = ['shipped', 'delivered', 'returned','confirmed']
    
    team_stats = users_qs.annotate(
        # العدد الكلي في هذه القناة
        total = Count('simple_orders', filter=Q(simple_orders__channel=target_channel)),

        # المؤكدة
        confirmed = Count('simple_orders', filter=Q(simple_orders__channel=target_channel, simple_orders__status__in=confirmed_statuses)),

        # الواصلة
        delivered = Count('simple_orders', filter=Q(simple_orders__channel=target_channel, simple_orders__status='delivered')),
        
        # باقي الحالات
        pending = Count('simple_orders', filter=Q(simple_orders__channel=target_channel, simple_orders__status='pending')),
        cancelled = Count('simple_orders', filter=Q(simple_orders__channel=target_channel, simple_orders__status='cancelled')),
        returned = Count('simple_orders', filter=Q(simple_orders__channel=target_channel, simple_orders__status='returned')),

    ).annotate(
        # حساب النسب المئوية
        conf_rate = Case(
            When(total__gt=0, then=F('confirmed') * 100.0 / F('total')),
            default=Value(0.0), output_field=FloatField()
        ),
        del_rate = Case(
            When(confirmed__gt=0, then=F('delivered') * 100.0 / F('confirmed')),
            default=Value(0.0), output_field=FloatField()
        )
    ).order_by('-total')

    # 4. تجهيز البيانات للواجهة
    data = []
    for agent in team_stats:
        # (اختياري) إخفاء من ليس لديهم أي نشاط في هذه القناة
        if agent.total == 0: 
            continue 
            
        data.append({
            'initial': agent.user_name or agent.first_name or agent.email.split('@')[0], # عرض الاسم أو جزء من الإيميل
            'name': (agent.email or agent.first_name or agent.email),
            'total': agent.total,
            'confirmed': agent.confirmed,
            'delivered': agent.delivered,
            'pending': agent.pending,
            'cancelled': agent.cancelled,
            'returned': agent.returned,
            'conf_rate': round(agent.conf_rate, 1),
            'del_rate': round(agent.del_rate, 1),
        })

    return JsonResponse({'stats': data})




def create_activity_log(channel, phone, content, user=None):
    """
    دالة لإنشاء رسالة نظام داخلية
    """
    # البحث عن أو إنشاء المحادثة/العميل
    contact = Contact.objects.get(phone=phone) # تأكد من الكود الخاص بك
    
    log  = Message.objects.create(
        channel=channel,
        sender=contact,
        body=content,      # مثال: "Conversation assigned to Ahmed"
        type='log',        # نوع جديد
        is_internal=True,  # رسالة داخلية
        is_from_me=True,      # نعتبرها منا لكي تظهر في اليمين (أو نخصص لها مكاناً في الوسط)
        status='read'      # لا تحتاج لحالة توصيل
    )
    
    log_payload = {
        "id": log.id,
        "body": log.body,  
        "type": "log",               
        "is_internal": True,
        "timestamp": log.created_at.strftime("%H:%M"),
        "sender_name": "System"       
    }
    

    # بيانات الغرفة/العميل
    socket_payload = {
        "contact": {
            "phone": contact.phone,
            "name": contact.name
        },
        "message": log_payload
    }
    from discount.channel.socket_utils import send_socket
   
    send_socket("log_message_received", socket_payload)



from django.views.decorators.http import require_POST
from django.contrib.auth import get_user_model

@require_POST
def assign_agent_to_contact(request):
    import json
    data = json.loads(request.body)
    
    phone = data.get('phone')
    agent_id = data.get('agent_id')
    
    # 1. جلب العميل
    try:
        contact = Contact.objects.get(phone=phone) # تأكد من اسم الحقل الصحيح لرقم الهاتف
    except Contact.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Contact not found'})

    # 2. جلب الموظف (أو إلغاء التعيين إذا كان agent_id فارغاً)
    if agent_id:
        try:
            agent = CustomUser.objects.get(id=agent_id)
            contact.assigned_agent = agent
            assigned_name = agent.user_name
            create_activity_log(contact.channel, phone, f"Conversation assigned to {agent.user_name}", user=request.user)
                
        except CustomUser.DoesNotExist:

            return JsonResponse({'success': False, 'message': 'Agent not found'})
    else:
        contact.assigned_agent = None
        assigned_name = "Unassigned"

    contact.save()
 
    return JsonResponse({'success': True, 'assigned_to': assigned_name})





from django.views.decorators.http import require_POST
from discount.models import Contact, CustomUser, Tags  

@require_POST
def update_contact_crm(request):
    import json
    data = json.loads(request.body)
    
    phone = data.get('phone')
    action = data.get('action') # 'agent', 'pipeline', 'add_tag', 'remove_tag'
    value = data.get('value')
    channel_id = data.get('channel_id')
    
    try:
        contact = Contact.objects.get(channel = WhatsAppChannel.objects.get(id=channel_id), phone=phone)
    except Contact.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Contact not found'})

    # 1. تحديث الموظف
    if action == 'agent':
        if value:
            # contact.assigned_agent_id = value
            agent = CustomUser.objects.get(id=value)
            create_activity_log(contact.channel, phone, f"Conversation assigned to {agent.user_name}", user=request.user)
            log_msg = f"تم تعيين المحادثة للموظف ID: {value}"
        else:
            contact.assigned_agent = None
            log_msg = "تم إلغاء التعيين"
        contact.save()

    # 2. تحديث المرحلة (Pipeline)
    elif action == 'pipeline':
        # التحقق من أن القيمة موجودة ضمن الخيارات
        if value in Contact.PipelineStage.values:
            contact.pipeline_stage = value
            contact.save()
            log_msg = f"تم تغيير المرحلة إلى: {value}"
        else:
            return JsonResponse({'success': False, 'message': 'Invalid stage'})

    # 3. إضافة تاج (Tag)
    elif action == 'add_tag':
        tag_name = value.strip()
        if tag_name:
            # 1. نحدد من هو المالك (الأدمن)
            # إذا كان المستخدم الحالي هو الأدمن نستخدمه، وإلا نستخدم الـ team_admin الخاص به
            owner = request.user if getattr(request.user, 'is_team_admin', False) else request.user.team_admin
            
            if not owner: # حالة حماية
                owner = request.user 

            # 2. نبحث عن التاج أو ننشئه (الخاص بهذا الأدمن فقط)
            tag, created = Tags.objects.get_or_create(
                name=tag_name, 
                admin=owner, # 🔥 مهم جداً للفصل بين المستخدمين
                defaults={'color': '#6366f1'} # لون افتراضي
            )
            
            # 3. نضيف التاج للعميل
            contact.tags.add(tag)
            
            log_msg = f"تمت إضافة وسم: {tag_name}"

    elif action == 'remove_tag':
        tag_name = value.strip()
        
        # نحدد المالك أيضاً للتأكد أننا نحذف التاج الصحيح
        owner = request.user if getattr(request.user, 'is_team_admin', False) else request.user.team_admin
        
        try:
            # نبحث عن التاج الخاص بهذا الأدمن
            tag = Tags.objects.get(name=tag_name, admin=owner)
            contact.tags.remove(tag)
            log_msg = f"تم حذف وسم: {tag_name}"
        except Tags.DoesNotExist:
            pass


   

    # (اختياري) تسجيل النشاط هنا create_activity_log(...)
    
    return JsonResponse({'success': True, 'message': log_msg})