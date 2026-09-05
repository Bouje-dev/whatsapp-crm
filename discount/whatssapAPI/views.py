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
from django.http import JsonResponse, HttpResponse, HttpResponseForbidden
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_GET, require_POST
from django.utils import timezone
from django.core.files.base import ContentFile
from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Max, Q
from django.core.paginator import Paginator
from discount.models import Message, SimpleOrder, Template, Order , Contact, WhatsAppChannel, CustomUser, ChatSession
from django.contrib.auth.decorators import login_required
from discount.activites import log_activity
from discount.services.plan_limits import check_plan_limit
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
        
        response = requests.get(media_url, headers=headers, timeout=30)
        if response.status_code != 200:
            return None
            
        media_data = response.json()
        download_url = media_data.get('url')
        
        if not download_url:
            return None
            
        # تحميل الملف
        download_response = requests.get(download_url, headers=headers, timeout=60)
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
             
            
            for entry in data.get("entry", []):
                for change in entry.get("changes", []):
                    value = change.get("value", {})

                    # Risk management kill-switch:
                    # If this webhook targets a suspended merchant/channel, abort immediately
                    # and never trigger AI replies to end-customers.
                    phone_number_id = (
                        (value.get("metadata") or {}).get("phone_number_id")
                        or value.get("phone_number_id")
                        or ""
                    )
                    if phone_number_id:
                        channel = WhatsAppChannel.objects.filter(phone_number_id=phone_number_id).first()
                        merchant_owner = getattr(channel, "owner", None) if channel else None
                        if merchant_owner and getattr(merchant_owner, "is_suspended", False):
                            logger.warning(
                                "WhatsApp webhook kill-switch: merchant suspended (owner=%s, phone_number_id=%s). Skipping.",
                                merchant_owner.id,
                                phone_number_id,
                            )
                            return HttpResponse("EVENT_RECEIVED", status=200)
                    
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
            errors = status.get('errors') or status.get('error')

            # Meta accepts the send with HTTP 200; delivery is async. This webhook tells you
            # if the message actually reached the user (delivered/read) or failed on-device/network.
            try:
                _blob = json.dumps(status, default=str)[:8000]
            except Exception:
                _blob = str(status)[:8000]
            print(
                "[Meta WhatsApp] status webhook",
                f"message_id={message_id!r}",
                f"status={status_value!r}",
                f"recipient_id={recipient_id!r}",
                f"errors={errors!r}",
                f"raw={_blob}",
            )
            logger.info(
                "[Meta WhatsApp] status webhook id=%s status=%s recipient_id=%s errors=%s",
                message_id,
                status_value,
                recipient_id,
                errors,
            )
            if status_value == "failed":
                logger.warning(
                    "[Meta WhatsApp] DELIVERY FAILED for wamid=%s errors=%s full=%s",
                    message_id,
                    errors,
                    _blob,
                )
                print(
                    "[Meta WhatsApp] DELIVERY FAILED — check errors above (user may block you, "
                    "invalid number, or client could not download media).",
                )

            # تحديث حالة الرسالة في قاعدة البيانات إذا لزم الأمر
            if message_id:
                try:
                    from discount.whatssapAPI.wa_status import (
                        normalize_whatsapp_delivery_status,
                        status_timestamp_from_meta_webhook,
                    )

                    message = Message.objects.get(message_id=message_id)
                    message.status = normalize_whatsapp_delivery_status(status_value)
                    message.status_timestamp = status_timestamp_from_meta_webhook(status)
                    message.save(update_fields=["status", "status_timestamp"])
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
    """
  Check whether the 24-hour customer-care window is open for this chat.
  Always returns HTTP 200 with can_send — used when opening a conversation, not as a send failure.
    """
    phone = request.GET.get("phone")
    channel_id = request.GET.get("channel_id")

    if not phone:
        return JsonResponse({
            "status": 200,
            "can_send": False,
            "error": "message not allowed",
            "reason": "Missing phone number.",
        })

    qs = Message.objects.filter(is_from_me=False)

    if channel_id:
        try:
            channel = WhatsAppChannel.objects.get(id=channel_id)
            resolved_sender = _resolve_message_sender_for_channel(channel, phone)
            qs = qs.filter(channel=channel, sender=resolved_sender)
        except (WhatsAppChannel.DoesNotExist, ValueError, TypeError):
            qs = qs.filter(sender=phone)
    else:
        qs = qs.filter(sender=phone)

    last_message = qs.order_by("-timestamp").first()

    if not last_message:
        return JsonResponse({
            "status": 200,
            "can_send": False,
            "error": "message not allowed",
            "reason": "you can not send msg to this user",
        })

    if timezone.now() - last_message.created_at > timedelta(hours=24):
        return JsonResponse({
            "status": 200,
            "can_send": False,
            "error": "message not allowed",
            "reason": "Message failed to send because more than 24 hours have passed since the customer last replied to this number.",
        })

    return JsonResponse({"status": 200, "can_send": True})

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
            print('temaplit' , res_data)
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
                media_type='template',
                user=request.user if request.user.is_authenticated else None,
            )
            log_activity('wa_message_sent', f"Template '{template_name}' to {to_number} via {channel.name}", request=request)
            return JsonResponse({"success": True, "wamid": wamid})

        # ============================================================
        # مسار 2: إرسال رسالة نصية (Text)
        # ============================================================
        elif msg_type == "text":
            body = (data.get("body") or data.get("message") or "").strip()
            if not body:
                return JsonResponse({"error": "Missing message body"}, status=400)
            payload = {
                "messaging_product": "whatsapp",
                "to": to_number.replace("+", "").strip(),
                "type": "text",
                "text": {"body": body[:4096]}
            }
            response = requests.post(url, headers=headers, json=payload)
            res_data = response.json()
            if response.status_code not in [200, 201]:
                return JsonResponse({"error": "Meta API Error", "details": res_data}, status=400)
            wamid = res_data.get("messages", [{}])[0].get("id")
            Message.objects.create(
                channel=channel,
                sender=to_number,
                is_from_me=True,
                body=body[:4096],
                message_id=wamid,
                status="sent",
                media_type="text",
                user=request.user if request.user.is_authenticated else None,
            )
            log_activity('wa_message_sent', f"Text message to {to_number} via {channel.name}", request=request)
            return JsonResponse({"success": True, "wamid": wamid})

        # ============================================================
        # مسار 3: إرسال وسائط (Media Upload)
        # ============================================================
        elif msg_type in ["image", "video", "document", "audio"]:
            pass

        return JsonResponse({"error": "Unsupported message type for this endpoint"}, status=400)

    except Exception as e:
        print(f"❌ Error in send_message: {e}")
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
@require_POST
def live_chat_audio_upload(request):
    """
    Live Chat voice note: multipart form `audio` → write to a real temp file on disk,
    FFmpeg to local Opus OGG, save to Message.media_file (S3 via django-storages),
    then upload the same local file to Meta /media and /messages.
    Always cleans up temp paths in `finally`.
    """
    from django.core.files import File
    from discount.whatssapAPI.process_messages import (
        _temp_suffix_from_filename_and_mime,
    )
    from discount.channel.socket_utils import send_socket

    if not request.user.is_authenticated:
        return JsonResponse({"ok": False, "error": "authentication_required"}, status=401)

    channel_id = request.POST.get("channel_id")
    to_raw = request.POST.get("to") or request.POST.get("phone")
    audio = request.FILES.get("audio")
    body_text = (request.POST.get("body") or "").strip()

    temp_input_path = None
    temp_mid_path = None
    temp_output_path = None
    saved_message = None

    try:
        if not audio:
            return JsonResponse({"ok": False, "error": "missing_audio", "details": "Expected request.FILES['audio']"}, status=400)
        if not to_raw:
            return JsonResponse({"ok": False, "error": "missing_recipient", "details": "POST field `to` is required"}, status=400)

        channel = get_target_channel(request.user, channel_id)
        if not channel:
            return JsonResponse({"ok": False, "error": "channel_denied"}, status=403)

        access_token = channel.access_token
        phone_id = channel.phone_number_id
        if not access_token or not phone_id:
            return JsonResponse({"ok": False, "error": "invalid_channel_config"}, status=500)

        to_number = str(to_raw).replace("+", "").strip()
        suffix = _temp_suffix_from_filename_and_mime(
            getattr(audio, "name", None) or "recording.webm",
            getattr(audio, "content_type", None) or "",
        ) or ".webm"

        in_fd, temp_input_path = tempfile.mkstemp(suffix=suffix)
        os.close(in_fd)
        with open(temp_input_path, "wb") as out_f:
            for chunk in audio.chunks():
                out_f.write(chunk)

        if not os.path.isfile(temp_input_path) or os.path.getsize(temp_input_path) <= 0:
            return JsonResponse({"ok": False, "error": "empty_incoming_audio"}, status=400)

        mid_fd, temp_mid_path = tempfile.mkstemp(suffix=".wav")
        os.close(mid_fd)
        out_fd, temp_output_path = tempfile.mkstemp(suffix=".ogg")
        os.close(out_fd)
        # Step 1 (Purify): rebuild headers/timestamps into PCM WAV @ 16k mono
        ffmpeg_step1 = [
            "ffmpeg",
            "-y",
            "-i",
            temp_input_path,
            "-ar",
            "16000",
            "-ac",
            "1",
            temp_mid_path,
        ]
        try:
            subprocess.run(ffmpeg_step1, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            logger.error("live_chat_audio_upload ffmpeg step1 failed stderr=%s", (e.stderr or "")[:4000])
            return JsonResponse(
                {"ok": False, "error": "ffmpeg_purify_failed", "details": "Could not purify WebM to WAV"},
                status=500,
            )
        if not os.path.isfile(temp_mid_path) or os.path.getsize(temp_mid_path) <= 0:
            return JsonResponse({"ok": False, "error": "empty_purified_wav"}, status=500)

        # Step 2 (Encode): strict WhatsApp Opus profile for PTT compatibility
        ffmpeg_step2 = [
            "ffmpeg",
            "-y",
            "-i",
            temp_mid_path,
            "-c:a",
            "libopus",
            "-b:a",
            "24k",
            "-vbr",
            "on",
            "-compression_level",
            "10",
            "-frame_duration",
            "60",
            "-application",
            "voip",
            temp_output_path,
        ]
        try:
            subprocess.run(ffmpeg_step2, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            logger.error("live_chat_audio_upload ffmpeg step2 failed stderr=%s", (e.stderr or "")[:4000])
            return JsonResponse(
                {"ok": False, "error": "ffmpeg_encode_failed", "details": "Could not encode WAV to Opus OGG"},
                status=500,
            )
        if not os.path.isfile(temp_output_path) or os.path.getsize(temp_output_path) <= 0:
            return JsonResponse({"ok": False, "error": "empty_converted_audio"}, status=500)

        saved_message = Message.objects.create(
            channel=channel,
            sender=to_number,
            is_from_me=True,
            body=body_text or "",
            user=request.user,
            media_type="audio",
            status="sent",
        )
        storage_name = f"live_chat_{uuid.uuid4().hex}.ogg"
        with open(temp_output_path, "rb") as local_f:
            saved_message.media_file.save(storage_name, File(local_f), save=True)

        api_ver = (channel.api_version or "v22.0").strip()
        fb_upload_url = f"https://graph.facebook.com/{api_ver}/{phone_id}/media"
        # CRITICAL: use a fresh file handle for Meta upload.
        # Never reuse the descriptor used by django-storages/S3 save path.
        with open(temp_output_path, "rb") as meta_fh:
            files = {"file": ("voice_message.ogg", meta_fh, "audio/ogg")}
            fb_res = requests.post(
                fb_upload_url,
                params={"messaging_product": "whatsapp", "access_token": access_token},
                files=files,
                timeout=80,
            )

        if fb_res.status_code not in (200, 201):
            try:
                saved_message.media_file.delete(save=False)
            except Exception:
                pass
            saved_message.delete()
            return JsonResponse(
                {"ok": False, "error": "meta_media_upload_failed", "details": fb_res.text},
                status=502,
            )

        try:
            fb_json = fb_res.json()
        except Exception:
            fb_json = {}
        media_id = fb_json.get("id")
        if not media_id:
            try:
                saved_message.media_file.delete(save=False)
            except Exception:
                pass
            saved_message.delete()
            return JsonResponse(
                {"ok": False, "error": "meta_media_missing_id", "details": fb_res.text},
                status=502,
            )

        saved_message.media_id = media_id
        saved_message.save(update_fields=["media_id"])

        msg_url = f"https://graph.facebook.com/{api_ver}/{phone_id}/messages"
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        send_payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_number,
            "type": "audio",
            "audio": {"id": media_id, "voice": True},
        }
        r = requests.post(msg_url, headers=headers, json=send_payload, timeout=30)

        if r.status_code not in (200, 201):
            try:
                saved_message.media_file.delete(save=False)
            except Exception:
                pass
            saved_message.delete()
            return JsonResponse(
                {"ok": False, "error": "whatsapp_messages_api_failed", "details": r.text, "status": r.status_code},
                status=502,
            )

        try:
            response_data = r.json()
            wa_message_id = None
            if response_data.get("messages"):
                wa_message_id = response_data["messages"][0].get("id")
            if wa_message_id:
                saved_message.message_id = wa_message_id
                saved_message.save(update_fields=["message_id"])
        except Exception:
            pass

        try:
            session = ChatSession.objects.filter(
                channel=channel, customer_phone=str(to_number).strip()
            ).order_by("-last_interaction").first()
            if session:
                session.last_manual_message_at = timezone.now()
                session.save(update_fields=["last_manual_message_at"])
        except Exception:
            pass

        media_url = ""
        try:
            if saved_message.media_file:
                media_url = saved_message.media_file.url
        except Exception:
            media_url = ""

        owner_id = channel.owner_id
        group_name = f"team_updates_{owner_id}" if owner_id else "webhook_events"

        final_payload = {
            "status": r.status_code,
            "whatsapp_response": r.text,
            "saved_message_id": saved_message.id,
            "media_id": media_id,
            "body": body_text,
            "to": to_number,
            "captions": body_text,
            "media_type": "audio",
            "url": media_url,
            "media_url": media_url,
        }
        sidebar_payload = {
            "phone": to_number,
            "name": to_number,
            "snippet": "audio",
            "timestamp": timezone.now().strftime("%H:%M"),
            "unread": 0,
            "last_status": "sent",
            "fromMe": True,
            "channel_id": channel.id,
        }
        send_socket("finished", final_payload, group_name=group_name)
        send_socket("update_sidebar_contact", sidebar_payload, group_name=group_name)

        log_activity(
            "wa_message_sent",
            f"Live Chat audio (local-first) to {to_number} via {channel.name}",
            request=request,
        )

        return JsonResponse(
            {
                "ok": True,
                "saved_message_id": saved_message.id,
                "wamid": getattr(saved_message, "message_id", None),
                "media_id": media_id,
                "media_url": media_url,
            }
        )

    except Exception as e:
        logger.exception("live_chat_audio_upload: %s", e)
        if saved_message is not None:
            try:
                saved_message.media_file.delete(save=False)
            except Exception:
                pass
            try:
                saved_message.delete()
            except Exception:
                pass
        return JsonResponse({"ok": False, "error": "server_error", "details": str(e)}, status=500)
    finally:
        for p in (temp_input_path, temp_mid_path, temp_output_path):
            if not p:
                continue
            try:
                if os.path.isfile(p):
                    os.remove(p)
            except OSError:
                pass


def _message_to_chat_dict(m, request):
    """Serialize a Message row for the live chat JSON API."""
    from discount.whatssapAPI.wa_status import normalize_whatsapp_delivery_status

    msg_type = ''
    Type = getattr(m, 'type', None)
    if Type:
        msg_type = Type
    else:
        msg_type = getattr(m, 'media_type', 'text')
    media_file = getattr(m, 'media_file', None)
    media_url = None
    raw_st = getattr(m, "status", None)
    status = normalize_whatsapp_delivery_status(raw_st) if raw_st else "sent"
    if media_file:
        try:
            url_attr = getattr(media_file, 'url', None)
            if url_attr:
                media_url = request.build_absolute_uri(url_attr)
            else:
                media_name = str(media_file).strip()
                if not media_name:
                    media_url = None
                elif media_name.startswith('http://') or media_name.startswith('https://'):
                    media_url = media_name
                else:
                    media_path = media_name.lstrip('/')
                    base = settings.MEDIA_URL or '/media/'
                    if not base.endswith('/'):
                        base = base + '/'
                    if media_path.startswith(base.lstrip('/')):
                        media_url = request.build_absolute_uri('/' + media_path)
                    else:
                        media_url = request.build_absolute_uri(base + media_path)
        except Exception:
            media_url = None
    else:
        media_url = getattr(m, 'media_url', None)

    note_author = None
    if getattr(m, "user_id", None):
        note_author = m.user.username if m.user else None
    elif (getattr(m, "type", None) or "") == "note" and getattr(m, "name", None):
        note_author = (m.name or "").strip() or None

    # ── Digital-delivery spoiler flags ────────────────────────────────────
    # IMPORTANT: This serializer is the chat-LIST payload. We MUST emit
    # only the boolean facts the bubble renderer needs to draw the blurred
    # spoiler UI. The actual ciphertext (`encrypted_asset`) and any
    # decrypted plaintext NEVER leave the server here — disclosure happens
    # exclusively through the strict owner-gated reveal endpoint
    # (`api_reveal_asset`). Leaking either field here would defeat the
    # entire RBAC model.
    is_digital_delivery = bool(getattr(m, 'is_digital_delivery', False))
    has_protected_asset = bool(is_digital_delivery and getattr(m, 'encrypted_asset', None))

    interactive = None
    try:
        from discount.whatssapAPI.process_messages import decode_interactive_captions
        interactive = decode_interactive_captions(getattr(m, "captions", None), m.body)
    except Exception:
        interactive = None

    # Inbound button taps are stored as type=interactive with no card JSON.
    # Expose them as text so the inbox never drops them.
    out_type = msg_type
    if str(msg_type or "").lower() == "interactive" and not interactive:
        out_type = "text"

    created = getattr(m, "created_at", None) or getattr(m, "timestamp", None)
    time_str = created.strftime("%H:%M") if created else ""
    timestamp_str = created.strftime("%Y-%m-%d %H:%M") if created else ""

    return {
        "id": m.id,
        "body": m.body,
        "fromMe": bool(m.is_from_me),
        "time": time_str,
        "type": out_type,
        "url": media_url,
        "status": status,
        "user": note_author,
        "timestamp": timestamp_str,
        "captions": m.captions,
        "interactive": interactive,
        "is_digital_delivery": is_digital_delivery,
        "has_protected_asset": has_protected_asset,
    }


def _digits_only_phone(s):
    return re.sub(r"\D", "", (s or ""))


def _resolve_message_sender_for_channel(channel, phone_param):
    """
    Message.sender may not match the UI phone string (with/without +, national vs international).
    Resolve to the sender value actually stored on Message rows so we mark the right rows read.
    """
    raw = (phone_param or "").strip()
    if not raw:
        return raw
    dq = _digits_only_phone(raw)
    if not dq:
        return raw
    if Message.objects.filter(channel=channel, sender=raw).exists():
        return raw
    best = None
    for s in (
        Message.objects.filter(channel=channel)
        .values_list("sender", flat=True)
        .distinct()
    ):
        sd = _digits_only_phone(str(s))
        if not sd:
            continue
        if sd == dq:
            return str(s)
        if len(dq) >= 9 and len(sd) >= 9 and (
            sd.endswith(dq[-9:]) or dq.endswith(sd[-9:])
        ):
            best = str(s)
    return best if best else raw


def _contact_for_channel_phone(channel, phone_param, resolved_sender):
    """CRM lookup when Contact.phone uses the same or a different format."""
    c = Contact.objects.filter(channel=channel, phone=resolved_sender).first()
    if c:
        return c
    dq = _digits_only_phone(phone_param or resolved_sender or "")
    if not dq:
        return None
    for row in Contact.objects.filter(channel=channel):
        if _digits_only_phone(row.phone) == dq:
            return row
    return None


# Statuses on a digital order that still need merchant action on a payment
# receipt. `pending_payment`  = waiting for the customer to send a receipt.
# `pending_verification`     = receipt received, merchant must approve/reject.
_ACTIVE_DIGITAL_ORDER_STATUSES = ("pending_payment", "pending_verification")
_SUPPORT_REVIEW_STATUS = "under_review"


def _active_digital_order_for(channel, phone_param, resolved_sender):
    """
    Return the latest still-actionable digital order for the open chat
    `(channel, customer_phone)`, or None.

    "Actionable" = is_digital=True AND status in (pending_payment,
    pending_verification). We try the resolved sender first (matches what
    `submit_customer_order` saves), then fall back to a digits-only match
    to be robust against legacy rows stored with/without `+` or spaces.
    """
    try:
        from discount.models import SimpleOrder
    except Exception:
        return None

    if not channel:
        return None

    candidates = []
    if resolved_sender:
        candidates.append(resolved_sender)
    if phone_param and phone_param not in candidates:
        candidates.append(phone_param)

    base_qs = (
        SimpleOrder.objects
        .filter(
            channel=channel,
            is_digital=True,
            status__in=_ACTIVE_DIGITAL_ORDER_STATUSES,
        )
        .select_related('product')
        .order_by('-created_at')
    )

    for cand in candidates:
        order = base_qs.filter(customer_phone=cand).first()
        if order:
            return order

    # Fallback: digit-only suffix match (handles +212 vs 212 vs 0X formatting)
    dq = _digits_only_phone(phone_param or resolved_sender or "")
    if not dq or len(dq) < 9:
        return None
    tail = dq[-9:]
    for order in base_qs.iterator(chunk_size=50):
        if (_digits_only_phone(order.customer_phone or "") or "").endswith(tail):
            return order
    return None


def _active_support_review_order_for(channel, phone_param, resolved_sender):
    """Latest completed digital order awaiting merchant support review."""
    try:
        from discount.services.post_sale_support import active_support_review_order
        return active_support_review_order(channel, phone_param, resolved_sender)
    except Exception:
        return None


def _serialize_support_review_order(order):
    try:
        from discount.services.post_sale_support import serialize_support_review_order
        return serialize_support_review_order(order)
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════════════
# Digital-delivery spoiler — labelled placeholder body builder
# ══════════════════════════════════════════════════════════════════════════
#
# These helpers compose the `Message.body` HTML for an outgoing digital-
# delivery fulfillment message. Labels are rendered as plaintext on the
# row (everyone in the dashboard sees "Email:", "🔗 Link:", etc.) while
# every sensitive value lives behind a CSS-blurred placeholder span that
# only the strict owner can decrypt via `api_reveal_asset`.
#
# Field config keys must match the keys in the dict passed to
# `Message.set_encrypted_asset(...)` so the JS reveal step can look up
# each value by its `data-field` attribute.
_SPOILER_FIELD_CONFIG = {
    "link":     {"label": "🔗 Link:",          "mask": "*" * 24},
    "email":    {"label": "📧 Email:",         "mask": "*" * 18},
    "password": {"label": "🔑 Password:",      "mask": "*" * 14},
    "username": {"label": "👤 Username:",      "mask": "*" * 14},
    "license":  {"label": "🗝️ License key:",   "mask": "*" * 20},
    "token":    {"label": "🪪 Token:",         "mask": "*" * 20},
}
_SPOILER_DEFAULT_FIELD = "link"


def _render_spoiler_body_html(message_id, field_keys, public_body=""):
    """
    Compose the `Message.body` HTML used by the dashboard chat bubble.

    Output shape (example, all server-controlled — safe to render via
    innerHTML for digital-delivery messages):

        شكراً على ثقتك فينا! 🎉<br>هاهو رابط تحميل المنتج ديالك:<br><br>
        🔗 الرابط: <span class="spoiler-text trigger-decrypt"
                          data-id="123" data-field="link"
                          title="انقر لفك التشفير">************************</span>

    `field_keys` is an iterable of field names; unknown keys fall back to
    the default link config so the row always renders something.
    """
    import html as _html
    parts = []
    if public_body:
        # Server-controlled message, but escape defensively in case a
        # merchant ever lets customers craft these strings.
        parts.append(_html.escape(public_body).replace("\n", "<br>"))
        parts.append("<br><br>")
    for key in field_keys:
        cfg = _SPOILER_FIELD_CONFIG.get(key) or _SPOILER_FIELD_CONFIG[_SPOILER_DEFAULT_FIELD]
        parts.append(_html.escape(cfg["label"]))
        parts.append(" ")
        parts.append(
            '<span class="spoiler-text trigger-decrypt" '
            'data-id="{mid}" data-field="{field}" '
            'title="Click to reval">{mask}</span>'.format(
                mid=int(message_id),
                field=_html.escape(key),
                mask=cfg["mask"],
            )
        )
        parts.append("<br>")
    # Drop the trailing <br> for a tidy bubble.
    if parts and parts[-1] == "<br>":
        parts.pop()
    return "".join(parts)


def _serialize_active_digital_order(order):
    """Compact JSON payload consumed by the dashboard payment-banner UI."""
    if not order:
        return None
    try:
        price = float(order.price) if order.price is not None else 0.0
    except (TypeError, ValueError):
        price = 0.0
    catalog_price = None
    try:
        prod = getattr(order, "product", None)
        if prod is not None and getattr(prod, "price", None) is not None:
            catalog_price = float(prod.price)
    except (TypeError, ValueError):
        catalog_price = None
    is_negotiated = (
        catalog_price is not None
        and price > 0
        and price < catalog_price - 0.001
    )
    return {
        "id": order.order_id,
        "status": order.status,
        "total_price": price,
        "catalog_price": catalog_price,
        "is_negotiated": is_negotiated,
        "currency": order.currency or "MAD",
        "product_name": (
            getattr(order, "product_name", None)
            or (getattr(order.product, "name", "") if getattr(order, "product", None) else "")
            or ""
        ),
        "customer_name": order.customer_name or "",
        "customer_phone": order.customer_phone or "",
        "created_at": order.created_at.isoformat() if order.created_at else None,
    }


@require_GET
def get_messages1(request):
    """
    GET /api/get_messages/?phone=<phone>&channel_id=<id>

    History (newest page first, then scroll up for older):
      - limit=10 (default, max 50)
      - before_id=<id>  optional cursor for the next *older* page (messages with id < before_id)

    Incremental sync (polling / modal): since_id>0 returns messages with id > since_id (ascending, capped).

    Response: messages oldest→newest within the chunk, has_older_messages, optional oldest_id/newest_id.
    """
    channel_id = request.GET.get('channel_id')
    tracking = request.GET.get('tracking')
    phone = request.GET.get('phone')
    since_id_raw = request.GET.get('since_id')
    before_id_raw = request.GET.get('before_id')
    limit_raw = request.GET.get('limit', '10')

    empty = {"messages": [], "has_older_messages": False, "crm_data": {}}

    if not phone:
        return JsonResponse(empty)

    try:
        limit = int(limit_raw)
        limit = max(1, min(limit, 50))
    except ValueError:
        limit = 10

    if not channel_id:
        return JsonResponse(empty)

    try:
        channel = WhatsAppChannel.objects.get(id=channel_id)
    except (WhatsAppChannel.DoesNotExist, ValueError, TypeError):
        return JsonResponse(empty)

    resolved_sender = _resolve_message_sender_for_channel(channel, phone)
    qs_base = Message.objects.filter(sender=resolved_sender, channel=channel)

    # --- Incremental: only new messages after since_id (skip pagination) ---
    since_val = None
    if since_id_raw not in (None, ''):
        try:
            since_val = int(since_id_raw)
        except ValueError:
            since_val = None

    # --- Paginated history cursor ---
    before_val = None
    if before_id_raw not in (None, ''):
        try:
            before_val = int(before_id_raw)
        except ValueError:
            before_val = None

    # Opening the chat (not scrolling older pages): mark ALL inbound unread for this thread.
    # Paginated fetch only loads the latest N messages; outbound/template messages after an
    # old customer reply can push unread inbound rows out of that page (common after 24h+).
    is_initial_open = before_val is None and not (since_val is not None and since_val > 0)
    if is_initial_open and resolved_sender:
        now = timezone.now()
        qs_base.filter(is_from_me=False, is_read=False).update(is_read=True, read_at=now)

    if since_val is not None and since_val > 0:
        qs = qs_base.filter(id__gt=since_val).order_by('id')[:200]
        messages = []
        for m in qs:
            if not m.is_read:
                m.is_read = True
                m.read_at = timezone.now()
                m.save(update_fields=['is_read', 'read_at'])
            messages.append(_message_to_chat_dict(m, request))
        return JsonResponse({
            "messages": messages,
            "has_older_messages": False,
            "oldest_id": messages[0]["id"] if messages else None,
            "newest_id": messages[-1]["id"] if messages else None,
            "crm_data": None,
        })

    # --- Paginated history ---
    if before_val is not None:
        page_qs = qs_base.filter(id__lt=before_val).order_by('-id')[:limit]
    else:
        page_qs = qs_base.order_by('-id')[:limit]

    batch = list(page_qs)
    batch.reverse()

    min_id = batch[0].id if batch else None
    has_older = False
    if min_id is not None:
        has_older = qs_base.filter(id__lt=min_id).exists()

    contact_crm_data = {}
    if not tracking and before_val is None:
        contact = _contact_for_channel_phone(channel, phone, resolved_sender)
        if contact:
            contact_crm_data = {
                'pipeline_stage': contact.pipeline_stage if contact.pipeline_stage else None,
                'assigned_agent_id': contact.assigned_agent_id,
                'tags': [
                    {'name': tag.name, 'color': tag.color}
                    for tag in contact.tags.all()
                ],
            }

    messages = []
    load_older = before_val is not None
    for m in batch:
        messages.append(_message_to_chat_dict(m, request))

    # Only attach the payment banner payload on the initial chat-open call
    # (not on older-page scrolls). The polling branch above never hits this
    # tail, so older pages keep the banner the dashboard already painted.
    active_digital_order_payload = None
    active_support_review_payload = None
    if not load_older:
        active_digital_order_payload = _serialize_active_digital_order(
            _active_digital_order_for(channel, phone, resolved_sender)
        )
        active_support_review_payload = _serialize_support_review_order(
            _active_support_review_order_for(channel, phone, resolved_sender)
        )

    return JsonResponse({
        "messages": messages,
        "has_older_messages": has_older,
        "oldest_id": min_id,
        "newest_id": batch[-1].id if batch else None,
        "crm_data": contact_crm_data,
        "active_digital_order": active_digital_order_payload,
        "active_support_review": active_support_review_payload,
    })


@login_required
@require_GET
def api_export_conversation_transcript(request):
    """
    Superadmin-only: full WhatsApp thread as plain text (customer, system, notes).
    GET ?phone=&channel_id=
    """
    if not getattr(request.user, "is_superuser", False):
        return JsonResponse({"success": False, "error": "Forbidden"}, status=403)

    channel_id = request.GET.get("channel_id")
    phone = request.GET.get("phone")
    if not channel_id or not phone:
        return JsonResponse({"success": False, "error": "phone and channel_id required"}, status=400)
    try:
        channel = WhatsAppChannel.objects.get(id=channel_id)
    except (WhatsAppChannel.DoesNotExist, ValueError, TypeError):
        return JsonResponse({"success": False, "error": "Channel not found"}, status=404)

    resolved_sender = _resolve_message_sender_for_channel(channel, phone)
    qs = (
        Message.objects.filter(sender=resolved_sender, channel=channel)
        .select_related("user")
        .order_by("timestamp", "id")
    )
    contact = _contact_for_channel_phone(channel, phone, resolved_sender)
    contact_name = ""
    if contact:
        contact_name = (getattr(contact, "name", None) or getattr(contact, "profile_name", None) or "").strip()

    from django.utils.html import strip_tags

    def _plain(text):
        raw = strip_tags(text or "").replace("\xa0", " ").strip()
        return raw or ""

    now = timezone.localtime(timezone.now())
    phone_label = (phone or resolved_sender or "").strip()
    lines = [
        "WhatsApp conversation transcript",
        f"Exported at: {now.strftime('%Y-%m-%d %H:%M:%S')}",
        f"Channel ID: {channel.id}",
        f"Customer: {contact_name or '—'} ({phone_label})",
        "",
        "=" * 60,
        "",
    ]
    count = 0
    for m in qs.iterator(chunk_size=200):
        count += 1
        created = getattr(m, "created_at", None) or getattr(m, "timestamp", None)
        when = timezone.localtime(created).strftime("%Y-%m-%d %H:%M:%S") if created else "—"
        msg_type = (getattr(m, "type", None) or "").strip().lower()
        is_note = msg_type == "note" or bool(getattr(m, "is_internal", False))
        if is_note:
            author = ""
            if getattr(m, "user_id", None) and m.user:
                author = (getattr(m.user, "username", None) or "").strip()
            if not author:
                author = (getattr(m, "name", None) or "").strip() or "Unknown"
            role = f"NOTE ({author})"
        elif getattr(m, "is_from_me", False):
            role = "SYSTEM"
        else:
            role = "CUSTOMER"
        body = _plain(m.body) or _plain(getattr(m, "captions", None))
        media_hint = ""
        media_type = (getattr(m, "media_type", None) or "").strip().lower()
        if not body:
            if media_type:
                media_hint = f"[{media_type}]"
            elif msg_type in ("image", "video", "audio", "document", "sticker"):
                media_hint = f"[{msg_type}]"
        lines.append(f"[{when}] {role}:")
        if body:
            lines.append(body)
        if media_hint:
            lines.append(media_hint)
        lines.append("")

    if count == 0:
        lines.append("(No messages in this conversation.)")
        lines.append("")

    text = "\n".join(lines).rstrip() + "\n"
    safe_phone = re.sub(r"\D", "", phone_label) or "chat"
    filename = f"chat-{safe_phone}-{now.strftime('%Y%m%d-%H%M')}.txt"
    return JsonResponse({
        "success": True,
        "filename": filename,
        "text": text,
        "message_count": count,
    })


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

        # 6. فلتر غير المقروء (Unread Only) / المقروء (Read Only)
        read_only = request.GET.get('read_only') == 'true'
        if unread_only:
            conversations = conversations.filter(unread_count__gt=0)
        elif read_only:
            conversations = conversations.filter(unread_count=0)

        # 7. الترقيم (Pagination)
        try:
            page_size = max(1, min(50, int(request.GET.get("page_size", 10))))
        except (TypeError, ValueError):
            page_size = 10
        paginator = Paginator(conversations, page_size)
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

        # HITL: which senders have AI disabled (Needs Human Action)
        needs_human_phones = set(
            ChatSession.objects.filter(
                channel=target_channel,
                customer_phone__in=senders_phones,
                ai_enabled=False,
            ).values_list('customer_phone', flat=True)
        )

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
                elif (msg.type or '') == 'interactive':
                    snippet = (msg.body or '🔘 Buttons')[:50]
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
                "assigned_agent_id": assigned_agent_id,
                "needs_human": phone in needs_human_phones,
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

    # 2. تحديد القنوات
    if getattr(user, 'is_team_admin', False) or user.is_superuser:
         # ملاحظة: تأكد أن المنطق هنا يطابق مودلز مشروعك (هل الأدمن هو الـ owner؟)
        allowed_channels = WhatsAppChannel.objects.filter(owner=user)
    else:
        allowed_channels = WhatsAppChannel.objects.filter(assigned_agents=user)

    # 3. استقبال وتنظيف البيانات (🔥 التصحيح هنا 🔥)
    req_channel_id = request.GET.get('channel_id')
    stage_filter = request.GET.get('stage')

    # تنظيف channel_id
    if req_channel_id in ['null', 'undefined', '']:
        req_channel_id = None
        
    # تنظيف stage_filter (هذا هو سبب المشكلة سابقاً)
    if stage_filter in ['null', 'undefined', 'all', '']:
        stage_filter = None

    # تحديد القناة المستهدفة
    target_channel = None
    if req_channel_id:
        target_channel = allowed_channels.filter(id=req_channel_id).first()
    else:
        target_channel = allowed_channels.first()

    if not target_channel:
        return JsonResponse({"contacts": [], "total_pages": 0})

    # 4. بناء الكويري
    contacts_qs = Contact.objects.filter(channel=target_channel) 
     
    

    if stage_filter:
        contacts_qs = contacts_qs.filter(pipeline_stage=stage_filter)
        print(f"Stage filter: {stage_filter} , contacts count: {contacts_qs}"  )

    # 5. البحث
    search_query = request.GET.get('q', '').strip()
    if search_query:
        contacts_qs = contacts_qs.filter(
            Q(name__icontains=search_query) | 
            Q(phone__icontains=search_query)
        )

    # 6. الترتيب والفلترة الإضافية
    filter_type = request.GET.get('filter', 'all')
    
    if filter_type == 'important':
        # تأكدنا من وجود الحقل لتجنب الأخطاء
        if hasattr(Contact, 'is_important'): 
            contacts_qs = contacts_qs.filter(is_important=True)
            
    elif filter_type == 'recent':
        contacts_qs = contacts_qs.order_by('-last_interaction')
    else:
        contacts_qs = contacts_qs.order_by('-last_interaction')

    # 7. الترحيل (Pagination)
    page_number = request.GET.get('page', 1)
    page_size = 20 
    paginator = Paginator(contacts_qs, page_size)
    page_obj = paginator.get_page(page_number)

    contacts_list = []
    for contact in page_obj:
        contacts_list.append({
            'id': contact.id,
            'phone': contact.phone,
            'name': contact.name or contact.phone,
            'last_interaction': contact.last_interaction.strftime("%Y-%m-%d %H:%M") if contact.last_interaction else "-",
            # التحقق من وجود الحقل لتجنب كراش إذا كان المودل قيد التطوير
            'created_at': contact.created_at.strftime("%Y-%m-%d") if hasattr(contact, 'created_at') and contact.created_at else None,
            'profile_picture': contact.profile_picture.url if contact.profile_picture else None,
            'is_important': getattr(contact, 'is_important', False),
            'channel_name': target_channel.name,
            'channel_id': target_channel.id,
            'assigned_agent_id': contact.assigned_agent_id , # تأكد أن هذا الحقل يعيد ID وليس object
            
            # 🔥 إضافة مفيدة: إعادة المرحلة الحالية للفرونت إند
            'pipeline_stage': contact.pipeline_stage 
        })
    
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
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.core.exceptions import ValidationError
import json
import logging
from datetime import datetime

# تعريف استثناء مخصص للتعامل مع أخطاء ميتا داخل المعاملة
class MetaSubmissionError(Exception):
    def __init__(self, message, detail=None):
        self.message = message
        self.detail = detail
        super().__init__(self.message)

@require_POST
def create_template(request):
    try:
        # 1. Basic Fields Extraction
        user = request.user 
        name = (request.POST.get('name') or '').strip()
        category = (request.POST.get('category') or '').strip()
        language = (request.POST.get('language') or '').strip()
        status = (request.POST.get('status') or '').strip()
        updated_raw = (request.POST.get('updated') or '').strip()
        body = (request.POST.get('body') or '').strip()
        footer = (request.POST.get('footer') or '').strip()
        header_type = (request.POST.get('header_type') or 'text').strip()

        # Files
        header_image = request.FILES.get('header_image')
        header_video = request.FILES.get('header_video')
        header_document = request.FILES.get('header_document')
        
        channel_id = request.POST.get('channel_id')
        if not channel_id: 
            return JsonResponse({'success': False, 'errors': 'channel_id is required'}, status=400)
        
        # 2. Authorization & Channel Retrieval
        try:
            if user.is_superuser or getattr(user, 'is_team_admin', False) or user.is_staff:
                channel = WhatsAppChannel.objects.get(id=channel_id)
            else:
                channel = WhatsAppChannel.objects.get(assigned_agents=user, id=channel_id)
        except WhatsAppChannel.DoesNotExist:
            return JsonResponse({'success': False, 'errors': 'Channel not found or access denied'}, status=404)

        # ---------------------------------------------------------
        # [NEW] Requirement 2: Prevent Duplicates
        # Check if a template with the same name already exists for this channel
        # ---------------------------------------------------------
        if Template.objects.filter(channel=channel, name=name).exists():
            return JsonResponse({
                'success': False, 
                'error': f'A template with the name "{name}" already exists for this channel.'
            }, status=400)

        # 3. Validation Logic
        errors = []
        if not name: errors.append('name is required')
        elif len(name) > MAX_NAME_LENGTH: errors.append(f'name max length is {MAX_NAME_LENGTH}')
        
        if not body: errors.append('body is required')
        elif len(body) > MAX_BODY_LENGTH: errors.append(f'body max length is {MAX_BODY_LENGTH}')

        if header_type not in ALLOWED_HEADER_TYPES: errors.append('invalid header_type')

        header_text_val = (request.POST.get('header_text') or '').strip()
        if header_type == 'text' and len(header_text_val) > 60:
            return JsonResponse({'success': False, 'error': 'Header text must be 60 characters or fewer (WhatsApp limit).'}, status=400)
        if header_type == 'image' and not header_image:
            return JsonResponse({'success': False, 'error': 'Image header requires an image file.'}, status=400)
        if header_type == 'video' and not header_video:
            return JsonResponse({'success': False, 'error': 'Video header requires a video file.'}, status=400)
        if header_type == 'document' and not header_document:
            return JsonResponse({'success': False, 'error': 'Document header requires a file (PDF or Word).'}, status=400)

        # Parse JSON fields
        body_samples_raw, err = parse_json_field(request.POST, 'body_samples')
        if err: errors.append(err)
        
        buttons_raw, err2 = parse_json_field(request.POST, 'buttons')
        if err2: errors.append(err2)

        if errors:
            return JsonResponse({'success': False, 'errors': errors}, status=400)

        # 4. Body Placeholders Validation
        placeholders = extract_placeholders(body)
        if len(placeholders) > MAX_PLACEHOLDERS:
            return JsonResponse({'success': False, 'error': f'Too many placeholders, max {MAX_PLACEHOLDERS}'}, status=400)
        if not placeholders_are_sequential(placeholders):
            return JsonResponse({'success': False, 'error': 'Placeholders must be sequential 1..N without gaps'}, status=400)

        max_placeholder = max(placeholders) if placeholders else 0

        # Validate Body Samples
        samples = []
        if max_placeholder > 0:
            if body_samples_raw is None:
                return JsonResponse({'success': False, 'error': 'body_samples missing for placeholders'}, status=400)
            if not isinstance(body_samples_raw, list):
                return JsonResponse({'success': False, 'error': 'body_samples must be an array'}, status=400)
            if len(body_samples_raw) != max_placeholder:
                return JsonResponse({'success': False, 'error': f'body_samples length must match placeholders count ({max_placeholder})'}, status=400)
            
            for i, s in enumerate(body_samples_raw, 1):
                if not isinstance(s, dict) or s.get('type') != 'text':
                    return JsonResponse({'success': False, 'error': f'body_samples[{i-1}] must be object with type "text"'}, status=400)
                samples.append({'type': 'text', 'text': str(s.get('text') or '')})

        # Validate Buttons
        clean_buttons = []
        if buttons_raw:
            clean_buttons, btn_err = validate_buttons(buttons_raw)
            if btn_err:
                return JsonResponse({'success': False, 'error': btn_err}, status=400)

        # Validate Media Files
        media_map = {
            'image': header_image,
            'video': header_video,
            'document': header_document
        }
        if header_type in media_map and media_map[header_type]:
             err = validate_uploaded_file(media_map[header_type], header_type)
             if err: return JsonResponse({'success': False, 'error': err}, status=400)

        # Normalize Body
        body_normalized = normalize_body_placeholders(body)

        # Parse Date
        updated_date = None
        if updated_raw:
            try:
                updated_date = datetime.strptime(updated_raw, '%Y-%m-%d').date()
            except ValueError:
                return JsonResponse({'success': False, 'error': 'updated must be in YYYY-MM-DD format'}, status=400)

        # ---------------------------------------------------------
        # [NEW] Requirement 1: Save only if Meta Success (Atomic Transaction)
        # ---------------------------------------------------------
        try:
            with transaction.atomic():
                # A. Create Local Object (Draft)
                template = Template.objects.create(
                    channel=channel,
                    user=user,
                    name=name,
                    category=category,
                    language=language,
                    status=status, # Likely 'draft' initially
                    updated_at=updated_date,
                    body=body_normalized,
                    footer=footer,
                    header_type=header_type,
                    header_text=header_text_val,
                )

                # Save Files
                if header_image:
                    template.header_image = header_image
                if header_video:
                    template.header_video = header_video
                if header_document:
                    template.header_document = header_document

                sv_map = {}
                for i, item in enumerate(samples, 1):
                    sv_map[str(i)] = str(item.get('text', '') or '')
                template.sample_values = sv_map
                template.buttons = clean_buttons

                template.save()

                # B. Submit to Meta
                # IMPORTANT: We pass the created object to the function
                meta_result = submit_template_to_meta(template, channel, user)

                if meta_result.get('ok'):
                    # C. Success Scenario
                    template.status = 'pending' # Meta usually starts as pending/review
                    meta_id = meta_result.get('meta_id')
                    if meta_id:
                        template.template_id = meta_id
                    
                    template.components = meta_result.get('response') or {}
                    template.save()
                    
                    log_activity('wa_template_created', f"Template '{name}' created for {channel.name}", request=request, related_object=template)
                    return JsonResponse({'success': True, 'id': template.id, 'meta_id': template.template_id})
                
                else:
                    # D. Failure Scenario
                    # RAISE an exception to trigger transaction.atomic() ROLLBACK
                    # This ensures the template created in step A is removed from DB.
                    error_msg = str(meta_result.get('error'))
                    error_detail = meta_result.get('response')
                    raise MetaSubmissionError(error_msg, error_detail)

        except MetaSubmissionError as mse:
            # Catch our custom error outside the atomic block
            # The DB rollback has already happened here.
            return JsonResponse({
                'success': False,
                'error': f"Failed to submit to Meta: {mse.message}",
                'detail': mse.detail
            }, status=400)

    except Exception as e:
        import traceback
        logging.exception('create_template unexpected error')
        return JsonResponse({'success': False, 'error': 'Internal server error', 'details': str(e)}, status=500)


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
        header_document = request.FILES.get('header_document')
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

        if header_document:
            template.header_document = header_document

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
    # Always include channels the user OWNS (owner FK) OR is assigned to as a team agent.
    # Previously only assigned_agents was checked for non-superusers, which meant channel
    # owners who were not also in assigned_agents got None back and saw empty data everywhere.
    from django.db.models import Q as _Q
    if user.is_superuser or getattr(user, 'is_team_admin', False):
        qs = WhatsAppChannel.objects.filter(_Q(owner=user) | _Q(assigned_agents=user)).distinct()
    else:
        qs = WhatsAppChannel.objects.filter(_Q(owner=user) | _Q(assigned_agents=user)).distinct()

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
                'components': template.components,
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
                    'components': template.components,
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





def _user_can_manage_simple_order(user, order):
    """Same access rules as api_orders list + sync."""
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    if not order.channel:
        return order.agent_id == user.id
    if order.channel.owner_id == user.id:
        return True
    if getattr(user, "is_team_admin", False):
        return True
    return order.agent_id == user.id


def _simple_order_to_api_dict(o):
    if o.product:
        product_name = o.product.name
    else:
        product_name = getattr(o, "product_name", "Unknown Product")

    agent = o.agent
    created_by_username = agent.username if agent else "—"
    created_by_is_bot = getattr(agent, "is_bot", False) if agent else False
    if created_by_is_bot:
        created_by_display = "AI Agent"
    else:
        created_by_display = (getattr(agent, "agent_role", None) or created_by_username) if agent else "—"

    raw_name = (o.customer_name or "").strip()
    if raw_name:
        display_name = raw_name
    elif o.customer_phone:
        display_name = o.customer_phone
    else:
        display_name = "Direct WhatsApp Customer"

    return {
        "id": o.id,
        "order_id": o.order_id,
        "customer_name": display_name,
        "customer_name_raw": raw_name,
        "customer_email": (getattr(o, "customer_email", None) or ""),
        "total_amount": float(o.price) if o.price else 0.0,
        "price": float(o.price) if o.price else 0.0,
        "customer_phone": o.customer_phone or "",
        "customer_city": o.customer_city or "",
        "is_digital": bool(getattr(o, "is_digital", False)),
        "status": o.status or "",
        "product": product_name,
        "product_id": o.product_id,
        "product_name": o.product_name or product_name,
        "created_by": created_by_username,
        "created_by_display": created_by_display,
        "created_by_is_bot": created_by_is_bot,
        "quantity": round(float(o.quantity)) if o.quantity is not None else 1,
        "created_at": o.created_at.strftime("%Y-%m-%d %H:%M") if o.created_at else None,
        "sheets_export_status": getattr(o, "sheets_export_status", None) or "",
        "sheets_export_error": (getattr(o, "sheets_export_error", None) or "")[:200],
    }


  
def api_orders(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return JsonResponse({"orders": []}, status=401)

    if request.method == "POST":
        return _api_order_create(request, user)

    # 1. تحديد القناة
    target_channel = get_target_channel(user, request.GET.get('channel_id'))
    
    if not target_channel:
        return JsonResponse({"orders": []})

    from discount.models import SimpleOrder
    # Channel owners and admins see ALL orders (including AI-created ones whose agent=bot_user).
    # Assigned team members who don't own the channel see only their own orders.
    is_channel_owner = (getattr(target_channel, "owner_id", None) == user.pk)
    if user.is_superuser or getattr(user, 'is_team_admin', False) or is_channel_owner:
        qs = SimpleOrder.objects.filter(channel=target_channel).order_by("-created_at")
    else:
        qs = SimpleOrder.objects.filter(channel=target_channel, agent=user).order_by("-created_at")

    page_size = max(1, min(50, int(request.GET.get("page_size", 20))))
    paginator = Paginator(qs, page_size)
    page_number = max(1, int(request.GET.get("page", 1)))
    page_obj = paginator.get_page(page_number)

    data = []
    for o in page_obj:
        data.append(_simple_order_to_api_dict(o))

    return JsonResponse({
        "orders": data,
        "status_choices": [
            {"value": v, "label": lbl}
            for v, lbl in SimpleOrder.STATUS_CHOICES
        ],
        "pagination": {
            "page": page_obj.number,
            "page_size": page_size,
            "total_count": paginator.count,
            "total_pages": paginator.num_pages,
            "has_previous": page_obj.has_previous(),
            "has_next": page_obj.has_next(),
        },
    })


@csrf_exempt
def _api_order_create(request, user):
    """Create a manual SimpleOrder from the dashboard orders panel."""
    from decimal import Decimal, InvalidOperation

    from discount.models import Products, SimpleOrder
    from discount.activites import log_activity

    try:
        body = json.loads(request.body.decode("utf-8") if request.body else "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"success": False, "message": "Invalid JSON"}, status=400)

    target_channel = get_target_channel(user, body.get("channel_id") or request.GET.get("channel_id"))
    if not target_channel:
        return JsonResponse({"success": False, "message": "Channel not found"}, status=404)

    is_channel_owner = getattr(target_channel, "owner_id", None) == user.pk
    if not (user.is_superuser or getattr(user, "is_team_admin", False) or is_channel_owner):
        return JsonResponse({"success": False, "message": "Not allowed to create orders for this channel"}, status=403)

    customer_name = str(body.get("customer_name") or "").strip()[:200] or None
    customer_phone = str(body.get("customer_phone") or "").strip()[:20]
    customer_city = str(body.get("customer_city") or "").strip()[:100] or None
    if not customer_phone:
        return JsonResponse({"success": False, "message": "Customer phone is required"}, status=400)

    raw_pid = body.get("product_id")
    if raw_pid in (None, "", 0, "0"):
        return JsonResponse({"success": False, "message": "Product is required"}, status=400)
    try:
        product_id = int(raw_pid)
    except (TypeError, ValueError):
        return JsonResponse({"success": False, "message": "Invalid product"}, status=400)

    product = Products.objects.filter(
        id=product_id,
        admin_id=target_channel.owner_id,
        project=str(target_channel.id),
    ).first()
    if not product:
        return JsonResponse({"success": False, "message": "Product not found in this channel"}, status=400)

    if "quantity" in body:
        try:
            quantity = Decimal(str(body.get("quantity")))
            if quantity <= 0:
                return JsonResponse({"success": False, "message": "Quantity must be greater than 0"}, status=400)
        except (InvalidOperation, TypeError, ValueError):
            return JsonResponse({"success": False, "message": "Invalid quantity"}, status=400)
    else:
        quantity = Decimal("1")

    if "price" in body and body.get("price") not in (None, ""):
        try:
            price = Decimal(str(body.get("price")))
            if price < 0:
                return JsonResponse({"success": False, "message": "Price cannot be negative"}, status=400)
        except (InvalidOperation, TypeError, ValueError):
            return JsonResponse({"success": False, "message": "Invalid price"}, status=400)
    else:
        unit_price = getattr(product, "price", None)
        try:
            price = (Decimal(str(unit_price or 0)) * quantity).quantize(Decimal("0.01"))
        except Exception:
            price = Decimal("0")

    status = str(body.get("status") or "pending").strip()[:20]
    valid_status = {v for v, _ in SimpleOrder.STATUS_CHOICES}
    if status not in valid_status:
        status = "pending"

    is_digital = bool(
        getattr(product, "is_digital", False)
        or (getattr(product, "checkout_mode", None) or "") in ("digital", "direct_sale")
    )
    if is_digital and status == "pending":
        status = "pending_payment"

    order_id = str(uuid.uuid4())[:8]
    while SimpleOrder.objects.filter(order_id=order_id).exists():
        order_id = str(uuid.uuid4())[:8]

    order = SimpleOrder.objects.create(
        product=product,
        agent=user,
        channel=target_channel,
        sku=str(getattr(product, "sku", "") or "")[:100],
        product_name=str(getattr(product, "name", "") or "")[:200],
        customer_name=customer_name or customer_phone,
        customer_phone=customer_phone,
        customer_city=customer_city,
        is_digital=is_digital,
        order_id=order_id,
        status=status,
        created_at=timezone.now(),
        price=price,
        currency=(getattr(product, "currency", None) or "MAD").strip() or "MAD",
        quantity=quantity,
        created_by_ai=False,
        sheets_export_status="",
    )

    log_activity(
        "order_created",
        f"Manual order #{order.pk} created for {customer_phone}",
        request=request,
        related_object=order,
    )

    return JsonResponse({
        "success": True,
        "message": "Order created",
        "order": _simple_order_to_api_dict(order),
    }, status=201)


@login_required
@csrf_exempt
@require_http_methods(["GET", "PATCH", "POST"])
def api_order_update(request, order_id):
    """
    GET  — fetch one order for edit form.
    PATCH/POST JSON — update editable fields on a SimpleOrder.
    """
    from decimal import Decimal, InvalidOperation

    from discount.models import SimpleOrder
    from discount.activites import log_activity

    try:
        order = SimpleOrder.objects.select_related("channel", "agent", "product").get(pk=order_id)
    except SimpleOrder.DoesNotExist:
        return JsonResponse({"success": False, "message": "Order not found"}, status=404)

    if not _user_can_manage_simple_order(request.user, order):
        return JsonResponse({"success": False, "message": "Not allowed to edit this order"}, status=403)

    if request.method == "GET":
        return JsonResponse({
            "success": True,
            "order": _simple_order_to_api_dict(order),
            "status_choices": [
                {"value": v, "label": lbl}
                for v, lbl in SimpleOrder.STATUS_CHOICES
            ],
        })

    try:
        body = json.loads(request.body.decode("utf-8") if request.body else "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"success": False, "message": "Invalid JSON"}, status=400)

    allowed_fields = {
        "customer_name": ("customer_name", 200),
        "customer_phone": ("customer_phone", 20),
        "customer_city": ("customer_city", 100),
        "product_name": ("product_name", 200),
        "status": ("status", 20),
    }
    changes = []
    update_fields = []

    if "product_id" in body:
        from discount.models import Products

        raw_pid = body.get("product_id")
        if raw_pid in (None, "", 0, "0"):
            return JsonResponse({"success": False, "message": "Product is required"}, status=400)
        try:
            product_id = int(raw_pid)
        except (TypeError, ValueError):
            return JsonResponse({"success": False, "message": "Invalid product"}, status=400)
        if not order.channel_id:
            return JsonResponse({"success": False, "message": "Order has no channel"}, status=400)
        product = Products.objects.filter(
            id=product_id,
            admin_id=order.channel.owner_id,
            project=str(order.channel_id),
        ).first()
        if not product:
            return JsonResponse({"success": False, "message": "Product not found in this channel"}, status=400)
        new_product_name = (product.name or "").strip()[:200]
        old_product_id = order.product_id
        old_product_name = order.product_name or ""
        if old_product_id != product.id:
            order.product = product
            update_fields.append("product")
            changes.append(f"product: {old_product_id or '—'} → {product.id}")
            new_sku = str(getattr(product, "sku", "") or "")[:100]
            old_sku = order.sku or ""
            if old_sku != new_sku:
                order.sku = new_sku
                update_fields.append("sku")
                changes.append(f"sku: {old_sku or '—'} → {new_sku or '—'}")
        if old_product_name != new_product_name:
            order.product_name = new_product_name or None
            if "product_name" not in update_fields:
                update_fields.append("product_name")
            changes.append(f"product_name: {old_product_name or '—'} → {new_product_name or '—'}")
        product_id_handled = True
    else:
        product_id_handled = False

    for key, (model_field, max_len) in allowed_fields.items():
        if key == "product_name" and product_id_handled:
            continue
        if key not in body:
            continue
        raw = body.get(key)
        if raw is None:
            continue
        new_val = str(raw).strip()[:max_len]
        old_val = getattr(order, model_field, None) or ""
        if key == "status":
            valid_status = {v for v, _ in SimpleOrder.STATUS_CHOICES}
            if new_val and new_val not in valid_status:
                return JsonResponse({"success": False, "message": f"Invalid status: {new_val}"}, status=400)
        if str(old_val) != new_val:
            setattr(order, model_field, new_val or None)
            update_fields.append(model_field)
            changes.append(f"{key}: {old_val or '—'} → {new_val or '—'}")

    if "quantity" in body:
        try:
            qty = Decimal(str(body.get("quantity")))
            if qty <= 0:
                return JsonResponse({"success": False, "message": "Quantity must be greater than 0"}, status=400)
            if order.quantity != qty:
                changes.append(f"quantity: {order.quantity} → {qty}")
                order.quantity = qty
                update_fields.append("quantity")
        except (InvalidOperation, TypeError, ValueError):
            return JsonResponse({"success": False, "message": "Invalid quantity"}, status=400)

    if "price" in body:
        try:
            price = Decimal(str(body.get("price")))
            if price < 0:
                return JsonResponse({"success": False, "message": "Price cannot be negative"}, status=400)
            if order.price != price:
                changes.append(f"price: {order.price} → {price}")
                order.price = price
                update_fields.append("price")
        except (InvalidOperation, TypeError, ValueError):
            return JsonResponse({"success": False, "message": "Invalid price"}, status=400)

    if not update_fields:
        return JsonResponse({
            "success": True,
            "message": "No changes",
            "order": _simple_order_to_api_dict(order),
        })

    order.save(update_fields=update_fields)
    log_activity(
        "order_updated",
        f"Order #{order.pk} updated: " + "; ".join(changes),
        request=request,
        related_object=order,
    )
    return JsonResponse({
        "success": True,
        "message": "Order updated",
        "order": _simple_order_to_api_dict(order),
    })


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def api_order_sync_google_sheets(request, order_id):
    """
    Manually trigger Google Sheets sync for a SimpleOrder.
    POST /discount/whatssapAPI/api_orders/<order_id>/sync/
    Returns { "success": bool, "message": str }.
    """
    from discount.models import SimpleOrder
    from discount.services.google_sheets_service import sync_order_to_google_sheets

    try:
        order = SimpleOrder.objects.select_related("channel", "agent").get(pk=order_id)
    except SimpleOrder.DoesNotExist:
        return JsonResponse({"success": False, "message": "Order not found"}, status=404)

    user = request.user
    # Access: channel owner, assigned agent, or superuser
    if not user.is_superuser:
        if not order.channel or order.channel.owner_id != user.id:
            if order.agent_id != user.id:
                return JsonResponse({"success": False, "message": "Not allowed to sync this order"}, status=403)

    success, message = sync_order_to_google_sheets(order_id)
    return JsonResponse({"success": success, "message": message or ("Synced" if success else "Sync failed")})


@require_GET
def api_products_list(request):
    """GET ?channel_id= — list products tagged to this WhatsApp channel only."""
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return JsonResponse({"products": [], "error": "Authentication required"}, status=401)
    from discount.models import Products, ProductImage, ProductVideo, UserCheckoutFormCopy, WhatsAppChannel
    raw_cid = request.GET.get("channel_id")
    target_channel = None
    if raw_cid and str(raw_cid) not in ("null", "undefined"):
        try:
            target_channel = WhatsAppChannel.objects.filter(id=raw_cid).first()
        except (TypeError, ValueError):
            target_channel = None
    if not target_channel or not target_channel.owner_id:
        return JsonResponse({"products": []})
    if not target_channel.has_user_permission(user):
        return JsonResponse({"products": [], "error": "Forbidden"}, status=403)
    channel_scope = str(target_channel.id)
    qs = Products.objects.filter(
        admin_id=target_channel.owner_id,
        project=channel_scope,
    ).order_by("-id")
    from discount.whatssapAPI.checkout_capture import form_preview_for_product, merge_preview_with_user_copy
    products = list(qs)
    copies = {}
    if user and products:
        copies = {
            row.product_id: row
            for row in UserCheckoutFormCopy.objects.filter(user=user, product_id__in=[p.id for p in products])
        }
    data = []
    for p in products:
        imgs = ProductImage.objects.filter(product=p).order_by("order", "id")
        vids = ProductVideo.objects.filter(product=p).order_by("order", "id")
        image_urls = [m.image.url for m in imgs if m.image]
        video_urls = [v.video.url for v in vids if v.video]
        try:
            form_preview = form_preview_for_product(p, "ar")
            form_preview = merge_preview_with_user_copy(form_preview, copies.get(p.id))
        except Exception:
            form_preview = None
        data.append({
            "id": p.id,
            "name": p.name or "",
            "sku": p.sku or "",
            "price": str(p.price) if p.price is not None else "",
            "backup_price": str(getattr(p, "backup_price", "") or ""),
            "coupon_code": (getattr(p, "coupon_code", None) or "").strip(),
            "currency": (p.currency or "MAD").strip() or "MAD",
            "description": (p.description or "")[:200],
            "how_to_use": (p.how_to_use or "")[:200] if p.how_to_use else "",
            "offer": p.offer or "",
            "delivery_options": (p.delivery_options or "").strip() or "",
            "category": (getattr(p, "category", None) or "general_retail").strip() or "general_retail",
            "seller_custom_persona": (getattr(p, "seller_custom_persona", None) or "").strip() or "",
            "testimonial_url": p.testimonial.url if p.testimonial else None,
            "images": image_urls,
            "videos": video_urls,
            "is_digital": bool(
                getattr(p, "is_digital", False)
                or (getattr(p, "checkout_mode", None) or "") in ("digital", "direct_sale")
            ),
            "checkout_mode": (getattr(p, "checkout_mode", None) or "standard_cod").strip() or "standard_cod",
            "form_preview": form_preview,
        })
    return JsonResponse({"products": data})


# Human-readable labels for product categories (for UI). Must match Products.PRODUCT_CATEGORY_CHOICES / classifier.
PRODUCT_CATEGORY_LABELS = {
    "beauty_and_skincare": "Beauty & Skincare",
    "electronics_and_gadgets": "Electronics & Gadgets",
    "fragrances": "Fragrances",
    "fashion_and_apparel": "Fashion & Apparel",
    "health_and_supplements": "Health & Supplements",
    "home_and_kitchen": "Home & Kitchen",
    "general_retail": "General",
    "beauty": "Beauty",
    "electronics": "Electronics",
    "general": "General",
}
ALLOWED_PRODUCT_CATEGORIES = frozenset(PRODUCT_CATEGORY_LABELS.keys())


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def api_products_classify(request):
    """
    Classify product category via AI when name/description has minimal signal.
    POST JSON: {"title": "...", "description": "..."}.
    Returns {"category": "...", "label": "..."}.
    Skips the LLM when input is too sparse; returns general_retail.
    """
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=401)
    try:
        body = json.loads(request.body) if request.body else {}
    except (ValueError, TypeError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    title = (body.get("title") or "").strip() or "Product"
    description = (body.get("description") or "").strip()
    from ai_assistant.product_classifier import classify_product, should_classify_product
    if not should_classify_product(title, description):
        return JsonResponse({
            "category": "general_retail",
            "label": PRODUCT_CATEGORY_LABELS.get("general_retail", "General"),
        })
    try:
        category = classify_product(title, description)
    except Exception as e:
        logger.warning("api_products_classify: %s", e)
        category = "general_retail"
    label = PRODUCT_CATEGORY_LABELS.get(category, "General")
    return JsonResponse({"category": category, "label": label})


# ══════════════════════════════════════════════════════════════════════════
# Dynamic Digital Stock — bulk-paste parsing and FIFO bulk creation
# ══════════════════════════════════════════════════════════════════════════
#
# Valid `stock_format` values, matching the radio toggle in the product form
# (see `templates/whatssap/whatssap.html`):
#
#   'single' — one opaque value per non-empty line (license key, code).
#   'combo'  — every non-empty line MUST contain exactly ONE ':' (email:password).
#   'iptv'   — one opaque Xtream host:user:pass or M3U URL per line (no colon rules).
_VALID_STOCK_FORMATS = ('single', 'combo', 'iptv')


def _parse_bulk_stock_input(raw_text, stock_format):
    """
    Parse the bulk-paste textarea into a list of cleaned credential lines.

    Returns a tuple `(lines, error_message)`:
      - lines: list[str] of validated, ready-to-encrypt rows. Empty when
        the input was blank (a legitimate "no new stock" case).
      - error_message: human-readable Validation Error pointing at the
        exact 1-based line number that broke the rule, or None on success.

    The function is pure / side-effect free so it can be called from both
    `api_products_create` and `api_products_update` (and unit-tested).
    """
    if stock_format not in _VALID_STOCK_FORMATS:
        return [], (
            'Validation Error: Unknown stock_format "%s" '
            '(expected one of: %s).' % (stock_format, ', '.join(_VALID_STOCK_FORMATS))
        )

    text = (raw_text or '').replace('\r\n', '\n').replace('\r', '\n')
    if not text.strip():
        return [], None  # no new stock — not an error

    cleaned = []
    # Enumerate against the ORIGINAL line numbers (1-based) so the error
    # message matches what the seller sees in the textarea. Blank lines
    # are silently ignored per spec.
    for lineno, raw_line in enumerate(text.split('\n'), start=1):
        line = raw_line.strip()
        if not line:
            continue
        if stock_format == 'combo':
            colon_count = line.count(':')
            if colon_count == 0:
                return [], (
                    "Validation Error: Line %d is missing the ':' separator. "
                    "Combo format expects 'email:password' on every line." % lineno
                )
            if colon_count > 1:
                # Strict per spec: "exactly one colon". This catches
                # passwords that themselves contain ':' (e.g. "pa:ss")
                # so the seller can re-escape before saving.
                return [], (
                    "Validation Error: Line %d contains %d ':' separators (expected exactly 1). "
                    "Combo format expects 'email:password' with no extra colons." % (lineno, colon_count)
                )
            email_part, password_part = line.split(':', 1)
            if not email_part.strip() or not password_part.strip():
                return [], (
                    "Validation Error: Line %d has an empty email or password "
                    "around the ':' separator." % lineno
                )
        cleaned.append(line)
    return cleaned, None


def _bulk_create_digital_stock(product, lines):
    """
    Encrypt and bulk-insert `DigitalAssetStock` rows for `product`.
    No-op when `lines` is empty.

    We can't use `bulk_create` here because the Fernet encryption hook
    runs in Python (`set_asset_content`) per-row. Wrapping the loop in
    `transaction.atomic` keeps the inserts all-or-nothing so a mid-loop
    failure doesn't leave half-loaded stock on the product.
    """
    if not lines:
        return 0
    from discount.models import DigitalAssetStock
    created = 0
    with transaction.atomic():
        for raw in lines:
            row = DigitalAssetStock(product=product, is_sold=False)
            row.set_asset_content(raw)
            row.save()
            created += 1
    return created


def _resolve_product_sku(raw_sku, *, exclude_product_id=None, auto_if_empty=False):
    """Validate optional SKU from form; auto-generate when empty and auto_if_empty is True."""
    from discount.models import Products

    sku_raw = (raw_sku or "").strip()
    if not sku_raw:
        if not auto_if_empty:
            return None, None
        sku = f"PROD-{uuid.uuid4().hex[:10].upper()}"
        while Products.objects.filter(sku=sku).exists():
            sku = f"PROD-{uuid.uuid4().hex[:10].upper()}"
        return sku, None
    if len(sku_raw) > 100:
        return None, "SKU must be 100 characters or less."
    qs = Products.objects.filter(sku=sku_raw)
    if exclude_product_id:
        qs = qs.exclude(id=exclude_product_id)
    if qs.exists():
        return None, "This SKU is already used by another product."
    return sku_raw, None


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def api_products_create(request):
    """
    Create product. Required: name, price, description, at least one image.
    Optional: how_to_use, offer, testimonial (file), category (from AI or manual).
    POST multipart: channel_id, name, price, description, how_to_use, offer, testimonial, images (multiple files).

    Digital extras (when `is_digital=true`):
      - `stock_format` ('single' | 'combo')
      - `bulk_stock_input` (textarea: one credential per non-empty line)
    """
    from decimal import Decimal, InvalidOperation
    from discount.models import Products, ProductImage, ProductVideo

    user = request.user
    channel = get_target_channel(user, request.POST.get("channel_id") or request.GET.get("channel_id"))
    if not channel or not channel.owner_id:
        return JsonResponse({"success": False, "error": "Channel not found or permission denied"}, status=403)

    name = (request.POST.get("name") or "").strip()
    price_raw = (request.POST.get("price") or "").strip()
    currency = (request.POST.get("currency") or "").strip() or "MAD"
    if len(currency) > 10:
        currency = currency[:10]
    description = (request.POST.get("description") or "").strip()
    how_to_use = (request.POST.get("how_to_use") or "").strip() or None
    offer = (request.POST.get("offer") or "").strip() or None
    backup_price_raw = (request.POST.get("backup_price") or "").strip()
    coupon_code = (request.POST.get("coupon_code") or "").strip() or None
    delivery_options = (request.POST.get("delivery_options") or "").strip() or None
    if delivery_options and len(delivery_options) > 500:
        delivery_options = delivery_options[:500]
    return_policy_val = (request.POST.get("return_policy") or "").strip() or None

    errors = []
    if not name:
        errors.append("Product name is required.")
    if not price_raw:
        errors.append("Price is required.")
    else:
        try:
            price_val = Decimal(price_raw)
            if price_val < 0:
                errors.append("Price must be a positive number.")
        except (InvalidOperation, ValueError):
            errors.append("Price must be a valid number.")
    if not description:
        errors.append("Description is required.")
    backup_price_val = None
    if backup_price_raw:
        try:
            backup_price_val = Decimal(backup_price_raw)
            if backup_price_val < 0:
                errors.append("Backup price must be a positive number.")
        except (InvalidOperation, ValueError):
            errors.append("Backup price must be a valid number.")
    if coupon_code and len(coupon_code) > 64:
        coupon_code = coupon_code[:64]

    checkout_mode_param = (request.POST.get("checkout_mode") or "").strip() or "standard_cod"
    if checkout_mode_param not in ("quick_lead", "standard_cod", "strict_cod", "digital", "direct_sale"):
        checkout_mode_param = "standard_cod"

    is_digital_raw = (request.POST.get("is_digital") or "false").strip().lower()
    is_digital_val = is_digital_raw in ("true", "1", "yes")
    digital_url_val = (request.POST.get("digital_url") or "").strip() or None
    fulfillment_message_val = (request.POST.get("fulfillment_message") or "").strip() or None
    collect_info_raw = (request.POST.get("collect_customer_info") or "true").strip().lower()
    collect_customer_info_val = collect_info_raw not in ("false", "0", "no")

    # ── Dynamic digital stock (bulk-paste) ───────────────────────────────
    stock_format_val = (request.POST.get("stock_format") or "single").strip().lower()
    if stock_format_val not in _VALID_STOCK_FORMATS:
        stock_format_val = "single"
    bulk_stock_raw = request.POST.get("bulk_stock_input") or ""
    parsed_stock_lines, parsed_stock_error = _parse_bulk_stock_input(
        bulk_stock_raw, stock_format_val
    )
    if parsed_stock_error:
        # Halt the save and surface the exact line number to the seller.
        # The frontend renders this verbatim in the form's error banner.
        return JsonResponse(
            {"success": False, "error": parsed_stock_error, "errors": [parsed_stock_error]},
            status=400,
        )

    if is_digital_val and checkout_mode_param not in ("digital", "direct_sale"):
        checkout_mode_param = "digital"

    media_files = request.FILES.getlist("images") or request.FILES.getlist("image") or []
    image_urls_raw = request.POST.get("image_urls", "").strip()
    image_urls = []
    if image_urls_raw:
        try:
            image_urls = json.loads(image_urls_raw)
            if not isinstance(image_urls, list):
                image_urls = []
            image_urls = [u for u in image_urls if u and isinstance(u, str) and u.startswith("http")][:10]
        except (ValueError, TypeError):
            image_urls = []
    digital_file_upload = request.FILES.get("digital_file")
    if not media_files and not image_urls and not is_digital_val:
        errors.append("At least one product photo or video is required.")

    # A digital product is valid if ANY of the three fulfillment sources
    # is provided: static download URL, static file upload, OR dynamic
    # bulk stock. Without one of these the AI has nothing to deliver.
    if is_digital_val and not digital_url_val and not digital_file_upload and not parsed_stock_lines:
        errors.append(
            "Digital product requires a download URL, a file upload, "
            "OR at least one bulk stock line."
        )

    digital_product_type_val = None
    legal_consent_iptv_val = False
    if is_digital_val:
        from discount.services.digital_product_validation import parse_digital_product_fields
        digital_product_type_val, legal_consent_iptv_val, digital_type_err = parse_digital_product_fields(
            request.POST, is_digital=True
        )
        if digital_type_err:
            errors.append(digital_type_err)

    if errors:
        return JsonResponse({"success": False, "error": " ".join(errors), "errors": errors}, status=400)

    try:
        price_val = Decimal(price_raw)
    except (InvalidOperation, ValueError):
        return JsonResponse({"success": False, "error": "Invalid price"}, status=400)

    sku, sku_error = _resolve_product_sku(
        request.POST.get("sku"),
        auto_if_empty=True,
    )
    if sku_error:
        return JsonResponse({"success": False, "error": sku_error, "errors": [sku_error]}, status=400)

    seller_custom_persona = (request.POST.get("seller_custom_persona") or "").strip() or None
    if seller_custom_persona and len(seller_custom_persona) > 2000:
        seller_custom_persona = seller_custom_persona[:2000]

    from discount.services.product_search import parse_aliases
    aliases_val = parse_aliases(request.POST.get("aliases"))

    category_param = (request.POST.get("category") or "").strip().lower()
    if category_param not in ALLOWED_PRODUCT_CATEGORIES:
        category_param = None

    product = Products.objects.create(
        admin_id=channel.owner_id,
        project=str(channel.id),
        name=name,
        sku=sku,
        price=price_val,
        currency=currency,
        description=description,
        how_to_use=how_to_use or None,
        offer=offer or None,
        backup_price=backup_price_val,
        coupon_code=(coupon_code.upper() if coupon_code else None),
        delivery_options=delivery_options,
        return_policy=return_policy_val,
        seller_custom_persona=seller_custom_persona,
        stock=0,
        category=category_param or "general_retail",
        checkout_mode=checkout_mode_param,
        is_digital=is_digital_val,
        digital_url=digital_url_val,
        fulfillment_message=fulfillment_message_val,
        collect_customer_info=collect_customer_info_val,
        stock_format=stock_format_val,
        digital_product_type=digital_product_type_val if is_digital_val else None,
        legal_consent_iptv=legal_consent_iptv_val,
        aliases=aliases_val,
    )
    if digital_file_upload:
        product.digital_file = digital_file_upload
        product.save(update_fields=["digital_file"])

    # Bulk-load the seller's pasted credentials (only for digital products).
    # The raw text never persists on `Products` itself — every row is
    # Fernet-encrypted on `DigitalAssetStock.asset_content` so the digital
    # inventory is consumed (and exhausted) atomically on each sale.
    if is_digital_val and parsed_stock_lines:
        _bulk_create_digital_stock(product, parsed_stock_lines)

    # AI product classification — physical goods only; digital products use the Digital persona router.
    if not category_param and not is_digital_val:
        from ai_assistant.product_classifier import classify_product, should_classify_product
        if should_classify_product(name, description):
            try:
                category = classify_product(product.name, product.description)
                product.category = category
                product.save(update_fields=["category"])
            except Exception as e:
                logger.warning("Product classification failed for product_id=%s: %s", product.id, e)

    testimonial_file = request.FILES.get("testimonial")
    if testimonial_file:
        product.testimonial = testimonial_file
        product.save(update_fields=["testimonial"])

    img_order = 0
    vid_order = 0
    if media_files:
        for f in media_files:
            content_type = (getattr(f, "content_type") or "").lower()
            if content_type.startswith("video/"):
                ProductVideo.objects.create(product=product, video=f, order=vid_order)
                vid_order += 1
            else:
                ProductImage.objects.create(product=product, image=f, order=img_order)
                img_order += 1
    elif image_urls:
        for i, img_url in enumerate(image_urls):
            try:
                r = requests.get(img_url, timeout=10, headers={"User-Agent": "Mozilla/5.0 (compatible; ProductBot/1.0)"})
                r.raise_for_status()
                content_type = r.headers.get("Content-Type", "").split(";")[0].strip()
                if "image" not in content_type:
                    continue
                fname = (img_url.split("/")[-1] or "image").split("?")[0] or "image.jpg"
                if "." not in fname:
                    fname += ".jpg"
                fname = f"{uuid.uuid4().hex}_{i}.jpg"
                ProductImage.objects.create(product=product, image=ContentFile(r.content, name=fname), order=i)
            except Exception as e:
                logger.warning("Failed to fetch product image %s: %s", img_url[:80], e)

    return JsonResponse({
        "success": True,
        "product_id": product.id,
        "message": "Product created successfully.",
    })


def _serialize_digital_stock_unsold(product, limit=200):
    """
    Decrypt unsold FIFO rows for the product-edit form (owner-only detail
  endpoint). Returns [{id, line, content}, …] — never used in list APIs.
    """
    if not product or not bool(getattr(product, 'is_digital', False)):
        return []
    try:
        from discount.models import DigitalAssetStock
        rows = (
            DigitalAssetStock.objects
            .filter(product=product, is_sold=False)
            .order_by('id')[:limit]
        )
        out = []
        for idx, row in enumerate(rows, start=1):
            content = row.get_asset_content()
            if not content:
                continue
            out.append({
                'id': row.id,
                'line': idx,
                'content': content,
            })
        return out
    except Exception as exc:
        logging.getLogger(__name__).warning(
            'digital_stock_unsold serialize failed product_id=%s: %s',
            getattr(product, 'id', None), exc,
        )
        return []


@login_required
@require_GET
def api_products_detail(request, product_id):
    """GET single product full details for preview/edit. User must own channel that owns the product."""
    from discount.models import Products, ProductImage, ProductVideo
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=401)
    product = get_object_or_404(Products, id=product_id)
    channel = get_target_channel(user, request.GET.get("channel_id"))
    if (
        not channel
        or not channel.owner_id
        or product.admin_id != channel.owner_id
        or (str(getattr(product, "project", "") or "") != str(channel.id))
    ):
        return JsonResponse({"error": "Product not found or access denied"}, status=404)
    imgs = ProductImage.objects.filter(product=product).order_by("order", "id")
    vids = ProductVideo.objects.filter(product=product).order_by("order", "id")
    image_urls = [m.image.url for m in imgs if m.image]
    video_urls = [v.video.url for v in vids if v.video]
    is_digital = bool(getattr(product, "is_digital", False))
    checkout_mode = (getattr(product, "checkout_mode", None) or "standard_cod").strip() or "standard_cod"
    # Treat checkout_mode as digital even if is_digital was not persisted (legacy rows).
    if checkout_mode in ("digital", "direct_sale"):
        is_digital = True
    digital_file_name = ""
    has_digital_file = False
    digital_file_url = None
    if getattr(product, "digital_file", None) and product.digital_file.name:
        has_digital_file = True
        digital_file_name = product.digital_file.name.split("/")[-1]
        try:
            digital_file_url = product.digital_file.url
        except Exception:
            digital_file_url = None
    stock_available = 0
    stock_sold = 0
    if is_digital:
        try:
            stock_available = product.digital_stock.filter(is_sold=False).count()
            stock_sold = product.digital_stock.filter(is_sold=True).count()
        except Exception:
            pass
    return JsonResponse({
        "id": product.id,
        "name": product.name or "",
        "sku": product.sku or "",
        "price": str(product.price) if product.price is not None else "",
        "backup_price": str(getattr(product, "backup_price", "") or ""),
        "coupon_code": (getattr(product, "coupon_code", None) or "").strip(),
        "currency": (product.currency or "MAD").strip() or "MAD",
        "description": product.description or "",
        "how_to_use": product.how_to_use or "",
        "offer": product.offer or "",
        "delivery_options": (product.delivery_options or "").strip() or "",
        "return_policy": (getattr(product, "return_policy", None) or "").strip(),
        "category": (getattr(product, "category", None) or "general_retail").strip() or "general_retail",
        "seller_custom_persona": (getattr(product, "seller_custom_persona", None) or "").strip() or "",
        "checkout_mode": checkout_mode,
        "testimonial_url": product.testimonial.url if product.testimonial else None,
        "images": image_urls,
        "videos": video_urls,
        "is_digital": is_digital,
        "digital_url": (getattr(product, "digital_url", None) or "").strip(),
        "has_digital_file": has_digital_file,
        "digital_file_name": digital_file_name,
        "digital_file_url": digital_file_url,
        "fulfillment_message": (getattr(product, "fulfillment_message", None) or "").strip(),
        "collect_customer_info": bool(getattr(product, "collect_customer_info", True)),
        "stock_format": (getattr(product, "stock_format", None) or "single"),
        "digital_stock_available": stock_available,
        "digital_stock_sold": stock_sold,
        # Owner-only: unsold credentials for the edit form (detail endpoint is gated).
        "digital_stock_unsold": _serialize_digital_stock_unsold(product),
        "digital_product_type": (getattr(product, "digital_product_type", None) or "").strip() or None,
        "legal_consent_iptv": bool(getattr(product, "legal_consent_iptv", False)),
        "aliases": list(getattr(product, "aliases", None) or []),
    })


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def api_products_update(request, product_id):
    """Update product. Same fields as create; images optional (if provided, replace existing)."""
    from decimal import Decimal, InvalidOperation
    from discount.models import Products, ProductImage, ProductVideo
    user = request.user
    product = get_object_or_404(Products, id=product_id)
    channel = get_target_channel(user, request.POST.get("channel_id") or request.GET.get("channel_id"))
    if (
        not channel
        or not channel.owner_id
        or product.admin_id != channel.owner_id
        or (str(getattr(product, "project", "") or "") != str(channel.id))
    ):
        return JsonResponse({"success": False, "error": "Product not found or permission denied"}, status=403)
    name = (request.POST.get("name") or "").strip()
    price_raw = (request.POST.get("price") or "").strip()
    currency = (request.POST.get("currency") or "").strip() or "MAD"
    if len(currency) > 10:
        currency = currency[:10]
    description = (request.POST.get("description") or "").strip()
    how_to_use = (request.POST.get("how_to_use") or "").strip() or None
    offer = (request.POST.get("offer") or "").strip() or None
    backup_price_raw = (request.POST.get("backup_price") or "").strip()
    coupon_code = (request.POST.get("coupon_code") or "").strip() or None
    delivery_options = (request.POST.get("delivery_options") or "").strip() or None
    if delivery_options and len(delivery_options) > 500:
        delivery_options = delivery_options[:500]
    return_policy_val = (request.POST.get("return_policy") or "").strip() or None
    seller_custom_persona = (request.POST.get("seller_custom_persona") or "").strip() or None
    if seller_custom_persona and len(seller_custom_persona) > 2000:
        seller_custom_persona = seller_custom_persona[:2000]
    category_raw = (request.POST.get("category") or "").strip().lower()
    if category_raw not in ALLOWED_PRODUCT_CATEGORIES:
        category_raw = getattr(product, "category", None) or "general_retail"
    checkout_mode_raw = (request.POST.get("checkout_mode") or "").strip() or "standard_cod"
    if checkout_mode_raw not in ("quick_lead", "standard_cod", "strict_cod", "digital", "direct_sale"):
        checkout_mode_raw = getattr(product, "checkout_mode", None) or "standard_cod"
    is_digital_raw = (request.POST.get("is_digital") or "false").strip().lower()
    is_digital_val = is_digital_raw in ("true", "1", "yes")
    digital_url_val = (request.POST.get("digital_url") or "").strip() or None
    fulfillment_message_val = (request.POST.get("fulfillment_message") or "").strip() or None
    collect_info_raw = (request.POST.get("collect_customer_info") or "true").strip().lower()
    collect_customer_info_val = collect_info_raw not in ("false", "0", "no")
    if is_digital_val and checkout_mode_raw not in ("digital", "direct_sale"):
        checkout_mode_raw = "digital"

    # ── Dynamic digital stock (bulk-paste, APPEND on update) ─────────────
    # On UPDATE we only append rows; we never delete unsold rows because
    # they may have been pasted by the seller across multiple edit
    # sessions, and silently discarding them would lose inventory.
    stock_format_val = (request.POST.get("stock_format") or product.stock_format or "single").strip().lower()
    if stock_format_val not in _VALID_STOCK_FORMATS:
        stock_format_val = product.stock_format or "single"
    bulk_stock_raw = request.POST.get("bulk_stock_input") or ""
    parsed_stock_lines, parsed_stock_error = _parse_bulk_stock_input(
        bulk_stock_raw, stock_format_val
    )
    if parsed_stock_error:
        return JsonResponse(
            {"success": False, "error": parsed_stock_error, "errors": [parsed_stock_error]},
            status=400,
        )

    errors = []
    if not name:
        errors.append("Product name is required.")
    if not price_raw:
        errors.append("Price is required.")
    else:
        try:
            pv = Decimal(price_raw)
            if pv < 0:
                errors.append("Price must be a positive number.")
        except (InvalidOperation, ValueError):
            errors.append("Price must be a valid number.")
    if not description:
        errors.append("Description is required.")
    backup_price_val = None
    if backup_price_raw:
        try:
            backup_price_val = Decimal(backup_price_raw)
            if backup_price_val < 0:
                errors.append("Backup price must be a positive number.")
        except (InvalidOperation, ValueError):
            errors.append("Backup price must be a valid number.")
    if coupon_code and len(coupon_code) > 64:
        coupon_code = coupon_code[:64]

    from discount.services.product_search import parse_aliases
    aliases_val = parse_aliases(request.POST.get("aliases"))

    digital_product_type_val = None
    legal_consent_iptv_val = False
    if is_digital_val:
        from discount.services.digital_product_validation import parse_digital_product_fields
        digital_product_type_val, legal_consent_iptv_val, digital_type_err = parse_digital_product_fields(
            request.POST, is_digital=True
        )
        if digital_type_err:
            errors.append(digital_type_err)

    if errors:
        return JsonResponse({"success": False, "error": " ".join(errors), "errors": errors}, status=400)
    sku, sku_error = _resolve_product_sku(
        request.POST.get("sku"),
        exclude_product_id=product.id,
        auto_if_empty=False,
    )
    if sku_error:
        return JsonResponse({"success": False, "error": sku_error, "errors": [sku_error]}, status=400)
    try:
        price_val = Decimal(price_raw)
    except (InvalidOperation, ValueError):
        return JsonResponse({"success": False, "error": "Invalid price"}, status=400)
    media_files = request.FILES.getlist("images") or request.FILES.getlist("image") or []
    digital_file_upload = request.FILES.get("digital_file")
    if (not is_digital_val and not media_files
            and not ProductImage.objects.filter(product=product).exists()
            and not ProductVideo.objects.filter(product=product).exists()):
        errors.append("At least one product photo or video is required.")
        return JsonResponse({"success": False, "error": " ".join(errors), "errors": errors}, status=400)
    product.name = name
    if sku is not None:
        product.sku = sku
    product.price = price_val
    product.currency = currency
    product.description = description
    product.how_to_use = how_to_use or None
    product.offer = offer or None
    product.backup_price = backup_price_val
    product.coupon_code = (coupon_code.upper() if coupon_code else None)
    product.delivery_options = delivery_options
    product.return_policy = return_policy_val
    product.category = category_raw or "general_retail"
    product.seller_custom_persona = seller_custom_persona
    product.checkout_mode = checkout_mode_raw or "standard_cod"
    product.is_digital = is_digital_val
    product.digital_url = digital_url_val
    product.fulfillment_message = fulfillment_message_val
    product.collect_customer_info = collect_customer_info_val
    product.stock_format = stock_format_val
    product.digital_product_type = digital_product_type_val if is_digital_val else None
    product.legal_consent_iptv = legal_consent_iptv_val
    product.aliases = aliases_val
    product.save(update_fields=["name", "sku", "price", "currency", "description", "how_to_use", "offer", "backup_price",
                                "coupon_code", "delivery_options", "return_policy", "category", "seller_custom_persona",
                                "checkout_mode", "is_digital", "digital_url", "fulfillment_message",
                                "collect_customer_info", "stock_format", "digital_product_type", "legal_consent_iptv",
                                "aliases"])
    if digital_file_upload:
        product.digital_file = digital_file_upload
        product.save(update_fields=["digital_file"])

    # Append the new bulk-pasted rows to the existing FIFO inventory.
    # Existing unsold rows are PRESERVED — sellers can top-up across
    # multiple edit sessions without losing what they already pasted.
    if is_digital_val and parsed_stock_lines:
        _bulk_create_digital_stock(product, parsed_stock_lines)
    testimonial_file = request.FILES.get("testimonial")
    if testimonial_file:
        product.testimonial = testimonial_file
        product.save(update_fields=["testimonial"])
    if media_files:
        ProductImage.objects.filter(product=product).delete()
        ProductVideo.objects.filter(product=product).delete()
        img_order = 0
        vid_order = 0
        for f in media_files:
            content_type = (getattr(f, "content_type") or "").lower()
            if content_type.startswith("video/"):
                ProductVideo.objects.create(product=product, video=f, order=vid_order)
                vid_order += 1
            else:
                ProductImage.objects.create(product=product, image=f, order=img_order)
                img_order += 1
    return JsonResponse({"success": True, "product_id": product.id, "message": "Product updated successfully."})


def _scrape_product_page(url):
    """
    Fetch URL and extract product-like data (title, description, price, images).
    Returns dict with keys: title, description, price, currency, image_urls, raw_text.
    Returns None if request fails or page is empty.
    """
    from urllib.parse import urljoin, urlparse
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return None
    if not url or not url.strip().startswith(("http://", "https://")):
        return None
    try:
        resp = requests.get(
            url.strip(),
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; rv:91.0) Gecko/20100101 Firefox/91.0"},
            allow_redirects=True,
        )
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
        html = resp.text
    except Exception as e:
        logger.warning("Scrape request failed for %s: %s", url[:80], e)
        return None
    if not html or len(html) < 200:
        return None
    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception:
        return None
    base_url = resp.url
    title = None
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        title = (og_title["content"] or "").strip()
    if not title and soup.title and soup.title.string:
        title = (soup.title.string or "").strip()
    if not title:
        h1 = soup.find("h1")
        if h1 and h1.get_text():
            title = h1.get_text(strip=True)[:200]

    description = None
    og_desc = soup.find("meta", property="og:description")
    if og_desc and og_desc.get("content"):
        description = (og_desc["content"] or "").strip()
    if not description:
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc and meta_desc.get("content"):
            description = (meta_desc["content"] or "").strip()
    if not description:
        for p in soup.find_all("p", limit=5):
            t = (p.get_text() or "").strip()
            if len(t) > 80:
                description = t[:1500]
                break

    price = None
    currency = None
    import re
    price_pattern = re.compile(r"(\d+[\d.,\s]*(?:\.\d{2})?)\s*([A-Z]{3}|MAD|USD|EUR|DH|د\.م\.|د\.م)")
    for elem in soup.find_all(string=price_pattern):
        m = price_pattern.search(elem)
        if m:
            price = m.group(1).replace(" ", "").replace(",", ".").strip()
            currency = (m.group(2) or "").strip().upper()
            if currency in ("DH", "د.م.", "د.م"):
                currency = "MAD"
            break
    if not price:
        for attr in ("data-price", "data-product-price", "content"):
            el = soup.find(attrs={attr: True})
            if el and el.get(attr):
                try:
                    price = str(float(re.sub(r"[^\d.]", "", el[attr]) or 0))
                    break
                except ValueError:
                    pass
    if not currency:
        currency = "MAD"

    image_urls = []
    og_image = soup.find("meta", property="og:image")
    if og_image and og_image.get("content"):
        u = urljoin(base_url, (og_image["content"] or "").strip())
        if u.startswith("http"):
            image_urls.append(u)
    for img in soup.find_all("img", src=True, limit=15):
        src = (img.get("src") or "").strip()
        if not src or "logo" in src.lower() or "icon" in src.lower() or "pixel" in src.lower():
            continue
        u = urljoin(base_url, src)
        if u.startswith("http") and u not in image_urls:
            image_urls.append(u)

    raw_text = (title or "") + "\n" + (description or "")
    if not title and not description and not price and not image_urls:
        return None
    return {
        "title": title or "",
        "description": description or "",
        "price": price,
        "currency": currency or "MAD",
        "image_urls": image_urls[:10],
        "raw_text": raw_text[:8000],
    }


def _ai_extract_product(scraped_data):
    """Send scraped data to OpenAI and return structured product dict (name, description, price, currency, image_urls, how_to_use)."""
    try:
        from ai_assistant.services import get_api_key, OPENAI_API_URL
    except ImportError:
        return None
    api_key = get_api_key()
    if not api_key:
        return None
    text = (
        "Page title: " + (scraped_data.get("title") or "—") + "\n"
        "Description: " + (scraped_data.get("description") or "—") + "\n"
        "Price: " + (str(scraped_data.get("price")) if scraped_data.get("price") else "—") + "\n"
        "Currency: " + (scraped_data.get("currency") or "—") + "\n"
        "Image URLs: " + ", ".join(scraped_data.get("image_urls") or [])
    )
    system = (
        "You are a product data extractor. Given scraped content from a product page, return a single JSON object with exactly these keys: "
        '"name" (string, product title), "description" (string, product description), "price" (string or null, numeric price), '
        '"currency" (string, e.g. MAD, USD), "image_urls" (array of full image URLs from the list provided, keep up to 10), '
        '"how_to_use" (string or null). Use only information from the content. If price is missing use null. Return only valid JSON, no markdown."'
    )
    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": text},
        ],
        "max_tokens": 800,
        "temperature": 0.2,
    }
    try:
        r = requests.post(
            OPENAI_API_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=30,
        )
        if r.status_code != 200:
            return None
        data = r.json()
        content = (data.get("choices", [{}])[0].get("message", {}).get("content") or "").strip()
        if not content:
            return None
        content = content.replace("```json", "").replace("```", "").strip()
        return json.loads(content)
    except Exception as e:
        logger.warning("AI product extract failed: %s", e)
        return None


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def api_products_extract_from_link(request):
    """
    POST JSON or form: url = product page URL.
    Scrapes the page; if nothing found returns error. Else sends to AI and returns structured product.
    """
    try:
        if request.content_type and "application/json" in request.content_type:
            body = json.loads(request.body.decode("utf-8") or "{}")
            url = (body.get("url") or "").strip()
        else:
            url = (request.POST.get("url") or "").strip()
    except Exception:
        url = (request.POST.get("url") or "").strip()
    if not url:
        return JsonResponse({"success": False, "error": "Please provide a product link (url)."}, status=400)
    scraped = _scrape_product_page(url)
    if not scraped:
        return JsonResponse({
            "success": False,
            "error": "We did not find anything in this link. Make sure the URL is a valid product page and try again.",
        }, status=200)
    product_data = _ai_extract_product(scraped)
    if not product_data:
        return JsonResponse({
            "success": False,
            "error": "We could not extract product details. Please try again or create the product manually.",
        }, status=200)
    name = (product_data.get("name") or "").strip() or scraped.get("title") or "Product"
    description = (product_data.get("description") or "").strip() or scraped.get("description") or ""
    price = product_data.get("price")
    if price is not None:
        price = str(price).strip().replace(",", ".")
    else:
        price = scraped.get("price")
        if price is not None:
            price = str(price).strip().replace(",", ".")
    if not price:
        price = ""
    currency = (product_data.get("currency") or "").strip() or scraped.get("currency") or "MAD"
    if len(currency) > 10:
        currency = currency[:10]
    image_urls = product_data.get("image_urls") or scraped.get("image_urls") or []
    if not isinstance(image_urls, list):
        image_urls = []
    image_urls = [u for u in image_urls if u and isinstance(u, str) and u.startswith("http")][:10]
    how_to_use = (product_data.get("how_to_use") or "").strip() or None
    return JsonResponse({
        "success": True,
        "product": {
            "name": name,
            "description": description,
            "price": price,
            "currency": currency,
            "image_urls": image_urls,
            "how_to_use": how_to_use or "",
        },
    })


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
@check_plan_limit("max_channels")
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
        log_activity('wa_channel_created', f"Channel created: {new_channel.name} ({new_channel.phone_number})", request=request, related_object=new_channel)
        return JsonResponse({'success': True, 'id': new_channel.id})

    except IntegrityError as e:
        err_lower = str(e).lower()
        if "phone_number" in err_lower or "whatsappchannel" in err_lower:
            return JsonResponse(
                {
                    "success": False,
                    "error": "This WhatsApp number is already connected. Remove the existing channel or use a different number.",
                    "error_code": "duplicate_phone",
                },
                status=409,
            )
        logger.exception("create_channel_api integrity error")
        return JsonResponse(
            {"success": False, "error": "Could not save this channel.", "error_code": "integrity"},
            status=409,
        )
    except Exception as e:
        logger.exception("create_channel_api failed")
        return JsonResponse({"success": False, "error": "Could not create channel.", "error_code": "unknown"}, status=400)












import json
import requests
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
 
import time

def register_phone_number_with_retry(phone_id, access_token, pin_code, max_retries=3):
    """
    محاولة تسجيل الرقم مع إعادة المحاولة في حالة تأخر تفعيل الحساب من طرف Meta
    """
    url = f"https://graph.facebook.com/v24.0/{phone_id}/register"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "pin": pin_code
    }

    for attempt in range(max_retries):
        try:
            print(f"🔄 محاولة التسجيل رقم {attempt + 1}...")
            response = requests.post(url, headers=headers, json=payload)
            data = response.json()

            if response.status_code == 200 and data.get('success'):
                return True, "تم التسجيل بنجاح"
            
            # تحليل الخطأ
            error_code = data.get('error', {}).get('code')
            error_msg = data.get('error', {}).get('message')
            
            # إذا كان الخطأ هو الخطأ الشهير (Pending/Invalid Linking)
            if error_code == 100 or "Pending" in str(data):
                print(f"⚠️ الحساب غير جاهز بعد، انتظار 5 ثواني... ({error_msg})")
                time.sleep(5) # انتظار قبل المحاولة التالية
                continue
            else:
                # أخطاء أخرى (مثل PIN خطأ) لا فائدة من إعادة المحاولة
                return False, f"خطأ غير قابل للتجاوز: {error_msg}"

        except Exception as e:
            print(f"Network Error: {e}")
            time.sleep(2)

    return False, "فشلت جميع المحاولات. يرجى التأكد من إضافة طريقة دفع في حساب Meta."


@csrf_exempt
@require_POST
@check_plan_limit("max_channels")
def exchange_token_and_create_channel(request):
    try:
        data = json.loads(request.body)
        auth_code = data.get('code') # استلام الكود
        channel_name = data.get('name')
        target_waba_id = data.get('waba_id') # استلام المعرف من الفرونت إند
        phone_id = data.get('phone_number_id') # استلام المعرف من الفرونت إند

        if not auth_code:
            return JsonResponse({'success': False, 'error': 'No authorization code provided'}, status=400)

        # ---------------------------------------------------------
        # الخطوة 1: تبديل الكود بـ Access Token (مهم جداً التغيير هنا)
        # ---------------------------------------------------------
        exchange_url = "https://graph.facebook.com/v24.0/oauth/access_token"
        params = {
            'client_id': settings.META_APP_ID,
            'client_secret': settings.META_APP_SECRET,
            'code': auth_code,
            # 'redirect_uri': 'https://app.waselytics.com/' 
             
        }
        
        exchange_resp = requests.get(exchange_url, params=params).json()
        print(f"DEBUG Meta Response: {exchange_resp}") # أضف هذا السطر لرؤية الخطأ في Railway logs
        if 'access_token' not in exchange_resp:
            return JsonResponse({'success': False, 'error': 'Failed to exchange code', 'details': exchange_resp}, status=400)
            
        access_token = exchange_resp['access_token']

        # ---------------------------------------------------------
        # الخطوة 2: جلب رقم الهاتف الفعلي (للعرض فقط)
        # ---------------------------------------------------------
        # بما أننا نملك phone_id، جلب الرقم سهل جداً الآن
        phone_info_url = f"https://graph.facebook.com/v24.0/{phone_id}?access_token={access_token}"
        phone_info = requests.get(phone_info_url).json()
        phone_number = phone_info.get('display_phone_number', 'Unknown')

        # ---------------------------------------------------------
        # الخطوة 3: الاشتراك في الويب هوك (Subscribe App)
        # ---------------------------------------------------------
        subscribe_url = f"https://graph.facebook.com/v24.0/{target_waba_id}/subscribed_apps"
        requests.post(subscribe_url, data={'access_token': access_token})
        
        # ---------------------------------------------------------
        # الخطوة 4: الحفظ في قاعدة البيانات
        # ---------------------------------------------------------
        channel = WhatsAppChannel.objects.create(
            owner=request.user,
            name=channel_name,
            phone_number=phone_number,
            phone_number_id=phone_id,
            business_account_id=target_waba_id,
            access_token=access_token # هذا التوكن الآن جاهز للإرسال
        )
        subscribe_url = f"https://graph.facebook.com/v24.0/{target_waba_id}/subscribed_apps"
        subscribe_payload = {
            "access_token": access_token # نستخدم توكن العميل هنا
        }

        try:
            sub_resp = requests.post(subscribe_url, data=subscribe_payload)
            if sub_resp.status_code == 200:
                print(f"✅ Webhook Subscribed for WABA: {target_waba_id}")
            else:
                print(f"⚠️ Webhook Subscription Warning: {sub_resp.text}")
        except Exception as e:
            print(f"❌ Webhook Subscription Error: {str(e)}")
    
        # url = f"https://graph.facebook.com/v24.0/{phone_id}/register"

        # headers = {
        #     "Authorization": f"Bearer {access_token}",
        #     "Content-Type": "application/json"
        # }

        # payload = {
        #     "messaging_product": "whatsapp",
        #     "pin": "123456"  # هذا هو كود فك التشفير (6 أرقام)، يمكنك وضع أي رقم تريده الآن
        # }

        # try:
        #     response = requests.post(url, headers=headers, json=payload)
        #     print(f"Status: {response.status_code}")
        #     print(response.json())
            
        #     if response.status_code == 200:
        #         print("🎉 تم تسجيل الرقم بنجاح! جرب إرسال رسالة الآن.")
        #     else:
        #         print("❌ فشل التسجيل، انظر للخطأ أعلاه.")

        # except Exception as e:
        #     print(f"Error: {e}")
        register_phone_number_with_retry(phone_id, access_token, pin_code="438660", max_retries=3)
            
        channel.assigned_agents.add(request.user)

        dashboard_url = reverse('tracking')
        success_redirect_url = f"{dashboard_url}?setup=success&channel_id={channel.id}"

        return JsonResponse({
            'success': True, 
            'channel_id': channel.id,
            'phone_number': phone_number,
            'redirect_url': success_redirect_url
        })

    except IntegrityError as e:
        err_lower = str(e).lower()
        if "phone_number" in err_lower or "whatsappchannel" in err_lower:
            return JsonResponse(
                {
                    "success": False,
                    "error": (
                        "This WhatsApp number is already connected to Waselytics. "
                        "Remove or delete the existing channel first, then try again—or use a different WhatsApp Business number."
                    ),
                    "error_code": "duplicate_phone",
                },
                status=409,
            )
        logger.exception("exchange_token_and_create_channel integrity error")
        return JsonResponse(
            {
                "success": False,
                "error": "This channel could not be saved. Please try again.",
                "error_code": "integrity",
            },
            status=409,
        )
    except Exception as e:
        logger.exception("exchange_token_and_create_channel failed")
        return JsonResponse(
            {
                "success": False,
                "error": "We couldn’t finish connecting WhatsApp. Please try again.",
                "error_code": "unknown",
            },
            status=500,
        )






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

        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday_start = today_start - timedelta(days=1)

        # Date range filter: today | 7d | month (default)
        range_param = request.GET.get('range', 'month')
        if range_param == 'today':
            range_start = today_start
            chart_days = 1
        elif range_param == '7d':
            range_start = today_start - timedelta(days=6)
            chart_days = 7
        else:
            first_of_month = today_start.replace(day=1)
            range_start = first_of_month
            chart_days = (now.date() - first_of_month.date()).days + 1

        # Contacts
        total_contacts = Contact.objects.filter(channel=channel, created_at__gte=range_start).count()
        today_contacts = Contact.objects.filter(channel=channel, created_at__gte=today_start).count()
        yesterday_contacts = Contact.objects.filter(
            channel=channel, created_at__gte=yesterday_start, created_at__lt=today_start
        ).count()

        # Messages
        msgs_in_range = Message.objects.filter(channel=channel, created_at__gte=range_start)
        total_messages = msgs_in_range.count()
        sent_count = msgs_in_range.filter(is_from_me=True).count()
        received_count = msgs_in_range.filter(is_from_me=False).count()

        # Orders
        orders_base = SimpleOrder.objects.filter(channel=channel)
        if not (user.is_superuser or user.is_team_admin):
            orders_base = orders_base.filter(agent=user)
        total_order = orders_base.filter(created_at__gte=range_start).count()
        orders_today = orders_base.filter(created_at__gte=today_start).count()
        orders_yesterday = orders_base.filter(
            created_at__gte=yesterday_start, created_at__lt=today_start
        ).count()

        # Account info
        is_connected = channel.is_configured()
        account_info = {
            'display_name': channel.name,
            'phone_number': channel.phone_number,
            'waba_id': channel.business_account_id,
            'status': 'CONNECTED' if is_connected else 'DISCONNECTED',
            'is_connected': is_connected,
            'quality': 'GREEN',
            'limit': 'TIER_250'
        }

        # Chart data (one point per day in the selected range)
        today_date = now.date()
        labels = []
        sent_data = []
        received_data = []
        for i in range(chart_days - 1, -1, -1):
            day = today_date - timedelta(days=i)
            labels.append(day.strftime("%a %d") if chart_days > 1 else day.strftime("%H:00"))
            daily_msgs = Message.objects.filter(channel=channel, created_at__date=day)
            sent_data.append(daily_msgs.filter(is_from_me=True).count())
            received_data.append(daily_msgs.filter(is_from_me=False).count())

        return JsonResponse({
            'success': True,
            'stats': {
                'contacts': total_contacts,
                'messages': total_messages,
                'campaigns': 0,
                'sent': sent_count,
                'received': received_count,
                'yesterday_contacts': yesterday_contacts,
                'today_contacts': today_contacts,
                'orders_today': orders_today,
                'orders_yesterday': orders_yesterday,
                'total_orders': total_order,
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


# ---------------------------------------------------------------------------
# AI Sales Agent Analytics Dashboard
# ---------------------------------------------------------------------------
from django.http import HttpResponse
import csv
from io import StringIO


def ai_analytics_dashboard_page(request):
    """Render the AI Analytics Dashboard (channel from GET or first accessible)."""
    if not request.user.is_authenticated:
        from django.shortcuts import redirect
        from django.urls import reverse
        return redirect(reverse('login') or '/')
    channel = get_target_channel(request.user, request.GET.get('channel_id'))
    return render(request, 'dashboard/analytics.html', {
        'channel': channel,
        'channel_id': getattr(channel, 'id', None),
    })


def api_ai_analytics(request):
    """JSON: AI analytics for date range. GET range=today|7d|month, channel_id=."""
    try:
        user = request.user
        channel = get_target_channel(user, request.GET.get('channel_id'))
        if not channel:
            return JsonResponse({'error': 'Channel not found'}, status=404)

        from discount.services.ai_stats import get_ai_analytics
        now = timezone.now()
        range_param = (request.GET.get('range') or 'month').strip().lower()
        if range_param == 'today':
            date_from = now.replace(hour=0, minute=0, second=0, microsecond=0)
            date_to = now
            label = 'Today'
        elif range_param == '7d':
            date_from = now - timedelta(days=7)
            date_to = now
            label = 'Last 7 Days'
        else:
            date_from = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            date_to = now
            label = 'This Month'

        data = get_ai_analytics(channel, date_from, date_to)
        data['range_label'] = label
        return JsonResponse({'success': True, 'data': data})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)


def api_ai_analytics_export_csv(request):
    """Export AI analytics (and optionally order list) to CSV. GET range=, channel_id=."""
    try:
        user = request.user
        channel = get_target_channel(user, request.GET.get('channel_id'))
        if not channel:
            return HttpResponse('Channel not found', status=404)

        from discount.services.ai_stats import get_ai_analytics
        now = timezone.now()
        range_param = (request.GET.get('range') or 'month').strip().lower()
        if range_param == 'today':
            date_from = now.replace(hour=0, minute=0, second=0, microsecond=0)
            date_to = now
        elif range_param == '7d':
            date_from = now - timedelta(days=7)
            date_to = now
        else:
            date_from = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            date_to = now

        data = get_ai_analytics(channel, date_from, date_to)
        buf = StringIO()
        w = csv.writer(buf)
        w.writerow(['AI Analytics Export', date_from.date(), 'to', date_to.date()])
        w.writerow([])
        w.writerow(['Metric', 'Value'])
        w.writerow(['Total AI Conversations', data['total_ai_conversations']])
        w.writerow(['Total AI Messages', data['total_ai_messages']])
        w.writerow(['Orders Closed by AI', data['total_ai_orders']])
        w.writerow(['Manual Orders', data['total_manual_orders']])
        w.writerow(['AI Success Rate (%)', data['ai_conversion_rate']])
        w.writerow(['Time Saved (hours)', data['hours_saved']])
        w.writerow(['API Characters Used', data['api_characters_used']])
        w.writerow([])
        w.writerow(['Top Products (AI)', 'Count'])
        for row in data['top_products']:
            w.writerow([row['product_name'], row['count']])
        response = HttpResponse(buf.getvalue(), content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="ai_analytics_export.csv"'
        return response
    except Exception as e:
        import traceback
        traceback.print_exc()
        return HttpResponse(str(e), status=500)






# path('privacy-policy/', views.privacy_policy, name='privacy_policy'),
# path('terms/', views.terms, name='terms'),
# path('data-deletion/', views.data_deletion, name='data_deletion'),
# path('contact/', views.contact, name='contact'),

 



from django.db.models import Count, Q, F, FloatField, Case, When, Value
from django.http import JsonResponse





from django.db.models import Count, Q, F, FloatField, Case, When, Value
from django.http import JsonResponse

from discount.models import CustomUser  # تأكد من استيراد مودل المستخدم الصحيح

from django.db.models import Count, Q, Case, When, Value, F, FloatField
 # تأكد من استيراد المودلز

def api_team_stats(request):
    user = request.user
    channel_id = request.GET.get('channel_id')
    
    # 1. تحديد القناة
    target_channel = get_target_channel(user, channel_id)
    
    if not target_channel:
        return JsonResponse({'stats': []})
    
    # 2. 🔥 المنطق الجديد: تحديد من سيظهر في الإحصائيات 🔥
    
    # نعتبره "مدير" إذا كان سوبر يوزر، أو أدمن فريق، أو هو مالك القناة الحالية
    is_manager = (
        user.is_superuser or 
        getattr(user, 'is_team_admin', False) or 
        user.id == target_channel.owner_id
    )

    if is_manager:
        users_qs = CustomUser.objects.filter(
            Q(id=target_channel.owner_id) |              
            Q(channels=target_channel) |                 
            Q(simple_orders__channel=target_channel)
        ).distinct()
    else:
        # ✅ الحالة الثانية: الموظف يرى نفسه فقط
        users_qs = CustomUser.objects.filter(id=user.id)

    confirmed_statuses = ['Shipped', 'Delivered', 'Returned', 'Confirmed', 'Pending' , 'returned' , 'out_for_delivery' , 'exception' , 'delivered' ,'confirmed' ,'pending' , 'shipped' , 'cancelled' ,'failed' ]
    returned_statuses = ['Returned', 'returned', 'Return']
    pending_statuses = ['Pending', 'pending' , 'exception' , 'out_for_delivery']
    team_stats = users_qs.annotate(
        # العدد الكلي لطلبات هذا المستخدم في هذه القناة
        total=Count('simple_orders', filter=Q(simple_orders__channel=target_channel),distinct=True),

        # باقي الحالات
        confirmed=Count('simple_orders', filter=Q(simple_orders__channel=target_channel, simple_orders__status__in=confirmed_statuses),distinct=True),
        delivered=Count('simple_orders', filter=Q(simple_orders__channel=target_channel, simple_orders__status='Delivered'),distinct=True),
        pending=Count('simple_orders', filter=Q(simple_orders__channel=target_channel, simple_orders__status__in =pending_statuses ), distinct=True),
        cancelled=Count('simple_orders', filter=Q(simple_orders__channel=target_channel, simple_orders__status='Cancelled'), distinct=True),
        returned = Count('simple_orders', filter=Q(simple_orders__channel=target_channel, simple_orders__status__in=returned_statuses), distinct=True)
    ).annotate(
        # حساب النسب المئوية
        conf_rate=Case(
            When(total__gt=0, then=F('confirmed') * 100.0 / F('total')),
            default=Value(0.0), output_field=FloatField()
        ),
        del_rate=Case(
            When(confirmed__gt=0, then=F('delivered') * 100.0 / F('confirmed')),
            default=Value(0.0), output_field=FloatField()
        )
    ).order_by('-total')

    # 4. تجهيز البيانات للواجهة
    data = []
    for agent in team_stats:
        # إخفاء من ليس لديهم أي نشاط (اختياري، يمكنك إزالته إذا أردت إظهار الأصفار للموظف)
        if agent.total == 0: 
            continue 
            
        data.append({
            'initial': agent.user_name or agent.first_name or agent.email.split('@')[0],
            'name': (agent.user_name or agent.first_name or agent.email), # عدلتها لتأخذ user_name كأولوية
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
    team_id = channel.owner.id 
    dynamic_group_name = f"team_updates_{team_id}"

   
    send_socket("log_message_received", socket_payload , group_name= dynamic_group_name )



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
            assigned_name = agent.user_name or getattr(agent, 'agent_role', None) or "Agent"
            create_activity_log(contact.channel, phone, f"Conversation assigned to {assigned_name}", user=request.user)
                
        except CustomUser.DoesNotExist:

            return JsonResponse({'success': False, 'message': 'Agent not found'})
    else:
        contact.assigned_agent = None
        assigned_name = "Unassigned"

    contact.save()
    log_activity('wa_contact_assigned', f"Contact {phone} assigned to {assigned_name}", request=request)
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
            contact.assigned_agent = agent
            _name = agent.user_name or getattr(agent, 'agent_role', None) or "Agent"
            create_activity_log(contact.channel, phone, f"Conversation assigned to {_name}", user=request.user)
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


   

    log_activity('wa_contact_crm_updated', f"Contact {phone}: {action} → {value}", request=request)
    return JsonResponse({'success': True, 'message': log_msg})


# TODO: REMOVE BEFORE PRODUCTION — dev-only plan switcher for testing checkPlanLimit
@csrf_exempt
@require_POST
def dev_switch_plan(request):
    """Temporary endpoint to switch a user's plan for local testing of plan limits."""
    from django.conf import settings as _settings
    if not getattr(_settings, "DEBUG", False):
        return JsonResponse({"error": "Not available in production"}, status=404)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON body"}, status=400)

    user_id = data.get("userId")
    new_plan_name = (data.get("newPlan") or "").strip().lower()
    if not user_id or not new_plan_name:
        return JsonResponse({"error": "userId and newPlan are required"}, status=400)

    from discount.models import Plan, CustomUser as User
    user = User.objects.filter(pk=user_id).first()
    if not user:
        return JsonResponse({"error": f"User {user_id} not found"}, status=404)

    plan = Plan.objects.filter(name__iexact=new_plan_name).first()
    if not plan:
        available = list(Plan.objects.values_list("name", flat=True))
        return JsonResponse(
            {"error": f"Plan '{new_plan_name}' not found", "available_plans": available},
            status=404,
        )

    user.plan = plan
    user.save(update_fields=["plan"])

    from discount.services.plan_limits import PLAN_LIMITS, is_limit_reached
    limits_snapshot = {}
    for resource in ("max_channels", "max_team_members", "max_monthly_orders"):
        reached, limit, current = is_limit_reached(user, resource)
        limits_snapshot[resource] = {"limit": limit, "current": current, "reached": reached}

    return JsonResponse({
        "success": True,
        "user_id": user.pk,
        "new_plan": plan.name,
        "limits": limits_snapshot,
    })


# ── Stripe Billing ──────────────────────────────────────────────────────

@csrf_exempt
@require_POST
def create_checkout_session(request):
    """Create a Stripe Checkout Session for $1 upfront + 7-day subscription trial."""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=401)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON body"}, status=400)

    user_id = str(data.get("userId") or request.user.pk).strip()
    price_id = str(data.get("priceId") or "").strip()
    plan_name = str(data.get("planId") or data.get("plan") or "").strip().lower()
    if not user_id:
        return JsonResponse({"error": "userId is required"}, status=400)
    if not price_id and not plan_name:
        return JsonResponse({"error": "priceId or planId is required"}, status=400)
    if user_id != str(request.user.pk):
        return JsonResponse({"error": "userId does not match authenticated user"}, status=403)

    from discount.services.stripe_billing import create_trial_checkout_session
    url = create_trial_checkout_session(
        user=request.user,
        user_id=user_id,
        price_id=price_id or None,
        plan_name=plan_name or None,
    )
    if not url:
        return JsonResponse({"error": "Failed to create checkout session"}, status=500)

    return JsonResponse({"success": True, "url": url})


@csrf_exempt
@require_POST
def create_portal_session(request):
    """Create a Stripe Billing Portal session for current user."""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=401)

    from discount.services.stripe_billing import create_billing_portal_session

    url = create_billing_portal_session(request.user)
    if not url:
        return JsonResponse({"error": "Failed to create billing portal session"}, status=500)
    return JsonResponse({"success": True, "url": url})


@require_GET
def wallet_summary(request):
    """Return wallet summary for current authenticated user."""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=401)

    owner = getattr(request.user, "team_admin", None) or request.user
    return JsonResponse(
        {
            "success": True,
            "walletBalance": str(getattr(owner, "wallet_balance", 0) or 0),
            "totalTokensUsed": int(getattr(owner, "total_tokens_used", 0) or 0),
            "lowBalanceAlertEnabled": bool(getattr(owner, "low_balance_alert_enabled", True)),
        }
    )


@csrf_exempt
@require_POST
def wallet_settings(request):
    """Update wallet settings for current authenticated user."""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=401)

    try:
        data = json.loads(request.body or "{}")
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON body"}, status=400)

    if "lowBalanceAlertEnabled" not in data:
        return JsonResponse({"error": "lowBalanceAlertEnabled is required"}, status=400)

    owner = getattr(request.user, "team_admin", None) or request.user
    owner.low_balance_alert_enabled = bool(data.get("lowBalanceAlertEnabled"))
    owner.save(update_fields=["low_balance_alert_enabled"])
    return JsonResponse({"success": True, "lowBalanceAlertEnabled": owner.low_balance_alert_enabled})


@csrf_exempt
@require_POST
def wallet_topup(request):
    """Create Stripe Checkout session for wallet top-up."""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=401)
    try:
        data = json.loads(request.body or "{}")
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON body"}, status=400)

    user_id = str(data.get("userId") or "").strip()
    amount = data.get("amount")
    if not user_id or amount is None:
        return JsonResponse({"error": "userId and amount are required"}, status=400)
    if user_id != str(request.user.pk):
        return JsonResponse({"error": "userId does not match authenticated user"}, status=403)

    from discount.services.stripe_billing import create_wallet_topup_checkout_session

    url = create_wallet_topup_checkout_session(request.user, user_id=user_id, amount=amount)
    if not url:
        return JsonResponse({"error": "Failed to create wallet top-up session"}, status=500)
    return JsonResponse({"success": True, "url": url})


@require_GET
def api_channel_limit_status(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=401)
    from discount.services.plan_limits import get_max_channels_status

    return JsonResponse(get_max_channels_status(request.user))


@csrf_exempt
@require_POST
def api_create_extra_channel_checkout(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=401)
    from discount.services.plan_limits import _resolve_admin_user, get_max_channels_status
    from discount.services.stripe_billing import create_extra_channel_checkout_session

    snap = get_max_channels_status(request.user)
    if not snap.get("can_purchase_extra"):
        return JsonResponse(
            {
                "success": False,
                "error": "Cannot purchase extra channel slot",
                "limits": snap,
            },
            status=403,
        )
    owner = _resolve_admin_user(request.user)
    url = create_extra_channel_checkout_session(owner)
    if not url:
        return JsonResponse({"success": False, "error": "Failed to create checkout session"}, status=500)
    return JsonResponse({"success": True, "url": url})


@require_GET
def api_verify_extra_channel_checkout(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=401)
    session_id = (request.GET.get("session_id") or "").strip()
    if not session_id:
        return JsonResponse({"error": "session_id required"}, status=400)

    from discount.services.plan_limits import _resolve_admin_user, get_max_channels_status
    from discount.services.stripe_billing import confirm_extra_channel_checkout_session

    owner = _resolve_admin_user(request.user)
    if request.user.pk != owner.pk:
        return JsonResponse({"error": "Only the workspace owner can confirm this payment"}, status=403)

    ok, err = confirm_extra_channel_checkout_session(session_id, owner)
    if not ok:
        return JsonResponse({"success": False, "error": err or "verification_failed"}, status=400)
    return JsonResponse({"success": True, "limits": get_max_channels_status(request.user)})


@csrf_exempt
@require_POST
def stripe_webhook(request):
    """
    Handle Stripe webhook events using raw request.body for signature verification.
    Returns 200 for non-critical processing errors to avoid retry storms.
    """
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")

    from discount.services.stripe_billing import handle_checkout_webhook
    ok = handle_checkout_webhook(payload, sig_header)
    if ok:
        return JsonResponse({"received": True})
    # Signature/config errors are critical; return 400 so Stripe flags invalid delivery.
    return JsonResponse({"received": False}, status=400)


# ──────────────────────────────────────────────────────────────────────────────
#  Store Payment Methods  (encrypted at rest, used by AI for digital products)
# ──────────────────────────────────────────────────────────────────────────────

@login_required
@require_GET
def api_payment_methods_list(request):
    """Return all payment methods for the authenticated merchant (masked details)."""
    from discount.models import StorePaymentMethod
    from discount.services.plan_limits import _resolve_admin_user
    owner = _resolve_admin_user(request.user)
    methods = StorePaymentMethod.objects.filter(owner=owner).order_by('provider_name', 'id')
    data = [
        {
            'id': m.id,
            'provider_name': m.provider_name,
            'provider_label': m.get_provider_name_display(),
            'display_name': m.display_name,
            'label': m.label,
            'is_bank': m.is_bank,
            'account_holder_name': m.account_holder_name or '',
            'account_details_masked': m.get_masked_details(),
            'instructions': m.instructions,
            'is_active': m.is_active,
        }
        for m in methods
    ]
    provider_choices = [
        {'value': v, 'label': l, 'is_bank': v in StorePaymentMethod.BANK_PROVIDERS}
        for v, l in StorePaymentMethod.PROVIDER_CHOICES
    ]
    return JsonResponse({'methods': data, 'provider_choices': provider_choices})


@csrf_exempt
@login_required
@require_POST
def api_payment_methods_create(request):
    """Create a new payment method. Account details are encrypted before storage."""
    from discount.models import StorePaymentMethod
    from discount.services.plan_limits import _resolve_admin_user
    owner = _resolve_admin_user(request.user)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON body.'}, status=400)

    provider = body.get('provider_name', '').strip()
    raw_identifier = body.get('account_identifier', '').strip()
    account_holder_name = body.get('account_holder_name', '').strip()
    display_name = body.get('display_name', '').strip()
    instructions = body.get('instructions', '').strip()

    valid_providers = [v for v, _ in StorePaymentMethod.PROVIDER_CHOICES]
    if provider not in valid_providers:
        return JsonResponse({'error': 'Invalid provider_name.'}, status=400)
    if not raw_identifier:
        return JsonResponse({'error': 'account_identifier is required.'}, status=400)

    is_bank = provider in StorePaymentMethod.BANK_PROVIDERS
    # RIB must be exactly 24 digits for bank providers
    if is_bank and not re.fullmatch(r'\d{24}', raw_identifier.replace(' ', '')):
        return JsonResponse({'error': 'RIB must be exactly 24 digits.'}, status=400)

    method = StorePaymentMethod(
        owner=owner,
        provider_name=provider,
        display_name=display_name,
        account_holder_name=account_holder_name if is_bank else '',
        instructions=instructions,
        is_active=True,
    )
    method.set_account_details(raw_identifier.replace(' ', '') if is_bank else raw_identifier)
    method.save()

    return JsonResponse({
        'success': True,
        'id': method.id,
        'label': method.label,
        'is_bank': method.is_bank,
        'provider_label': method.get_provider_name_display(),
        'account_holder_name': method.account_holder_name or '',
        'account_details_masked': method.get_masked_details(),
        'instructions': method.instructions,
        'is_active': method.is_active,
    })


@csrf_exempt
@login_required
@require_POST
def api_payment_methods_toggle(request, method_id: int):
    """Toggle the is_active flag of a payment method."""
    from discount.models import StorePaymentMethod
    from discount.services.plan_limits import _resolve_admin_user
    owner = _resolve_admin_user(request.user)

    try:
        method = StorePaymentMethod.objects.get(pk=method_id, owner=owner)
    except StorePaymentMethod.DoesNotExist:
        return JsonResponse({'error': 'Not found.'}, status=404)

    method.is_active = not method.is_active
    method.save(update_fields=['is_active'])
    return JsonResponse({'success': True, 'is_active': method.is_active})


@csrf_exempt
@login_required
@require_POST
def api_payment_methods_delete(request, method_id: int):
    """Permanently delete a payment method."""
    from discount.models import StorePaymentMethod
    from discount.services.plan_limits import _resolve_admin_user
    owner = _resolve_admin_user(request.user)

    deleted, _ = StorePaymentMethod.objects.filter(pk=method_id, owner=owner).delete()
    if deleted:
        return JsonResponse({'success': True})
    return JsonResponse({'error': 'Not found.'}, status=404)


# ──────────────────────────────────────────────────────────────────────────────
#  Digital-product fulfillment — receipt verification
# ──────────────────────────────────────────────────────────────────────────────

def _send_wa_text(channel, to: str, text: str):
    """
    Send a plain-text WhatsApp message via Meta Cloud API.
    Returns (success: bool, wamid: str | None).
    """
    try:
        from discount.services.message_normalize import normalize_outbound_text
        text = normalize_outbound_text(text or "")
    except Exception:
        pass
    access_token = getattr(channel, 'access_token', None)
    phone_id     = getattr(channel, 'phone_number_id', None)
    if not access_token or not phone_id:
        logging.getLogger(__name__).warning(
            "_send_wa_text: channel %s has no credentials", channel.pk
        )
        return False, None
    api_version = getattr(channel, 'api_version', None) or 'v17.0'
    url = f"https://graph.facebook.com/{api_version}/{phone_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }
    try:
        resp = requests.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
            timeout=15,
        )
        if resp.status_code == 200:
            wamid = None
            try:
                wamid = (resp.json().get('messages') or [{}])[0].get('id')
            except Exception:
                pass
            return True, wamid
        logging.getLogger(__name__).warning(
            "_send_wa_text failed: %s %s", resp.status_code, resp.text[:300]
        )
        return False, None
    except Exception as exc:
        logging.getLogger(__name__).exception("_send_wa_text exception: %s", exc)
        return False, None


def _persist_outbound_chat_message(
    channel,
    customer_phone,
    body,
    *,
    wa_sent=False,
    wamid=None,
    user=None,
):
    """
    Save an outbound WhatsApp text to the dashboard chat history.
    Used when `_send_wa_text` is called directly (receipt reject / fulfillment).
    """
    if not channel or not (customer_phone or '').strip():
        return None
    try:
        from discount.models import Message as WaMessage

        msg = WaMessage.objects.create(
            channel=channel,
            sender=(customer_phone or '').strip(),
            body=(body or '')[:4096],
            is_from_me=True,
            status='sent' if wa_sent else 'failed',
            type='text',
            message_id=wamid or None,
            user=user,
        )
        return msg.id
    except Exception as exc:
        logging.getLogger(__name__).warning(
            "_persist_outbound_chat_message failed: %s", exc,
        )
        return None


@csrf_exempt
@login_required
@require_POST
def api_verify_receipt(request):
    """
    Merchant approves or rejects a payment receipt for a digital order.

    POST body (JSON):
        order_id   – SimpleOrder.order_id (string)
        action     – "approve" | "reject"
        reason     – required when action is "reject" (merchant explanation)

    Approve flow:
        1. Mark the receipt message as approved.
        2. Build a fulfilment text (fulfillment_message + download link).
        3. Send it to the customer via WhatsApp.
        4. Set order.status = 'completed'.

    Reject flow:
        1. Mark the receipt message as rejected.
        2. Revert order.status = 'pending_payment' and save payment_rejection_reason.
        3. Restore FSM AWAITING_PAYMENT_RECEIPT for the AI agent.
        4. Send a localized WhatsApp message (store/agent language + reason).
    """
    from discount.models import SimpleOrder, Message as WaMessage
    from discount.services.plan_limits import _resolve_admin_user
    from discount.services.fulfillment_messages import (
        get_localized_rejection_message,
        resolve_fulfillment_language_code,
    )
    from discount.whatssapAPI.session_state import (
        STATE_AWAITING_PAYMENT_RECEIPT,
        set_conversation_state,
    )

    owner = _resolve_admin_user(request.user)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON body.'}, status=400)

    order_id = (body.get('order_id') or '').strip()
    action   = (body.get('action')   or '').strip().lower()
    reason   = (body.get('reason')   or '').strip()

    if not order_id:
        return JsonResponse({'error': 'order_id is required.'}, status=400)
    if action not in ('approve', 'reject'):
        return JsonResponse({'error': 'action must be "approve" or "reject".'}, status=400)
    if action == 'reject' and not reason:
        return JsonResponse({'error': 'reason is required when rejecting a receipt.'}, status=400)

    # Fetch the order — must belong to a channel owned by this merchant
    try:
        order = SimpleOrder.objects.select_related('product', 'channel').get(
            order_id=order_id,
            channel__owner=owner,
        )
    except SimpleOrder.DoesNotExist:
        return JsonResponse({'error': 'Order not found or access denied.'}, status=404)

    channel         = order.channel
    customer_phone  = order.customer_phone

    # Find the most recent pending-review receipt message for this customer+channel
    receipt_msg = (
        WaMessage.objects
        .filter(
            sender=customer_phone,
            channel=channel,
            is_payment_receipt=True,
            receipt_status='pending_review',
        )
        .order_by('-created_at')
        .first()
    )

    # ── REJECT ─────────────────────────────────────────────────────────────
    if action == 'reject':
        if receipt_msg:
            receipt_msg.receipt_status = 'rejected'
            receipt_msg.save(update_fields=['receipt_status'])

        order.status = 'pending_payment'
        order.payment_rejection_reason = reason[:255]
        order.payment_rejection_notice_text = None
        order.save(update_fields=[
            'status',
            'payment_rejection_reason',
            'payment_rejection_notice_text',
        ])

        if customer_phone and channel:
            try:
                set_conversation_state(
                    channel,
                    customer_phone,
                    STATE_AWAITING_PAYMENT_RECEIPT,
                    order_id=order.order_id,
                )
            except Exception as _fsm_set_err:
                logging.getLogger(__name__).warning(
                    "api_verify_receipt: set AWAITING_PAYMENT_RECEIPT failed for %s: %s",
                    order.order_id,
                    _fsm_set_err,
                )

        lang_code = resolve_fulfillment_language_code(
            order=order,
            channel=channel,
            customer_phone=customer_phone,
        )
        rejection_text = get_localized_rejection_message(lang_code, reason)
        wa_sent = False
        wamid = None
        rejection_message_id = None
        if channel and customer_phone:
            wa_sent, wamid = _send_wa_text(channel, customer_phone, rejection_text)
            if wa_sent:
                order.payment_rejection_notice_text = rejection_text
                order.save(update_fields=['payment_rejection_notice_text'])
            rejection_message_id = _persist_outbound_chat_message(
                channel,
                customer_phone,
                rejection_text,
                wa_sent=wa_sent,
                wamid=wamid,
                user=request.user if getattr(request, 'user', None) and request.user.is_authenticated else None,
            )

        return JsonResponse({
            'success': True,
            'new_status': 'pending_payment',
            'whatsapp_sent': wa_sent,
            'rejection_message_id': rejection_message_id,
        })

    # ── APPROVE ────────────────────────────────────────────────────────────
    if receipt_msg:
        receipt_msg.receipt_status = 'approved'
        receipt_msg.save(update_fields=['receipt_status'])

    order.status = 'completed'
    reject_fields_cleared = bool(
        getattr(order, 'payment_rejection_reason', None)
        or getattr(order, 'payment_rejection_notice_text', None)
    )
    if reject_fields_cleared:
        order.payment_rejection_reason = None
        order.payment_rejection_notice_text = None
        order.save(update_fields=[
            'status',
            'payment_rejection_reason',
            'payment_rejection_notice_text',
        ])
    else:
        order.save(update_fields=['status'])

    if customer_phone and channel:
        try:
            from discount.whatssapAPI.session_state import clear_conversation_state
            clear_conversation_state(channel, customer_phone)
        except Exception as _fsm_clear_err:
            logging.getLogger(__name__).warning(
                "api_verify_receipt: clear_conversation_state failed for order %s: %s",
                order.order_id, _fsm_clear_err,
            )

    # ── Dynamic Digital Stock consumption (race-safe FIFO) ────────────────
    # If the product has pre-loaded `DigitalAssetStock` rows we lock the
    # oldest unsold one with `SELECT … FOR UPDATE`, mark it as sold, and
    # link it to this order — all inside one transaction so two parallel
    # approvals on the same product can never grab the same row.
    #
    # The static `digital_url` / `digital_file` flow further below is the
    # fallback when no dynamic stock exists (legacy / one-off products).
    #
    # `consumed_stock_value` is the plaintext credential (single key OR
    # "email:password"). `consumed_stock_format` is the product's
    # `stock_format` at consume time. Both feed the WA text + spoiler
    # `asset_fields` builders below.
    product = order.product
    consumed_stock_value = None
    consumed_stock_format = None
    consumed_stock_row_id = None
    stock_depleted = False

    if product and bool(getattr(product, 'is_digital', False)):
        try:
            from discount.models import DigitalAssetStock
            with transaction.atomic():
                stock_row = (
                    DigitalAssetStock.objects
                    .select_for_update()
                    .filter(product=product, is_sold=False)
                    .order_by('id')
                    .first()
                )
                if stock_row:
                    plaintext = stock_row.get_asset_content()
                    if plaintext:
                        stock_row.is_sold = True
                        stock_row.order = order
                        stock_row.sold_at = timezone.now()
                        stock_row.save(update_fields=['is_sold', 'order', 'sold_at'])
                        consumed_stock_value = plaintext
                        consumed_stock_format = (
                            getattr(product, 'stock_format', None) or 'single'
                        )
                        consumed_stock_row_id = stock_row.id
                    else:
                        # Corrupted ciphertext (key rotation?). Leave the
                        # row available — don't consume something we
                        # can't actually deliver.
                        logging.getLogger(__name__).warning(
                            "api_verify_receipt: stock row %s for product %s "
                            "decrypted to empty — skipping consumption.",
                            stock_row.id, product.id,
                        )
        except Exception as _stock_err:
            logging.getLogger(__name__).warning(
                "api_verify_receipt: digital-stock consume failed for "
                "order %s product %s: %s — falling back to static URL.",
                order.order_id, getattr(product, 'id', None), _stock_err,
            )

    # Build the (legacy) static download link — only used when no dynamic
    # stock was consumed. NB: if dynamic stock IS in play, `download_url`
    # stays empty and the static fallback is skipped.
    download_url = ''
    if not consumed_stock_value and product:
        if (getattr(product, 'digital_url', None) or '').strip():
            download_url = product.digital_url.strip()
        elif getattr(product, 'digital_file', None) and product.digital_file.name:
            try:
                download_url = request.build_absolute_uri(product.digital_file.url)
            except Exception:
                download_url = product.digital_file.url

    # If the seller enabled dynamic stock but the inventory is empty,
    # flag it in the response so the dashboard can show a "stock depleted"
    # warning. We still send the public thank-you text so the customer
    # isn't left in silence.
    if product and bool(getattr(product, 'is_digital', False)) \
            and not consumed_stock_value and not download_url:
        try:
            from discount.models import DigitalAssetStock as _DS
            if _DS.objects.filter(product=product).exists():
                stock_depleted = True
        except Exception:
            pass

    fulfillment_note = (getattr(product, 'fulfillment_message', None) or '').strip() if product else ''

    # ── Split the fulfillment payload ─────────────────────────────────────
    # `public_body`  — non-sensitive thank-you, stored plaintext on the
    #                  Message row; visible to every employee in chat.
    # `asset_fields` — `{label_key: plaintext}` dict encrypted on the
    #                  Message row; revealed ONLY to the store owner via
    #                  the gated reveal endpoint (Telegram-style spoiler).
    # The WhatsApp customer ALWAYS receives the full text (public_body +
    # the credentials), regardless of the dashboard RBAC.
    from discount.services.fulfillment_messages import (
        get_localized_fulfillment_message,
        resolve_fulfillment_language_code,
    )

    has_asset = bool(consumed_stock_value or download_url)
    if fulfillment_note:
        public_body = fulfillment_note
    else:
        agent_language_code = resolve_fulfillment_language_code(
            order=order,
            channel=channel,
            customer_phone=customer_phone,
        )
        public_body = get_localized_fulfillment_message(
            agent_language_code,
            has_asset=has_asset,
        )

    asset_fields = {}
    fulfilment_text = public_body

    if consumed_stock_value:
        # Dynamic-stock path — branch on the product's stock_format.
        if consumed_stock_format == 'combo':
            # Split on the FIRST colon so passwords containing ':' still
            # work for legacy rows that pre-date strict validation.
            email_part, _, password_part = consumed_stock_value.partition(':')
            email_part = email_part.strip()
            password_part = password_part.strip()
            asset_fields = {"email": email_part, "password": password_part}
            fulfilment_text = (
                f"{public_body}\n\n"
                f"📧 {email_part}\n"
                f"🔑 {password_part}"
            )
        elif consumed_stock_format == 'iptv':
            val = consumed_stock_value.strip()
            if val.lower().startswith('http'):
                asset_fields = {"link": val, "iptv": val}
                fulfilment_text = f"{public_body}\n\n📺 IPTV\n🔗 {val}"
            else:
                asset_fields = {"iptv": val}
                fulfilment_text = f"{public_body}\n\n📺 IPTV\n{val}"
        else:
            # 'single' (or unknown → default) — one opaque credential.
            asset_fields = {"license": consumed_stock_value}
            fulfilment_text = f"{public_body}\n\n🔑 {consumed_stock_value}"
    elif download_url:
        # Legacy static-URL path.
        asset_fields = {"link": download_url}
        fulfilment_text = f"{public_body}\n\n🔗 {download_url}"

    wa_sent = False
    fulfilment_wamid = None
    if channel and customer_phone:
        wa_sent, fulfilment_wamid = _send_wa_text(channel, customer_phone, fulfilment_text)

    # ── Persist the outgoing fulfillment message so the dashboard chat
    # can render it as a Telegram-style spoiler bubble for non-owner
    # employees. This persistence is NEW for this flow — `_send_wa_text`
    # is wire-only, so historically these fulfillment messages never
    # appeared in the dashboard history.
    #
    # The body is saved in two passes because the spoiler `<span>`
    # placeholder needs `data-id="<msg.pk>"` baked in:
    #   pass 1: save with the plain `public_body` to mint the row id.
    #   pass 2: rebuild the body as labelled spoiler HTML with that id.
    #
    # Failures here do NOT break the API contract — the WA send has
    # already completed before this point.
    delivery_message_id = None
    try:
        from discount.models import Message as WaMessage

        # `asset_fields` was built upstream (dynamic-stock OR static URL
        # OR neither). Schema is `{field: value}` so the spoiler renderer
        # can show one labelled placeholder per field — keys "license",
        # "email" + "password", and "link" all have entries in
        # `_SPOILER_FIELD_CONFIG`.

        delivery_msg = WaMessage(
            sender=customer_phone or '',
            body=public_body,
            channel=channel,
            is_from_me=True,
            status='sent' if wa_sent else 'failed',
            type='text',
        )
        if asset_fields:
            delivery_msg.is_digital_delivery = True
            delivery_msg.set_encrypted_asset(asset_fields)
        delivery_msg.save()
        delivery_message_id = delivery_msg.id

        # Second pass: rebuild `body` with the per-field spoiler spans
        # now that we know the row id. The spans carry NO ciphertext and
        # NO plaintext — only the redaction mask plus the `data-id` and
        # `data-field` attributes the JS reveal needs.
        if asset_fields:
            delivery_msg.body = _render_spoiler_body_html(
                delivery_msg.id,
                list(asset_fields.keys()),
                public_body=public_body,
            )
            delivery_msg.save(update_fields=['body'])
    except Exception as _persist_err:
        logging.getLogger(__name__).warning(
            "api_verify_receipt: failed to persist fulfillment message for "
            "order %s: %s", order.order_id, _persist_err,
        )

    # ── Asset disclosure gate for the approve response ────────────────────
    # `_resolve_admin_user` walks the team_admin chain (so employees can
    # approve on the owner's behalf), but the new spoiler RBAC says the
    # download URL itself must reach ONLY the absolute store owner (or a
    # superuser). Employees see `download_url: null` here — they can still
    # confirm the approval succeeded, but the asset is only accessible via
    # the dashboard's owner-gated reveal endpoint.
    is_absolute_owner = bool(
        getattr(request.user, 'is_superuser', False)
        or (channel and getattr(channel, 'owner_id', None) == getattr(request.user, 'id', None))
    )
    response_payload = {
        'success':    True,
        'new_status': 'completed',
        'wa_sent':    wa_sent,
        'download_url': download_url if is_absolute_owner else None,
        'delivery_message_id': delivery_message_id,
        # Dynamic-stock telemetry for the dashboard (no plaintext leaks):
        #   - `stock_consumed_row_id`: the just-consumed DigitalAssetStock id
        #     (null if static-URL path was used).
        #   - `stock_depleted`: True when the product had dynamic-stock
        #     enabled but the inventory is now exhausted — the dashboard
        #     should surface a "stock empty" warning to the seller.
        'stock_consumed_row_id': consumed_stock_row_id,
        'stock_depleted': stock_depleted,
    }
    return JsonResponse(response_payload)


@csrf_exempt
@login_required
@require_POST
def api_resolve_support(request):
    """
    Merchant resolves a post-sale support ticket (replacement approve / reject).

    POST JSON: ``order_id``, ``action`` ∈ {``approve``, ``reject``}
    """
    from discount.models import SimpleOrder, Message as WaMessage
    from discount.services.plan_limits import _resolve_admin_user
    from discount.services.digital_fulfillment import (
        consume_next_digital_stock,
        resolve_static_download_url,
        build_fulfillment_text,
        build_public_body_for_delivery,
    )
    from discount.services.fulfillment_messages import get_localized_support_rejection_message
    owner = _resolve_admin_user(request.user)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON body.'}, status=400)

    order_id = (body.get('order_id') or '').strip()
    action = (body.get('action') or '').strip().lower()

    if not order_id:
        return JsonResponse({'error': 'order_id is required.'}, status=400)
    if action not in ('approve', 'reject'):
        return JsonResponse({'error': 'action must be "approve" or "reject".'}, status=400)

    try:
        order = SimpleOrder.objects.select_related('product', 'channel').get(
            order_id=order_id,
            channel__owner=owner,
        )
    except SimpleOrder.DoesNotExist:
        return JsonResponse({'error': 'Order not found or access denied.'}, status=404)

    if not order.is_digital or order.status != 'completed':
        return JsonResponse({'error': 'Support resolution applies to completed digital orders only.'}, status=400)

    if order.support_status != _SUPPORT_REVIEW_STATUS:
        return JsonResponse({
            'error': f'Order is not under review (current support_status={order.support_status}).',
        }, status=400)

    channel = order.channel
    customer_phone = order.customer_phone
    product = order.product

    if action == 'reject':
        order.support_status = 'rejected'
        order.save(update_fields=['support_status'])
        lang_code = None
        try:
            from discount.services.fulfillment_messages import resolve_fulfillment_language_code
            lang_code = resolve_fulfillment_language_code(
                order=order, channel=channel, customer_phone=customer_phone,
            )
        except Exception:
            pass
        rejection_text = get_localized_support_rejection_message(lang_code or 'ar')
        wa_sent = False
        if channel and customer_phone:
            wa_sent, _wamid = _send_wa_text(channel, customer_phone, rejection_text)
            _persist_outbound_chat_message(
                channel,
                customer_phone,
                rejection_text,
                wa_sent=wa_sent,
                wamid=_wamid,
                user=request.user if getattr(request, 'user', None) and request.user.is_authenticated else None,
            )
        return JsonResponse({
            'success': True,
            'support_status': 'rejected',
            'wa_sent': wa_sent,
        })

    # ── APPROVE: send replacement (new stock row or static URL) ───────────
    stock = consume_next_digital_stock(product, order)
    consumed_stock_value = stock.get('consumed_value', '')
    consumed_stock_format = stock.get('stock_format', 'single')
    consumed_stock_row_id = stock.get('stock_row_id')
    download_url = ''
    if not consumed_stock_value:
        download_url = resolve_static_download_url(product, request)

    stock_depleted = False
    if product and bool(getattr(product, 'is_digital', False)) \
            and not consumed_stock_value and not download_url:
        try:
            from discount.models import DigitalAssetStock as _DS
            if _DS.objects.filter(product=product).exists():
                stock_depleted = True
        except Exception:
            pass

    if stock_depleted:
        return JsonResponse({
            'error': 'No replacement stock available. Add more digital stock to this product.',
            'stock_depleted': True,
        }, status=409)

    public_body = build_public_body_for_delivery(
        order,
        channel,
        customer_phone,
        is_replacement=True,
        product=product,
        consumed_value=consumed_stock_value,
        download_url=download_url,
    )
    fulfilment_text, asset_fields = build_fulfillment_text(
        public_body,
        consumed_value=consumed_stock_value,
        stock_format=consumed_stock_format,
        download_url=download_url,
    )

    wa_sent = False
    if channel and customer_phone:
        wa_sent, _support_wamid = _send_wa_text(channel, customer_phone, fulfilment_text)

    delivery_message_id = None
    try:
        delivery_msg = WaMessage(
            sender=customer_phone or '',
            body=public_body,
            channel=channel,
            is_from_me=True,
            status='sent' if wa_sent else 'failed',
            type='text',
        )
        if asset_fields:
            delivery_msg.is_digital_delivery = True
            delivery_msg.set_encrypted_asset(asset_fields)
        delivery_msg.save()
        delivery_message_id = delivery_msg.id
        if asset_fields:
            delivery_msg.body = _render_spoiler_body_html(
                delivery_msg.id,
                list(asset_fields.keys()),
                public_body=public_body,
            )
            delivery_msg.save(update_fields=['body'])
    except Exception as _persist_err:
        logging.getLogger(__name__).warning(
            'api_resolve_support: persist replacement message failed order=%s: %s',
            order.order_id, _persist_err,
        )

    order.support_status = 'resolved'
    order.save(update_fields=['support_status'])

    return JsonResponse({
        'success': True,
        'support_status': 'resolved',
        'wa_sent': wa_sent,
        'delivery_message_id': delivery_message_id,
        'stock_consumed_row_id': consumed_stock_row_id,
        'stock_depleted': stock_depleted,
    })


# ══════════════════════════════════════════════════════════════════════════
# Digital-delivery spoiler reveal — strict owner-only decryption gate
# ══════════════════════════════════════════════════════════════════════════
#
# Security contract (do NOT loosen without a security review):
#
#   1. Authentication:   `@login_required` — anonymous requests get 302→login.
#   2. CSRF:             `@csrf_exempt` (mirrors `api_verify_receipt`; the
#                        frontend still sends `X-CSRFToken` for defense in
#                        depth and the session cookie is `SameSite=Lax`).
#   3. Method:           `@require_POST` — never GET, so the asset cannot be
#                        prefetched / cached / linked.
#   4. RBAC:             Plaintext disclosure is gated on
#                            request.user.is_superuser
#                          OR request.user.id == message.channel.owner_id
#                        We deliberately do NOT use `_resolve_admin_user(...)`
#                        here. That helper walks the `team_admin` chain so
#                        employees inherit their admin's billing identity
#                        — fine for plan limits, fatal for asset reveal,
#                        because it would let any sub-agent decrypt the
#                        owner's credentials.
#   5. Failure mode:     Any negative branch returns 403 with the exact JSON
#                        error string the spec mandates. We never reveal
#                        whether the message exists, belongs to a different
#                        channel, or has a corrupted ciphertext — all those
#                        paths look identical to the client.
#   6. Output:           Only `{ "asset": "<plaintext>" }` on success. We
#                        never echo the message id, channel id, or any
#                        sibling metadata that could help enumeration.
@csrf_exempt
@login_required
@require_POST
def api_reveal_asset(request):
    """
    POST /discount/whatssapAPI/api/messages/reveal-asset/

    Body (JSON): { "message_id": <int> }

    On success (HTTP 200):
        { "fields": { "<field_name>": "<plaintext value>", ... } }

        For legacy single-asset rows we synthesize `{"link": "<value>"}`
        so the frontend can always iterate `data.fields` uniformly.

    On any authorization or validation failure (HTTP 403):
        { "error": "Access Denied: Insufficient permissions." }
    """
    from discount.models import Message as WaMessage

    FORBIDDEN_PAYLOAD = {"error": "Access Denied: Insufficient permissions."}

    # --- 1. Parse the body conservatively ------------------------------------
    try:
        body = json.loads(request.body or b'{}')
    except (json.JSONDecodeError, ValueError):
        return HttpResponseForbidden(
            json.dumps(FORBIDDEN_PAYLOAD),
            content_type='application/json',
        )

    raw_id = body.get('message_id')
    try:
        message_id = int(raw_id)
    except (TypeError, ValueError):
        return HttpResponseForbidden(
            json.dumps(FORBIDDEN_PAYLOAD),
            content_type='application/json',
        )

    # --- 2. Fetch with channel pre-joined for the RBAC check ----------------
    # We do NOT 404 when the message is missing — that would leak existence.
    # Both "missing" and "unauthorized" return the same 403 payload.
    try:
        message = (
            WaMessage.objects
            .select_related('channel')
            .get(pk=message_id)
        )
    except WaMessage.DoesNotExist:
        return HttpResponseForbidden(
            json.dumps(FORBIDDEN_PAYLOAD),
            content_type='application/json',
        )

    # --- 3. Validate the spoiler precondition --------------------------------
    if not getattr(message, 'is_digital_delivery', False):
        return HttpResponseForbidden(
            json.dumps(FORBIDDEN_PAYLOAD),
            content_type='application/json',
        )
    if not getattr(message, 'encrypted_asset', None):
        return HttpResponseForbidden(
            json.dumps(FORBIDDEN_PAYLOAD),
            content_type='application/json',
        )

    # --- 4. Strict owner-only authorization ----------------------------------
    # NB: superuser is a deliberate escape hatch for support; if you want a
    # hard "owner only" policy, remove the `is_superuser` branch.
    channel = message.channel
    user = request.user
    is_authorized = bool(
        getattr(user, 'is_superuser', False)
        or (channel and getattr(channel, 'owner_id', None) == getattr(user, 'id', None))
    )
    if not is_authorized:
        logging.getLogger(__name__).info(
            "api_reveal_asset: DENIED user=%s message=%s channel_owner=%s",
            getattr(user, 'id', None),
            message_id,
            getattr(channel, 'owner_id', None),
        )
        return HttpResponseForbidden(
            json.dumps(FORBIDDEN_PAYLOAD),
            content_type='application/json',
        )

    # --- 5. Decrypt server-side and emit the structured field map ----------
    # Returning a dict (rather than a single plaintext string) lets the
    # Telegram-style spoiler renderer drop each value into the matching
    # `<span data-field="...">` placeholder without any further parsing.
    plaintext_fields = message.get_decrypted_asset_fields()
    if not plaintext_fields:
        # Corrupted ciphertext (e.g. key rotation). Treat as denial to avoid
        # leaking storage state. The dashboard simply tells the seller to
        # re-issue the asset.
        return HttpResponseForbidden(
            json.dumps(FORBIDDEN_PAYLOAD),
            content_type='application/json',
        )

    return JsonResponse({"fields": plaintext_fields})