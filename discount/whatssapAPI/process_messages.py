
import json
import os
import logging
from decimal import Decimal
import random
import threading
import time
from django.conf import settings
from django.http import HttpResponse, JsonResponse
import requests
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_GET, require_POST
from discount.whatssapAPI.views import download_whatsapp_media
from django.core.files.base import ContentFile

# إعداد logging
logger = logging.getLogger(__name__)

 
VERIFY_TOKEN = getattr(settings, 'VERIFY_TOKEN', "token")


ACCESS_TOKEN = getattr(settings, 'ACCESS_TOKEN', "EAALZBubBgmq0BP7ECHmEACY6YMB8nsV8MtxTQKwSexB3RqW9ZB3EkRdDp7MQnjuqCJHQ598lkQ9CQQmXTd2jZAI8NhGKyMLATmJgXbZAWKprwErSjANdMsTtduBBvqURZApEWlAqcYsgckaTLcWgYUHmzfFanu0oZANZC3H5zSj2fGjKZCm4oTTRpsjGbXy7zNwRbQZDZD")
# ------------ test number --------------- 
PHONE_NUMBER_ID = getattr(settings, 'PHONE_NUMBER_ID', "866281303235440")
import datetime as _dt
 
import re

from datetime import timedelta

from discount.models import CustomUser, Flow, Message, Contact, WhatsAppChannel, Node, NodeMedia, ChatSession, SimpleOrder, Products, ProductImage
from django.utils import timezone
from ..channel.socket_utils import send_socket

SESSION_TIMEOUT_HOURS = 24

# Parse [SEND_MEDIA: <id>] from AI reply; return (cleaned_text, list of media ids)
SEND_MEDIA_RE = re.compile(r"\[SEND_MEDIA:\s*(\d+)\]")
# Parse [SEND_PRODUCT_IMAGE] from AI reply; return (cleaned_text, True if tag present)
SEND_PRODUCT_IMAGE_RE = re.compile(r"\[SEND_PRODUCT_IMAGE\]", re.IGNORECASE)

# Phrases that mean "use the phone number from this chat"
_SAME_NUMBER_PATTERN = re.compile(
    r"^(same\s*number|this\s*number|the\s*chat\s*number|نفس\s*الرقم|هذا\s*الرقم|رقم\s*الواتساب|رقم\s*الشات|chat\s*number|same\s*as\s*chat|as\s*above)$",
    re.IGNORECASE,
)


def normalize_customer_phone_for_order(phone_value, chat_sender):
    """
    When the customer said the phone is 'the same as in the chat', use the chat sender.
    Returns chat_sender if phone_value is empty or indicates 'same number'; otherwise returns stripped phone_value.
    """
    if not chat_sender:
        return (phone_value or "").strip() or None
    raw = (phone_value or "").strip()
    if not raw:
        return chat_sender
    if _SAME_NUMBER_PATTERN.match(raw):
        return chat_sender
    # Allow numeric-only (with optional +) as valid phone
    if re.match(r"^[\d\s\+\-]+$", raw) and len(re.sub(r"\D", "", raw)) >= 8:
        return raw
    # If it looks like a phrase rather than a number, treat as "same number"
    if len(raw) < 6 or not re.search(r"\d{5,}", raw):
        return chat_sender
    return raw


def parse_and_strip_send_media(text):
    if not text or not isinstance(text, str):
        return (text or "", [])
    ids = []
    for m in SEND_MEDIA_RE.finditer(text):
        try:
            ids.append(int(m.group(1)))
        except (ValueError, IndexError):
            pass
    cleaned = SEND_MEDIA_RE.sub("", text).strip()
    cleaned = re.sub(r"\n\s*\n", "\n\n", cleaned)
    return (cleaned, ids)


def parse_and_strip_send_product_image(text):
    if not text or not isinstance(text, str):
        return (text or "", False)
    present = bool(SEND_PRODUCT_IMAGE_RE.search(text))
    cleaned = SEND_PRODUCT_IMAGE_RE.sub("", text).strip()
    cleaned = re.sub(r"\n\s*\n", "\n\n", cleaned)
    return (cleaned, present)


def format_order_confirmation(order):
    """Build the one-time order confirmation message shown to the customer after order creation."""
    if not order:
        return None
    product_name = (getattr(order, "product_name", None) or "").strip() or "—"
    qty = getattr(order, "quantity", 1)
    try:
        qty = int(Decimal(str(qty)))
    except Exception:
        qty = 1
    price = getattr(order, "price", None)
    try:
        price_val = float(Decimal(str(price))) if price is not None else 0
    except Exception:
        price_val = 0
    line_total = price_val * qty
    total = getattr(order, "price", None)
    try:
        total_val = float(Decimal(str(total)) * Decimal(str(qty))) if total is not None else line_total
    except Exception:
        total_val = line_total
    phone = (getattr(order, "customer_phone", None) or "").strip() or "—"
    name = (getattr(order, "customer_name", None) or "").strip() or "—"
    city = (getattr(order, "customer_city", None) or "").strip() or "—"
    address = city  # SimpleOrder has only customer_city; use as address
    return (
        f"✅ Order Confirmed!\n"
        f"Items: {product_name} x {qty} = {line_total:.0f} MAD\n"
        f"Total: {total_val:.0f} MAD\n"
        f"Information:\n"
        f"📞 Phone Number: {phone}\n"
        f"👤 Name: {name}\n"
        f"🏙️ City: {city}\n"
        f"🏠 Address: {address}\n"
        f"سوف نتواصل معك قريبا لتسليم الطلب. 🚚"
    )





# def send_socket(status, payload , group_name = "webhook_events", channel_name =None):
#         layer = get_channel_layer()
#         event = {
#             "type": "wh_event",  
#             "status": status,
#             "payload": payload,
#             # "sender": sreciver
#         }
#         try:
#             if channel_name:
#                 async_to_sync(layer.send)(channel_name, event)
#             else:
#                 async_to_sync(layer.group_send)(group_name, event)
#         except Exception as e:
#             print("Failed to send socket event:", e)










# -----------upload midua --------------------
def upload_to_whatsapp_media(media_url, channel=None, user=None, media_type="image"):
    """
    رفع الصورة أو الفيديو إلى واتساب API وإرجاع media_id
    
    Args:
        media_url: رابط الوسائط
        channel: القناة (اختياري) - إذا لم تُحدد، يستخدم الإعدادات العامة
        user: المستخدم (اختياري) - للتحقق من الصلاحيات
        media_type: نوع الوسائط (image, video, audio, document)
    
    Returns:
        media_id أو None في حالة الفشل
    """
    try:
        if not media_url:
            print("❌ No media URL provided to upload")
            return None

        # تحديد access_token و phone_number_id
        access_token = ACCESS_TOKEN
        phone_number_id = PHONE_NUMBER_ID
        
        if channel:
            # التحقق من الصلاحيات إذا كان user موجود
            if user:
                has_permission, error = check_user_channel_permission(user, channel)
                if not has_permission:
                    print(f"❌ Permission denied: {error}")
                    return None
            
            # استخدام بيانات القناة
            if channel.access_token:
                access_token = channel.access_token
            if channel.phone_number_id:
                phone_number_id = channel.phone_number_id

        endpoint = f"https://graph.facebook.com/v17.0/{phone_number_id}/media"

        response = requests.post(
            endpoint,
            data={
                "messaging_product": "whatsapp",
                "type": media_type,
                "url": media_url
            },
            headers={
                "Authorization": f"Bearer {access_token}"
            },
            timeout=30
        )

        result = response.json()

        print("📥 WhatsApp media upload response:", result)

        return result.get("id")  # هذا هو media_id

    except Exception as e:
        print(f"❌ upload_to_whatsapp_media error: {e}")
        import traceback
        traceback.print_exc()
        return None






        # ------------------- send Automations -----------------



def send_automated_response(recipient, responses, channel=None, user=None):
            """
            إرسال ردود آلية متعددة (نصوص + صور + فيديو + وثائق + صوت)
            بدون رفع وسائط، فقط باستخدام الرابط المباشر.
            
            Args:
                recipient: رقم المستلم
                responses: قائمة الردود
                channel: القناة (اختياري) - للتحقق من الصلاحيات واستخدام access_token الخاص بها
                user: المستخدم (اختياري) - للتحقق من الصلاحيات
            """
            import time
            import requests

            try:
                if not responses:
                    print("لا توجد ردود للإرسال")
                    return False

                if not isinstance(responses, list):
                    responses = [responses]

                # تحديد access_token و phone_number_id
                access_token = ACCESS_TOKEN
                phone_number_id = PHONE_NUMBER_ID
                
                if channel:
                    # التحقق من الصلاحيات إذا كان user موجود
                    if user:
                        has_permission, error = check_user_channel_permission(user, channel)
                        if not has_permission:
                            print(f"❌ Permission denied: {error}")
                            return False
                    
                    # استخدام بيانات القناة
                    if channel.access_token:
                        access_token = channel.access_token
                    if channel.phone_number_id:
                        phone_number_id = channel.phone_number_id

                headers = {
                    'Authorization': f'Bearer {access_token}',
                    'Content-Type': 'application/json'
                }

                for i, item in enumerate(responses):

                    msg_type = item.get("type")

                    # تعامل مع التأخير (نوع delay)
                    if msg_type == "delay":
                        duration = item.get("duration", 0)
                        print(f"⏳ Delay {duration} sec")
                        time.sleep(duration)
                        continue

                    # تأخير داخل كل رسالة
                    delay = item.get("delay", 0)
                    if delay > 0:
                        print(f"⏳ Internal delay {delay} sec")
                        time.sleep(delay)

                    # ------------------------
                    # نص message
                    # ------------------------
                    if msg_type == "text":
                        text = item.get("content", "")
                        if not text:
                            print("❌ نص فارغ")
                            continue

                        data = {
                            "messaging_product": "whatsapp",
                            "to": recipient,
                            "type": "text",
                            "text": {"body": text}
                        }
                         

                    # ------------------------
                    # وسائط image / video / audio / document
                    # ------------------------
                    elif msg_type in ["image", "video", "audio", "document"]:
                        media_url = item.get("media_url")

                        if not media_url:
                            print("❌ media_url مفقود")
                            continue

                        data = {
                            "messaging_product": "whatsapp",
                            "to": recipient,
                            "type": msg_type,
                            msg_type: {
                                "link": media_url
                            }
                        }

                        caption = item.get("content", "").strip()
                        if caption:
                            data[msg_type]["caption"] = caption

                    else:
                        print(f"❌ نوع غير معروف: {msg_type}")
                        continue

                    # ------------------------
                    # إرسال الرسالة
                    # ------------------------
                    print(f"🚀 Sending message {i+1} ({msg_type}) ...")
                    res = requests.post(
                        f"https://graph.facebook.com/v17.0/{phone_number_id}/messages",
                        headers=headers,
                        json=data
                    )

                    print("📥 WhatsApp Response:", res.status_code, res.text)
                    print("👌 data send " , data)

                    if res.status_code != 200:
                        print(f"❌ Failed message {i+1}")
                        # Fallback: if media failed, send text description when available
                        fallback_caption = item.get("fallback_caption") or item.get("content", "").strip()
                        if fallback_caption and msg_type in ["image", "video"]:
                            fallback_data = {
                                "messaging_product": "whatsapp",
                                "to": recipient,
                                "type": "text",
                                "text": {"body": fallback_caption}
                            }
                            res_fb = requests.post(
                                f"https://graph.facebook.com/v17.0/{phone_number_id}/messages",
                                headers=headers,
                                json=fallback_data
                            )
                            if res_fb.status_code == 200:
                                print(f"✅ Sent fallback text for failed media")
                    else:
                        # حفظ الرسالة المرسلة في قاعدة البيانات
                        try:
                            body = item.get("content", "")
                            media_url = item.get("media_url")
                            media_id = item.get("media_id" , None)
                            
                            savedmsg = Message.objects.create(
                                channel=channel if channel else None,
                                sender=recipient,
                                body=body,
                                is_from_me=True,
                                media_type=msg_type if msg_type in ["image", "video", "audio", "document"] else None,
                                media_id= media_id,
                                media_url = media_url , 
                                message_id= res.json().get("messages", [{}])[0].get("id") ,
                                type = msg_type , 
                                 
                            )
                            snippet = body or ""
                            if msg_type == 'image': snippet = 'image'
                            elif msg_type == 'video': snippet = 'vedio'
                            elif msg_type == 'audio': snippet = 'audio'
                        #     payload ={
                        #         'sender':recipient,
                        #         'body': body,
                        #         'is_from_me':True,
                        #         'media_type':msg_type if msg_type in ["image", "video", "audio", "document"] else None,
                        #         'media_id': media_id,
                        #         'media_url' : media_url , 
                        #         'message_id': res.json().get("messages", [{}])[0].get("id"),
                        #         'contact':{
                        #         'phone':recipient,}
                        #    }   
                            final_payload = {
                                "status": res.status_code,
                                "whatsapp_response": res.text if hasattr(res, "text") else str(res),
                                "saved_message_id": savedmsg.id,
                                "media_id": media_id,
                                "body": body,
                                "to": recipient,
                                "media_type":msg_type if msg_type in ["image", "video", "audio", "document"] else None,
                                "url": media_url,  # ✅ أضفنا الرابط هنا لكي يعرضه المتصفح
                                "media_url": media_url # ✅ نسخة احتياطية حسب تسمية الجافاسكربت لديك
                            }
                            sidebar_payload = {
                                "phone": recipient, 
                                "name": recipient,  # سيتم تحسينه في الفرونت إند إذا كان الاسم موجوداً
                                "snippet": snippet,
                                "timestamp": timezone.now().strftime("%H:%M"),
                                "unread": 0,       # 0 لأننا نحن المرسلون
                                "last_status": "sent",
                                "fromMe": True,    # ضروري لظهور أيقونة الصح
                                "channel_id": channel.id if channel else None,
                                 
                            }     
                            team_id = channel.owner.id 

                            dynamic_group_name = f"team_updates_{team_id}"

                            # send_socket(
                            #     data_type='new_message_received',
                            # payload = payload ,
                            # group_name =  dynamic_group_name
                            #                     )

                            send_socket("finished",final_payload , group_name= dynamic_group_name)
                            send_socket("update_sidebar_contact", sidebar_payload , group_name =dynamic_group_name)


                                                
                            # send_socket("new_contact" ,payload)
                             
                            print(f"✅ Message saved to database")
                        except Exception as e:
                            print(f"⚠️ Error saving message: {e}")
                        
                        print(f"✅ Sent message {i+1}")

                    time.sleep(1)  # pause

                return True

            except Exception as e:
                print("❌ Error in send_automated_response:", e)
                return False












# ------------------web hook validate ----------------

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











# _----------- media thing-------------
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
















# ---------------------Save sms----------------

def save_incoming_message(msg, message_type, sender=None, channel=None, name=None, body_override=None):
    """
    Save incoming WhatsApp message. If body_override is provided (e.g. transcription or vision description), use it as body.
    """
    try:
        if not sender:
            sender = msg.get("from")
        
        # 1. استخراج النص الأساسي (الافتراضي)
        body = msg.get("text", {}).get("body", "")
        
        message_id = msg.get("id")
        timestamp = msg.get("timestamp")
        
        # 2. معالجة الردود عن طريق الأزرار (Buttons & Interactive)
        # النوع الأول: زر من قالب (Template Button)
        if message_type == 'button':
            body = msg.get('button', {}).get('text')
            
        # النوع الثاني: زر تفاعلي (Interactive Message - List or Button)
        elif message_type == 'interactive':
            interactive_obj = msg.get('interactive', {})
            interactive_type = interactive_obj.get('type')
            
            if interactive_type == 'button_reply':
                body = interactive_obj.get('button_reply', {}).get('title')
            elif interactive_type == 'list_reply':
                body = interactive_obj.get('list_reply', {}).get('title')

        # 3. معالجة الإحالات (Referrals - Click to WhatsApp Ads)
        # الإحالة تأتي ككائن داخل الرسالة بغض النظر عن نوعها (نص، صورة، إلخ)
        referral_body = ""
        if 'referral' in msg:
            referral_data = msg['referral']
            headline = referral_data.get('headline', 'Ad')
            source_url = referral_data.get('source_url', '')
            # نقوم بتجهيز نص يوضح أن العميل قادم من إعلان
            referral_body = f"\n[Coming from Ad: {headline}]"
            
            # إذا لم يكن هناك نص (مجرد نقرة على الإعلان)، نجعله هو الـ body
            if not body:
                body = f"Hello (from Ad: {headline})"
            
        # إضافة معلومات الإعلان للنص الأصلي إذا وجد
        if referral_body:
            body = f"{body} {referral_body}"

        # 4. معالجة الوسائط
        media_type = None
        media_id = None
        
        # التحقق من أنواع الميديا المختلفة (بما في ذلك الملصقات)
        for media_key in ['image', 'audio', 'video', 'document', 'sticker', 'voice']:
            if media_key in msg:
                media_type = media_key
                # أحياناً يكون النوع voice ولكن نريد حفظه كـ audio
                if media_type == 'voice': 
                    media_type = 'audio'
                    
                media_data = msg[media_key]
                media_id = media_data.get('id')
                
                # التقاط الـ Caption للصورة أو الفيديو إذا وجد وجعله هو الـ Body
                if 'caption' in media_data:
                    caption_text = media_data.get('caption')
                    if caption_text:
                        body = caption_text  # نجعل الكابشن هو نص الرسالة
                break
        if body_override is not None:
            body = body_override
                
        # 5. معالجة التوقيت (Timestamp)
        parsed_timestamp = None
        try:
            import datetime as _dt
            if timestamp is not None:
                if isinstance(timestamp, (int, float)) or (isinstance(timestamp, str) and re.fullmatch(r'\d+', timestamp)):
                    parsed_timestamp = _dt.datetime.fromtimestamp(int(timestamp), tz=_dt.timezone.utc)
                else:
                    try:
                        parsed_timestamp = _dt.datetime.fromisoformat(timestamp)
                        if parsed_timestamp.tzinfo is None:
                            parsed_timestamp = timezone.make_aware(parsed_timestamp, timezone.get_current_timezone())
                    except Exception:
                        parsed_timestamp = None
        except Exception:
            parsed_timestamp = None

        # 6. معالجة الموقع الجغرافي
        if message_type == 'location':
            loc = msg.get('location', {})
            latitude = loc.get('latitude')
            longitude = loc.get('longitude')
            # حفظ الإحداثيات كنص
            body = f"{latitude},{longitude}"

        # 7. الحفظ في قاعدة البيانات
        # تأكد من أن المودل Message لديك يحتوي على حقل لحفظ 'captions' إذا أردت فصله، أو استخدم body
        message_obj = Message.objects.create(
            channel=channel if channel else None,
            sender=sender,
            body=body, # سيحتوي الآن على نص الزر، أو الكابشن، أو نص الإعلان
            type=message_type, # سيحفظ 'button' أو 'interactive' أو 'image' إلخ
            is_from_me=False,
            media_type=media_type,
            media_id=media_id,
            message_id=message_id,
            timestamp=parsed_timestamp,
            media_url=media_id, # يمكن تعديل هذا لاحقاً بالرابط الحقيقي بعد التحميل
        )

        # 8. تحميل وحفظ ملف الميديا
        access_token_to_use = None
        if channel and channel.access_token:
            access_token_to_use = channel.access_token
        elif ACCESS_TOKEN: # تأكد أن هذا المتغير معرف في scope الملف
            access_token_to_use = ACCESS_TOKEN
            
        if media_id and access_token_to_use:
            # دالة التحميل الخاصة بك
            media_content = download_whatsapp_media(media_id, access_token_to_use)
            if media_content:
                filename = f"{media_id}_{media_type}.{get_media_extension(media_type)}"
                # حفظ الملف في حقل media_file
                message_obj.media_file.save(filename, ContentFile(media_content))
                # تحديث رابط الميديا ليكون الرابط الداخلي بدلاً من ID واتساب
                message_obj.media_url = message_obj.media_file.url 
                message_obj.save()
                
        # return message_obj

    




# 1. تجهيز بيانات الرسالة (للعرض داخل الشات)
        msg_payload = {
            "id": message_obj.id,
            "body": message_obj.body,
            "type": message_obj.media_type,
            "url": message_obj.media_file.url if message_obj.media_file else None, # تأكد من الرابط
            "time": message_obj.created_at.strftime("%H:%M"),
            "status": "received",
            "fromMe": False ,
            "channel_id": channel.id if channel else None, # هام للفرونت إند - مع التحقق من None
        }

        # 2. تجهيز بيانات جهة الاتصال (للقائمة الجانبية)
        snippet = ''
        if message_obj.media_type == 'audio': snippet = '[صوت]'
        elif message_obj.media_type == 'image': snippet = '[صورة]'
        elif message_obj.media_type == 'video': snippet = '[فيديو]'
        else: snippet = message_obj.body[:80] if message_obj.body else ''

        unread_count = Message.objects.filter(sender=message_obj.sender, is_read=False, channel=channel).count() if channel else Message.objects.filter(sender=message_obj.sender, is_read=False).count()

        contact_payload = {
            "channel_id": channel.id if channel else None, # هام للفرونت إند - مع التحقق من None
            "phone": message_obj.sender,
            "name": name if name else message_obj.sender, # أو الاسم المخزن في جدول Contact
            "snippet": snippet,
            "unread": unread_count,
            "last_id": message_obj.id,
            "timestamp": message_obj.created_at.strftime("%H:%M") 
        }

        # 3. إرسال باكيج موحد يحتوي على الاثنين
        full_payload = {
            "contact": contact_payload,
            "message": msg_payload
        }
        team_id = channel.owner.id 
        dynamic_group_name = f"team_updates_{team_id}"

        send_socket(
            data_type="new_message_received", # اسم نوع جديد وواضح
            payload=full_payload ,
            group_name = dynamic_group_name
        )

        return message_obj


        
    except Exception as e:
        print(f"❌ Error saving message: {e}")
        return None



















def get_matching_flow(sender_phone: str, message_text: str, channel=None):
    """
    البحث عن الفلو المناسب بناءً على:
    1. هل هذه بداية محادثة جديدة؟ (Conversation Start)
    2. هل النص يطابق أي كلمات مفتاحية؟ (Keyword Match)
    
    Args:
        sender_phone: رقم المرسل
        message_text: نص الرسالة
        channel: القناة (اختياري) - للبحث في الرسائل الخاصة بالقناة فقط
    """
    
    # 1. التحقق من حالة "بداية المحادثة"
    # نتحقق مما إذا كان هناك رسائل سابقة من هذا الرقم خلال فترة معينة (مثلاً 24 ساعة)
    # إذا لم نجد، فهذه "بداية محادثة"
    msg_filter = Message.objects.filter(sender=sender_phone)
    if channel:
        msg_filter = msg_filter.filter(channel=channel)
    
    last_msg = msg_filter.order_by('-timestamp').first()
    
    # نعتبرها محادثة جديدة إذا لم تكن هناك رسائل أبداً، أو آخر رسالة كانت قبل 24 ساعة
    is_new_conversation = False
    if not last_msg:
        is_new_conversation = True
    else:
        if timezone.now() - last_msg.timestamp > timedelta(hours=24):
            is_new_conversation = True

    flows = Flow.objects.filter(active=True)
    if channel:
        flows = flows.filter(channel=channel)

    # الأولوية 1: البحث عن فلو "بداية المحادثة" إذا انطبق الشرط
    if is_new_conversation:
        start_flow = flows.filter(trigger_on_start=True).first()
        if start_flow:
            print(f"🎯 Found Conversation Start Flow: {start_flow.name}")
            return start_flow

    # الأولوية 2: البحث عن الكلمات المفتاحية في النص
    if message_text:
        for flow in flows:
            # نتجاوز فلو البداية هنا لأننا فحصناه، إلا إذا كان له كلمات مفتاحية أيضاً
            if flow.trigger_on_start and not flow.trigger_keywords:
                continue
                
            if flow.match_trigger(message_text):
                print(f"🎯 Found Keyword Match Flow: {flow.name}")
                return flow
    
    return None


def get_flow_first_ai_agent_node(flow):
    """Return the first ai-agent node in the flow (after trigger), or None. Uses select_related for connections."""
    if not flow or not flow.start_node:
        return None
    connections = flow.connections.all().select_related("to_node")
    current = flow.start_node
    if current.node_type == "trigger":
        conn = connections.filter(from_node=current).first()
        if not conn:
            return None
        current = conn.to_node
    visited = set()
    while current and current.id not in visited:
        visited.add(current.id)
        if current.node_type == "ai-agent":
            return current
        conn = connections.filter(from_node=current).first()
        if not conn:
            break
        current = conn.to_node
    return None


# Catalog: when customer asks for available products, we list them; when they choose one, we activate that product's node
CATALOG_CACHE_PREFIX = "catalog_pending:"
CATALOG_CACHE_TTL = 3600  # 1 hour

# Keywords/phrases that indicate "asking for available products" (EN/AR/FR)
_CATALOG_INTENT_PATTERNS = re.compile(
    r"\b(what\s*(do\s*you\s*)?(have|sell|offer)|available\s*products?|product\s*list|show\s*(me\s*)?(your\s*)?products?|"
    r"catalog|list\s*(of\s*)?products?|what\s*can\s*i\s*buy|do\s*you\s*have\s*products?|"
    r"عرض\s*المنتجات|المنتجات\s*المتوفرة|ماذا\s*تبيع|وش\s*عندك|واش\s*عندك|شنو\s*عندك|"
    r"quels?\s*produits|liste\s*des\s*produits|produits\s*disponibles|qu['\u2019]est-ce\s*que\s*vous\s*avez)\b",
    re.IGNORECASE,
)


def get_channel_products_with_nodes(channel):
    """
    Return list of products for this channel that have an AI-agent node in some flow.
    Each item: {"product_id": int, "name": str, "node_id": int, "node": Node}.
    """
    if not channel:
        return []
    owner_id = getattr(channel, "owner_id", None) or (getattr(channel, "owner", None) and getattr(channel.owner, "id", None))
    if not owner_id:
        return []
    seen_product_ids = set()
    result = []
    try:
        nodes = Node.objects.filter(
            flow__channel=channel,
            flow__active=True,
            node_type="ai-agent",
        ).select_related("flow")
        for node in nodes:
            ac = getattr(node, "ai_model_config", None) or {}
            pid = ac.get("product_id") if isinstance(ac, dict) else None
            if pid is None:
                continue
            try:
                pid = int(pid)
            except (TypeError, ValueError):
                continue
            if pid in seen_product_ids:
                continue
            seen_product_ids.add(pid)
            product = Products.objects.filter(id=pid, admin_id=owner_id).first()
            if not product:
                continue
            name = (getattr(product, "name", None) or "").strip() or f"Product {pid}"
            result.append({
                "product_id": pid,
                "name": name,
                "node_id": node.id,
                "node": node,
            })
    except Exception as e:
        logger.warning("get_channel_products_with_nodes: %s", e)
    return result


def _is_catalog_intent(message_text):
    """True if the message is asking for available products / catalog."""
    if not message_text or not isinstance(message_text, str):
        return False
    text = message_text.strip()
    if len(text) < 2:
        return False
    return bool(_CATALOG_INTENT_PATTERNS.search(text))


def _get_catalog_pending(channel, sender):
    """Return catalog pending data for (channel, sender) or None."""
    if not channel or not sender:
        return None
    try:
        from django.core.cache import cache
        key = f"{CATALOG_CACHE_PREFIX}{channel.id}:{sender}"
        return cache.get(key)
    except Exception:
        return None


def _set_catalog_pending(channel, sender, products_list):
    """Store catalog state so next message can resolve product choice. products_list: list of {product_id, name, node_id}."""
    if not channel or not sender:
        return
    try:
        from django.core.cache import cache
        key = f"{CATALOG_CACHE_PREFIX}{channel.id}:{sender}"
        cache.set(key, {"products": products_list}, timeout=CATALOG_CACHE_TTL)
    except Exception as e:
        logger.warning("_set_catalog_pending: %s", e)


def _clear_catalog_pending(channel, sender):
    if not channel or not sender:
        return
    try:
        from django.core.cache import cache
        key = f"{CATALOG_CACHE_PREFIX}{channel.id}:{sender}"
        cache.delete(key)
    except Exception:
        pass


def _resolve_product_choice(message_text, catalog_products):
    """
    If message_text indicates a choice from catalog_products, return (node_id, product_name).
    catalog_products: list of {product_id, name, node_id, node?}. node is optional (e.g. from cache we only have node_id).
    Matching: by number (1, first, 2, second), or by product name (substring).
    """
    if not message_text or not catalog_products:
        return None
    text = (message_text or "").strip().lower()
    if not text:
        return None
    node_id = None
    product_name = None
    # By index: "1", "first", "2", "second", "number 3", "الاول", "الثاني", etc.
    index_phrases = [
        (r"^(1|first|1st|one|numero\s*1|رقم\s*1|الاول|الأول|اول)$", 0),
        (r"^(2|second|2nd|two|numero\s*2|رقم\s*2|الثاني|الثانية|ثاني)$", 1),
        (r"^(3|third|3rd|three|numero\s*3|رقم\s*3|الثالث|ثالث)$", 2),
        (r"^(4|fourth|4th|رقم\s*4|الرابع)$", 3),
        (r"^(5|fifth|5th|رقم\s*5|الخامس)$", 4),
    ]
    for pattern, idx in index_phrases:
        if re.match(pattern, text, re.IGNORECASE) and idx < len(catalog_products):
            item = catalog_products[idx]
            node_id = item.get("node_id")
            if node_id is not None:
                product_name = item.get("name") or f"Product {item.get('product_id')}"
                return (node_id, product_name)
    # By product name (substring match)
    for item in catalog_products:
        name = (item.get("name") or "").strip().lower()
        if not name:
            continue
        if name in text or text in name:
            node_id = item.get("node_id")
            if node_id is not None:
                product_name = item.get("name") or f"Product {item.get('product_id')}"
                return (node_id, product_name)
        if re.search(r"(want|need|give\s*me|the)\s+.+", text) or "one" in text:
            if name in text or any(word in text for word in name.split() if len(word) > 2):
                node_id = item.get("node_id")
                if node_id is not None:
                    product_name = item.get("name") or f"Product {item.get('product_id')}"
                    return (node_id, product_name)
    return None


def _send_catalog_reply(sender, catalog_products, channel):
    """Build and send the list of product names to the customer."""
    if not catalog_products:
        return
    lines = []
    for i, item in enumerate(catalog_products, 1):
        name = item.get("name") or f"Product {item.get('product_id')}"
        lines.append(f"{i}. {name}")
    intro = "Here are our available products. Reply with the number or name of the product you're interested in:\n\n"
    body = intro + "\n".join(lines)
    send_automated_response(sender, [{"type": "text", "content": body, "delay": 0}], channel=channel)


def update_chat_session_on_trigger(channel, customer_phone, active_node):
    """On new trigger match: set or update ChatSession to this product (active_node)."""
    if not channel or not customer_phone or not active_node:
        return
    try:
        ChatSession.objects.update_or_create(
            channel=channel,
            customer_phone=customer_phone,
            defaults={
                "active_node": active_node,
                "is_expired": False,
                "last_interaction": timezone.now(),
            },
        )
    except Exception as e:
        logger.warning("update_chat_session_on_trigger: %s", e)


def get_active_session(channel, customer_phone):
    """Return active ChatSession for (channel, customer_phone) if not expired and within 24h. Uses select_related('active_node')."""
    if not channel or not customer_phone:
        return None
    cutoff = timezone.now() - timedelta(hours=SESSION_TIMEOUT_HOURS)
    return (
        ChatSession.objects.filter(
            channel=channel,
            customer_phone=customer_phone,
            is_expired=False,
            last_interaction__gte=cutoff,
        )
        .select_related("active_node")
        .first()
    )


def expire_chat_session(channel, customer_phone):
    """Mark session as expired (e.g. after successful order)."""
    if not channel or not customer_phone:
        return
    try:
        ChatSession.objects.filter(channel=channel, customer_phone=customer_phone).update(is_expired=True)
    except Exception as e:
        logger.warning("expire_chat_session: %s", e)


def _touch_session_last_interaction(channel, customer_phone):
    """Update last_interaction so session stays active for 24h after each response."""
    if not channel or not customer_phone:
        return
    try:
        ChatSession.objects.filter(
            channel=channel,
            customer_phone=customer_phone,
            is_expired=False,
        ).update(last_interaction=timezone.now())
    except Exception as e:
        logger.warning("_touch_session_last_interaction: %s", e)


def _voice_settings_for_node(channel, node):
    """
    Return a wrapper so generate_voice uses node's persona (voice_id) or node_voice_id,
    and node's voice_stability, voice_similarity, voice_speed when set; otherwise channel.
    """
    if not node:
        return channel

    class _NodeVoiceOverride:
        def __init__(self, _channel, _node):
            self._channel = _channel
            self._node = _node

        def __getattr__(self, name):
            if self._node:
                if name == "voice_gender":
                    v = getattr(self._node, "node_gender", None)
                    if v and (v or "").strip():
                        return (v or "").strip().upper()
                if name == "selected_voice_id":
                    try:
                        persona = getattr(self._node, "persona", None)
                        if persona and getattr(persona, "voice_id", None):
                            return (persona.voice_id or "").strip()
                    except Exception:
                        pass
                    v = getattr(self._node, "node_voice_id", None)
                    if v and (v or "").strip():
                        return (v or "").strip()
                if name == "voice_stability":
                    v = getattr(self._node, "voice_stability", None)
                    if v is not None:
                        return float(v)
                if name == "voice_similarity":
                    v = getattr(self._node, "voice_similarity", None)
                    if v is not None:
                        return float(v)
                if name == "voice_speed":
                    v = getattr(self._node, "voice_speed", None)
                    if v is not None:
                        return float(v)
                if name in ("voice_provider", "ai_voice_provider"):
                    try:
                        persona = getattr(self._node, "persona", None)
                        if persona and getattr(persona, "provider", None):
                            return (persona.provider or "").strip().upper()
                    except Exception:
                        pass
            return getattr(self._channel, name)

    return _NodeVoiceOverride(channel, node)


def _conversation_already_has_order_confirmation(conversation_messages):
    """True if any previous agent message indicates the order was already confirmed (so we must not repeat confirmation)."""
    if not conversation_messages:
        return False
    order_confirm_phrases = (
        "تم تسجيل طلبك",
        "طلبك تم تسجيله",
        "order is registered",
        "your order is confirmed",
        "سنتواصل معك قريباً",
    )
    for m in conversation_messages:
        if m.get("role") != "agent":
            continue
        body = (m.get("body") or "").strip().lower()
        for phrase in order_confirm_phrases:
            if phrase.lower() in body:
                return True
    return False


# Phrases that mean "asking the customer to place/confirm order" — we allow only once per session
_ORDER_ASK_PATTERN = re.compile(
    r"(نبدأو\s*ف?ي?\s*إجراءات\s*الطلب|واش\s*نبدأو|نأكد\s*ليك\s*الطلب|"
    r"نخلي\s*ليك\s*حبة\s*محجوزة|واش\s*نبغاو\s*نحجزو|"
    r"shall\s*we\s*start\s*the\s*order|do\s*you\s*want\s*to\s*order|"
    r"place\s*your\s*order|confirm\s*your\s*order|prepare\s*your\s*(shipment|order)|"
    r"ready\s*to\s*order|start\s*the\s*order)",
    re.IGNORECASE,
)


def _reply_is_order_ask(text):
    """True if the reply is asking the customer to place/confirm the order (we enforce at most one such ask per session)."""
    if not text or not isinstance(text, str):
        return False
    return bool(_ORDER_ASK_PATTERN.search(text))


def _strip_order_ask_from_reply(reply_text):
    """Remove sentences that are an order ask; return cleaned text or a short fallback."""
    if not reply_text or not _reply_is_order_ask(reply_text):
        return reply_text
    # Split on sentence boundaries and drop segments that look like an order ask
    parts = re.split(r"([.!؟?]\s*)", reply_text)
    kept = []
    buf = ""
    for i, p in enumerate(parts):
        buf += p
        if re.search(r"[.!؟?]\s*$", buf) or (i == len(parts) - 1 and buf.strip()):
            if buf.strip() and not _reply_is_order_ask(buf):
                kept.append(buf)
            buf = ""
    cleaned = ("".join(kept) or "").strip()
    if not cleaned:
        cleaned = (
            "إذا عندك أي سؤال آخر على المنتج أو الجودة أو التوصيل، سُولني براحتك. "
            "(If you have any other questions about the product, quality, or delivery, ask anytime.)"
        )
    return cleaned


def _build_state_header_from_product_context(product_context, sales_stage=None, sentiment=None):
    """Build 'CURRENT STATE' line for GPT from product_context (product name, price), optional sales_stage and sentiment."""
    parts = []
    if product_context and isinstance(product_context, str):
        text = product_context.strip()
        if text:
            name = ""
            price = ""
            for line in text.split("\n"):
                line = line.strip()
                if not line:
                    continue
                if line.lower().startswith("product name"):
                    name = line.split(":", 1)[-1].strip() or "this product"
                elif line.lower().startswith("prices"):
                    price = line.split(":", 1)[-1].strip() or "see above"
            product_name = name or "this product"
            current_price = price or "see product details"
            parts.append(
                f"You are in the middle of a sale for {product_name}. Current Price: {current_price}. Do not re-introduce yourself."
            )
    if sales_stage:
        parts.append(f"Current goal stage: {sales_stage}. Follow this stage and output [STAGE: ...] at the end of your reply.")
    if sentiment == "in_hurry":
        parts.append("Customer is in a hurry: keep replies very short and direct.")
    if not parts:
        return None
    return "CURRENT STATE: " + " ".join(parts) + " Respond to the customer's last message as a continuation of this sale."


# --- Sentiment: detect "in a hurry" from recent customer messages ---
IN_HURRY_KEYWORDS = re.compile(
    r"\b(quick|fast|urgent|عجل|بسرعة|فورا|rapide|vite|urgence)\b",
    re.IGNORECASE,
)
MAX_AVG_WORDS_FOR_HURRY = 5


def _infer_sentiment_from_conversation(conversation_messages, last_n=5):
    """Infer sentiment from last_n customer messages. Returns 'in_hurry' or None."""
    if not conversation_messages:
        return None
    customer_bodies = [
        (m.get("body") or "").strip()
        for m in conversation_messages[-last_n:]
        if m.get("role") == "customer"
    ]
    if not customer_bodies:
        return None
    for body in customer_bodies:
        if body and IN_HURRY_KEYWORDS.search(body):
            return "in_hurry"
    word_counts = [len(b.split()) for b in customer_bodies if b]
    if word_counts and sum(word_counts) / len(word_counts) <= MAX_AVG_WORDS_FOR_HURRY and len(customer_bodies) >= 2:
        return "in_hurry"
    return None


def _execute_check_stock(channel, product_id=None, sku=None):
    """Check product stock for the channel's store. Returns a short message for the agent."""
    from discount.models import Products
    if not channel:
        return "Channel not available. Cannot check stock."
    owner = getattr(channel, "owner", None)
    if not owner:
        return "Store not configured. Cannot check stock."
    try:
        qs = Products.objects.filter(admin=owner)
        if product_id is not None:
            qs = qs.filter(id=int(product_id))
        elif sku and str(sku).strip():
            qs = qs.filter(sku=str(sku).strip())
        else:
            return "Please specify product_id or sku to check stock."
        product = qs.first()
        if not product:
            return "Product not found."
        stock = getattr(product, "stock", 0)
        if stock is None:
            stock = 0
        if stock > 0:
            return f"In stock: {stock} unit(s) available. Product: {getattr(product, 'name', 'Item')}."
        return "Currently out of stock. We can notify when restocked."
    except Exception as e:
        logger.warning("check_stock failed: %s", e)
        return "Unable to check stock at the moment."


def _execute_track_order(channel, customer_phone):
    """Look up latest order by customer_phone (optionally scoped to channel). Returns JSON string for the AI."""
    try:
        from discount.orders_ai import track_order as _track_order
        data = _track_order(customer_phone, channel=channel)
        import json as _json
        return _json.dumps(data, ensure_ascii=False)
    except Exception as e:
        logger.warning("track_order failed: %s", e)
        return '{"found": false, "status": null, "shipping_company": null, "expected_delivery_date": null, "days_until_delivery": null, "customer_name": null}'


def _execute_apply_discount(channel, coupon_code):
    """Validate coupon and return a message for the agent (e.g. limited-time discount)."""
    if not coupon_code or not str(coupon_code).strip():
        return "No coupon code provided."
    code = str(coupon_code).strip().upper()
    # Optional: load from channel.context_data or Node config; for now use a small allowlist
    allowed = getattr(settings, "AI_SALES_COUPON_CODES", None) or ["WELCOME10", "RAMADAN15", "FIRST10", "COD10"]
    if code in [c.upper() for c in allowed]:
        return f"Coupon '{code}' is valid. You can offer a limited-time discount (e.g. 10% off) to the customer. Tell them the code is valid for this order."
    return f"Coupon '{code}' is not valid or expired. Suggest they contact support for a valid code, or emphasize product value instead."


def get_channel_catalog_context(channel, max_products=100, description_chars=200):
    """
    Build a single text block listing all products the channel owner has (for AI when no product is selected).
    Format: Product name, Price, Category, short Description — so the AI can answer "what do you have?" and suggest matches.
    """
    if not channel:
        return ""
    owner = getattr(channel, "owner", None)
    if not owner:
        return ""
    try:
        qs = Products.objects.filter(admin=owner).order_by("name")[: max(1, int(max_products))]
        lines = ["# STORE CATALOG (all products the store has)\n"]
        for p in qs:
            name = (getattr(p, "name", None) or "").strip() or "Unnamed"
            price = getattr(p, "price", None)
            currency = (getattr(p, "currency", None) or "MAD").strip() or "MAD"
            price_str = f"{price} {currency}" if price is not None else "—"
            category = (getattr(p, "category", None) or "").strip() or "general"
            desc = (getattr(p, "description", None) or "").strip()
            if desc and len(desc) > description_chars:
                desc = desc[: description_chars].rstrip() + "…"
            sku = (getattr(p, "sku", None) or "").strip()
            lines.append(f"- **{name}** | Price: {price_str} | Category: {category}" + (f" | SKU: {sku}" if sku else ""))
            if desc:
                lines.append(f"  Description: {desc}")
        return "\n".join(lines) if len(lines) > 1 else ""
    except Exception as e:
        logger.warning("get_channel_catalog_context: %s", e)
        return ""


def search_channel_products(channel, query, top_n=5):
    """
    Search the channel's products by query. Returns the closest matching products (by name, description, category).
    Used when the customer asks "do you have X?" — if we don't have X exactly, return the closest products we have.
    Returns a string for the AI (list of product names, prices, and why they're relevant).
    """
    if not channel or not query or not str(query).strip():
        return "No search query provided."
    owner = getattr(channel, "owner", None)
    if not owner:
        return "Store not configured."
    q = str(query).strip().lower()
    words = [w for w in re.split(r"\s+", q) if len(w) >= 2]
    if not words:
        return "Query too short. Use 2+ characters or words."
    try:
        products = list(Products.objects.filter(admin=owner).order_by("name")[:200])
        if not products:
            return "The store has no products in the catalog."
        scored = []
        for p in products:
            name = (getattr(p, "name", None) or "").strip().lower() or ""
            desc = (getattr(p, "description", None) or "").strip().lower() or ""
            category = (getattr(p, "category", None) or "").strip().lower() or ""
            sku = (getattr(p, "sku", None) or "").strip().lower() or ""
            text = f"{name} {desc} {category} {sku}"
            score = 0
            for w in words:
                if w in name:
                    score += 10
                if w in category:
                    score += 5
                if w in desc:
                    score += 2
                if w in sku:
                    score += 3
            scored.append((score, p))
        scored.sort(key=lambda x: -x[0])
        top = [p for _, p in scored[: top_n] if scored[0][0] > 0 or _ == scored[0][0]]
        if not top and scored:
            top = [p for _, p in scored[: top_n]]
        if not top:
            return "No matching products. Use the full catalog below to suggest alternatives."
        lines = ["Closest products matching the customer's request:\n"]
        for p in top:
            name = (getattr(p, "name", None) or "").strip() or "Unnamed"
            price = getattr(p, "price", None)
            currency = (getattr(p, "currency", None) or "MAD").strip() or "MAD"
            price_str = f"{price} {currency}" if price is not None else "—"
            category = (getattr(p, "category", None) or "").strip() or "general"
            lines.append(f"- {name} | Price: {price_str} | Category: {category}")
        return "\n".join(lines)
    except Exception as e:
        logger.warning("search_channel_products: %s", e)
        return "Search failed. Use the store catalog to suggest products."


def _execute_search_products(channel, query):
    """Execute search_products tool: return closest products for the channel matching the query."""
    return search_channel_products(channel, query or "", top_n=5)


def _execute_submit_customer_order(channel, sender, arguments, current_node):
    """
    Execute submit_customer_order tool. Product comes from session (current_node), not from AI.
    Returns a JSON string for the tool result (success or error message for AI to self-correct).
    """
    if not channel or not current_node:
        return json.dumps({"success": False, "message": "SYSTEM ERROR: Channel or product context missing."}, ensure_ascii=False)
    ai_cfg = getattr(current_node, "ai_model_config", None) or {}
    session_product_id = ai_cfg.get("product_id") if isinstance(ai_cfg, dict) else None
    try:
        session_product_id = int(session_product_id) if session_product_id is not None else None
    except (TypeError, ValueError):
        session_product_id = None
    session_seller_id = getattr(channel, "owner_id", None) or (getattr(channel, "owner", None) and getattr(channel.owner, "id", None))
    try:
        from discount.orders_ai import handle_submit_order_tool
        outcome = handle_submit_order_tool(
            arguments,
            session_product_id=session_product_id,
            session_seller_id=session_seller_id,
            channel=channel,
            customer_phone_from_chat=sender,
        )
        return json.dumps(outcome, ensure_ascii=False)
    except Exception as e:
        logger.exception("_execute_submit_customer_order: %s", e)
        return json.dumps({"success": False, "message": "SYSTEM ERROR: Order could not be processed. Please try again."}, ensure_ascii=False)


def run_ai_agent_node(current_node, sender, channel, state_header=None):
    """
    Run the AI agent for one node (product context, GPT, media, voice). Returns list of message dicts.
    Goal-oriented: uses ChatSession.context_data for sales_stage and sentiment; runs check_stock, apply_discount, record_order.
    On successful order save, expires ChatSession for (channel, sender).
    """
    from django.conf import settings

    output_messages = []
    reply_text = None
    order_was_saved = False
    saved_order = None
    try:
        from ai_assistant.services import (
            generate_reply_with_tools,
            continue_after_tool_calls,
            get_agent_name_for_node,
            get_order_confirmation_fallback,
            should_handover,
            get_handover_message,
            _is_price_or_quality_objection,
            _is_misunderstand_message,
        )
        from discount.orders_ai import (
            extract_order_data_from_reply,
            save_order_from_ai,
            should_accept_order_data,
            get_trust_score,
            increment_trust_score,
            reset_trust_score,
            looks_like_order_confirmation_without_data,
        )
        from django.db import transaction as db_transaction
        from django.core.cache import cache

        session = get_active_session(channel, sender)
        if not session and channel and sender:
            session, _ = ChatSession.objects.get_or_create(
                channel=channel,
                customer_phone=sender,
                defaults={"active_node": current_node, "is_expired": False, "ai_enabled": True},
            )
        ctx = getattr(session, "context_data", None) or {} if session else {}
        sales_stage = ctx.get("sales_stage")
        sentiment = ctx.get("sentiment")
        already_asked_for_sale = bool(ctx.get("has_asked_for_sale"))
        if not sentiment and channel and sender:
            conversation_for_sentiment = get_conversation_history(sender, channel)
            inferred = _infer_sentiment_from_conversation(conversation_for_sentiment)
            if inferred:
                sentiment = inferred
                if session:
                    ctx["sentiment"] = sentiment
                    session.context_data = ctx
                    session.save(update_fields=["context_data"])

        product_context = (getattr(current_node, "product_context", None) or "").strip()
        conversation = get_conversation_history(sender, channel)
        # Market/tone: do NOT use a global tone. 3 options:
        # (1) If there were chats before with this user → infer tone from that conversation (AR_MA → MA, AR_SA → SA).
        # (2) If first time and we have product context → use node market (from ai_model_config or node_language).
        # (3) If first time and no product context → infer from phone number (e.g. +966 → AR_SA, +212 → AR_MA).
        ai_config = getattr(current_node, "ai_model_config", None) or {}
        node_market = (ai_config.get("market") or "").strip().upper()
        if not node_market and getattr(current_node, "node_language", None):
            lang = (current_node.node_language or "").strip().upper()
            if lang.startswith("AR_SA") or lang == "SA":
                node_market = "SA"
            elif lang.startswith("AR_MA") or lang == "MA":
                node_market = "MA"
        if node_market not in ("MA", "SA", "GCC"):
            node_market = "MA"
        from ai_assistant.services import infer_market_from_conversation, infer_market_from_phone
        has_prior_conversation = len(conversation) > 1 and any(
            m.get("role") == "customer" and (m.get("body") or "").strip() and (m.get("body") or "").strip() != "[media]"
            for m in conversation
        )
        if has_prior_conversation:
            inferred = infer_market_from_conversation(conversation)
            market = inferred if inferred else node_market
        else:
            if product_context:
                market = node_market
            else:
                inferred = infer_market_from_phone(sender)
                market = inferred if inferred else node_market
        if not conversation or conversation[-1].get("role") != "customer":
            conversation = conversation or []
            conversation.append({"role": "customer", "body": ""})
        custom_instruction = None
        persona = getattr(current_node, "persona", None)
        if persona and getattr(persona, "behavioral_instructions", None):
            identity = (persona.behavioral_instructions or "").strip()
            product_block = f"Product Info: {product_context}" if product_context else "Product Info: (use conversation context)."
            custom_instruction = (
                f"Identity: {identity}. {product_block} "
                "Task: Respond to the customer as this specific persona. Match their tone but stay true to your identity."
            )
        if _conversation_already_has_order_confirmation(conversation):
            post_order_note = (
                
                "The customer already placed an order in this chat (order was confirmed). "
                "Do NOT repeat 'تم تسجيل طلبك. سنتواصل معك قريباً.' or any order confirmation. "
                "Answer their current question (e.g. delivery, another product, timing) normally."
            )
            custom_instruction = (custom_instruction + " " + post_order_note) if custom_instruction else post_order_note
        # Agent name: when voice reply is on use persona name or Chuck; when off use a random name (AI thinks as human)
        response_mode = getattr(current_node, "response_mode", None) or ""
        voice_enabled_legacy = getattr(current_node, "voice_enabled", False)
        voice_reply_on = (response_mode == "AUDIO_ONLY") or (response_mode == "AUTO_SMART") or voice_enabled_legacy
        agent_name = get_agent_name_for_node(voice_reply_on, persona, market=market)
        trust_score = get_trust_score(channel.id, sender) if channel else 0

        if state_header is None and product_context:
            state_header = _build_state_header_from_product_context(
                product_context, sales_stage=sales_stage, sentiment=sentiment
            )

        media_context = None
        store = getattr(channel, "owner", None) if channel else None
        allow_multi_modal = store and getattr(store, "is_feature_allowed", None) and store.is_feature_allowed("multi_modal")
        if allow_multi_modal:
            try:
                media_assets = list(getattr(current_node, "media_assets", []).all())
                if media_assets:
                    lines = []
                    for m in media_assets:
                        lines.append(f"ID {m.id}: {m.get_file_type_display()} – {m.description or m.file.name or 'Media'}")
                    media_context = "You have the following media assets to show the customer:\n" + "\n".join(lines)
            except Exception:
                pass
        # Product photo from catalog + dynamic persona (category + seller instructions)
        try:
            ai_cfg = getattr(current_node, "ai_model_config", None) or {}
            product_id = ai_cfg.get("product_id") if isinstance(ai_cfg, dict) else None
            if product_id is not None:
                first_img = ProductImage.objects.filter(product_id=int(product_id)).order_by("order", "id").first()
                if first_img and first_img.image:
                    product_photo_line = (
                        "Product photo (from catalog): When the customer asks for a photo/image/picture of the product, "
                        "include [SEND_PRODUCT_IMAGE] in your reply to send it. You may add a short caption."
                    )
                    media_context = (media_context + "\n\n" + product_photo_line) if media_context else product_photo_line
                # Inject category-based persona and seller_custom_persona into the sales prompt
                try:
                    from discount.product_sales_prompt import get_dynamic_persona_instruction
                    persona_instruction = get_dynamic_persona_instruction(product_id)
                    if persona_instruction:
                        custom_instruction = (custom_instruction or "") + "\n\n" + persona_instruction
                except Exception as persona_err:
                    logger.debug("Dynamic persona for product_id=%s: %s", product_id, persona_err)
        except (TypeError, ValueError, AttributeError):
            pass

        # Intelligent Handover (Supervisor Agent): analyze intent & bot performance before calling GPT
        handover, handover_reason = should_handover(conversation, market=market, use_llm_intent=True)
        if handover:
            handover_text = get_handover_message(market)
            result = {
                "reply": handover_text,
                "stage": None,
                "handover": True,
                "handover_reason": (handover_reason or "Customer asked for human").strip() or "Customer asked for human",
                "tool_calls": [],
                "raw_message": {},
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "model": None,
            }
        else:
            result = generate_reply_with_tools(
                conversation,
                custom_instruction=custom_instruction,
                product_context=product_context or None,
                trust_score=trust_score,
                media_context=media_context,
                state_header=state_header,
                sales_stage=sales_stage,
                sentiment=sentiment,
                market=market,
                agent_name=agent_name,
            )
        tool_calls_for_info = [tc for tc in (result.get("tool_calls") or []) if tc.get("name") in ("check_stock", "apply_discount", "track_order", "search_products", "submit_customer_order", "save_order", "record_order")]
        first_result_order_tools = [tc for tc in (result.get("tool_calls") or []) if tc.get("name") in ("save_order", "record_order")]
        submit_order_success_outcome = None
        save_order_result_order = None  # order from save_order/record_order when executed in loop
        if tool_calls_for_info and channel:
            raw_msg = result.get("raw_message") or {}
            tool_calls_from_api = raw_msg.get("tool_calls") or []
            tool_results = []
            for tc in tool_calls_from_api:
                tcid = tc.get("id")
                fn = tc.get("function", {})
                name = fn.get("name")
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except Exception:
                    args = {}
                if name == "check_stock":
                    content = _execute_check_stock(
                        channel,
                        product_id=args.get("product_id"),
                        sku=args.get("sku"),
                    )
                    tool_results.append({"tool_call_id": tcid, "content": content})
                elif name == "apply_discount":
                    content = _execute_apply_discount(channel, args.get("coupon_code"))
                    tool_results.append({"tool_call_id": tcid, "content": content})
                elif name == "track_order":
                    content = _execute_track_order(channel, args.get("customer_phone") or sender)
                    tool_results.append({"tool_call_id": tcid, "content": content})
                elif name == "search_products":
                    content = _execute_search_products(channel, args.get("query") or "")
                    tool_results.append({"tool_call_id": tcid, "content": content})
                elif name == "submit_customer_order":
                    content = _execute_submit_customer_order(channel, sender, args, current_node)
                    tool_results.append({"tool_call_id": tcid, "content": content})
                    try:
                        outcome = json.loads(content)
                        if outcome.get("success"):
                            submit_order_success_outcome = outcome
                    except Exception:
                        pass
                elif name in ("save_order", "record_order") and getattr(channel, "ai_order_capture", True):
                    args["customer_phone"] = normalize_customer_phone_for_order(args.get("customer_phone"), sender)
                    if "address" in args and not args.get("customer_city"):
                        args["customer_city"] = args.get("address")
                    args.setdefault("agent_name", agent_name)
                    args.setdefault("bot_session_id", f"{getattr(channel, 'id', '')}:{sender}"[:100])
                    if should_accept_order_data(conversation, args, current_stage=current_stage, trust_score=trust_score):
                        with db_transaction.atomic():
                            save_res = save_order_from_ai(channel, **args)
                        if isinstance(save_res, dict):
                            content = json.dumps(save_res)
                        elif save_res is not None:
                            content = json.dumps({"saved": True, "order_id": getattr(save_res, "order_id", None)})
                            save_order_result_order = save_res  # so we set order_was_saved and saved_order below
                        else:
                            content = json.dumps({"saved": False, "message": "Order could not be saved."})
                    else:
                        content = json.dumps({"saved": False, "message": "Order not accepted (trust/stage)."})
                    tool_results.append({"tool_call_id": tcid, "content": content})
            if tool_results:
                try:
                    result = continue_after_tool_calls(
                        conversation,
                        first_assistant_message=raw_msg,
                        tool_results=tool_results,
                        custom_instruction=custom_instruction,
                        product_context=product_context or None,
                        trust_score=trust_score,
                        media_context=media_context,
                        state_header=state_header,
                        sales_stage=sales_stage,
                        sentiment=sentiment,
                        market=market,
                        agent_name=agent_name,
                    )
                    # save_order/record_order were already executed in the loop above and tool result sent to AI
                except Exception as cont_err:
                    logger.warning("continue_after_tool_calls failed: %s", cont_err)

        # If submit_customer_order succeeded, mark order as saved and fetch for session expiry / confirmation
        if submit_order_success_outcome and channel:
            order_was_saved = True
            oid = submit_order_success_outcome.get("order_id")
            if oid:
                saved_order = SimpleOrder.objects.filter(order_id=oid).first()
        # If save_order/record_order succeeded in the tool loop, use that order
        if save_order_result_order and channel:
            order_was_saved = True
            saved_order = save_order_result_order

        reply_text = (result.get("reply") or "").strip()
        current_stage = result.get("stage")

        # Enforce "ask to order at most once" per session (code-level; AI may ignore prompt rules)
        is_order_ask = _reply_is_order_ask(reply_text)
        if is_order_ask and already_asked_for_sale:
            reply_text = _strip_order_ask_from_reply(reply_text)
            result = dict(result)
            result["tool_calls"] = [
                tc for tc in (result.get("tool_calls") or [])
                if tc.get("name") not in ("save_order", "record_order")
            ]
        if is_order_ask and not already_asked_for_sale and session:
            ctx = getattr(session, "context_data", None) or {}
            ctx["has_asked_for_sale"] = True
            session.context_data = ctx
            session.save(update_fields=["context_data"])

        # Do not hand over when last message is price/quality objection or "you don't understand" (sales agent handles: value + ask to rephrase)
        if result.get("handover") and conversation:
            last_user_msg = None
            for m in reversed(conversation):
                if m.get("role") == "customer":
                    last_user_msg = (m.get("body") or "").strip()
                    break
            if last_user_msg and (_is_price_or_quality_objection(last_user_msg) or _is_misunderstand_message(last_user_msg)):
                result = dict(result)
                result["handover"] = False
                result["handover_reason"] = ""
        if session:
            ctx = getattr(session, "context_data", None) or {}
            if current_stage:
                ctx["sales_stage"] = current_stage
            if sentiment:
                ctx["sentiment"] = sentiment
            if ctx != (getattr(session, "context_data", None) or {}):
                session.context_data = ctx
                session.save(update_fields=["context_data"])
        # HITL: If AI requested handover, disable AI for this session and notify merchant
        if result.get("handover") and channel and sender:
            handover_reason = (result.get("handover_reason") or "Customer asked for human").strip() or "Customer asked for human"
            try:
                session, _ = ChatSession.objects.get_or_create(
                    channel=channel,
                    customer_phone=sender,
                    defaults={"active_node": current_node, "is_expired": False, "ai_enabled": True},
                )
                session.ai_enabled = False
                session.handover_reason = handover_reason[:120]
                session.save(update_fields=["ai_enabled", "handover_reason"])
                from discount.models import HandoverLog
                HandoverLog.objects.create(channel=channel, customer_phone=sender, reason=session.handover_reason)
                # Private note in chat: why the AI handed over (visible to team only, not to customer)
                handover_note_body = f"AI handed over to human: {session.handover_reason}"
                Message.objects.create(
                    channel=channel,
                    sender=sender,
                    body=handover_note_body,
                    type="note",
                    is_internal=True,
                    is_from_me=True,
                    status="read",
                )
                team_id = getattr(channel, "owner_id", None) or (getattr(channel, "owner", None) and getattr(channel.owner, "id", None))
                if team_id:
                    send_socket(
                        "handover",
                        {
                            "channel_id": channel.id,
                            "customer_phone": sender,
                            "reason": session.handover_reason,
                            "message": reply_text[:200] if reply_text else "",
                        },
                        group_name=f"team_updates_{team_id}",
                    )
            except Exception as hitl_err:
                logger.warning("HITL handover update: %s", hitl_err)
        if current_stage and channel:
            cache.set(f"sales_stage:{channel.id}:{sender}", current_stage, timeout=3600)

        saved_order = None
        if channel and getattr(channel, "ai_order_capture", True):
            for tc in result.get("tool_calls") or []:
                if tc.get("name") in ("save_order", "record_order"):
                    args = tc.get("arguments") or {}
                    args["customer_phone"] = normalize_customer_phone_for_order(args.get("customer_phone"), sender)
                    if "address" in args and not args.get("customer_city"):
                        args["customer_city"] = args.get("address")
                    if should_accept_order_data(conversation, args, current_stage=current_stage, trust_score=trust_score):
                        with db_transaction.atomic():
                            args.setdefault("agent_name", agent_name)
                            args.setdefault("bot_session_id", f"{getattr(channel, 'id', '')}:{sender}"[:100])
                            save_res = save_order_from_ai(channel, **args)
                        if save_res is not None and not isinstance(save_res, dict):
                            saved_order = save_res
                            order_was_saved = True
                    else:
                        logger.warning(
                            "Order not saved (tool_calls save_order/record_order rejected): channel=%s sender=%s trust_score=%s stage=%r; should_accept_order_data returned False.",
                            channel.id if channel else None,
                            sender,
                            trust_score,
                            current_stage,
                        )

        if reply_text and channel and getattr(channel, "ai_order_capture", True):
            reply_text, order_data = extract_order_data_from_reply(reply_text)
            if order_data and should_accept_order_data(conversation, order_data, current_stage=current_stage, trust_score=trust_score):
                with db_transaction.atomic():
                    save_res = save_order_from_ai(
                        channel,
                        customer_phone=sender,
                        customer_name=order_data.get("name"),
                        customer_city=order_data.get("city") or order_data.get("address"),
                        sku=order_data.get("sku") or None,
                        product_name=order_data.get("product_name") or None,
                        price=order_data.get("price"),
                        agent_name=agent_name,
                        bot_session_id=f"{getattr(channel, 'id', '')}:{sender}"[:100],
                    )
                if save_res is not None and not isinstance(save_res, dict):
                    saved_order = save_res
                    order_was_saved = True
            elif order_data:
                logger.warning(
                    "Order not saved (ORDER_DATA rejected): channel=%s sender=%s trust_score=%s stage=%r; should_accept_order_data returned False.",
                    channel.id if channel else None,
                    sender,
                    trust_score,
                    current_stage,
                )
            elif looks_like_order_confirmation_without_data(reply_text):
                # Fail-safe: AI said "order registered" but [ORDER_DATA] tag was missing or invalid — Incomplete Capture
                logger.warning(
                    "Incomplete Capture: AI replied with order confirmation but no valid [ORDER_DATA] (channel=%s, sender=%s). Forcing retry.",
                    channel.id if channel else None,
                    sender,
                )
                reply_text = (
                    "عذراً، لم نستلم تفاصيل التوصيل كاملة. من فضلك أرسل الاسم الكامل، المدينة، والعنوان مرة أخرى."
                    " (Sorry, we didn’t get full delivery details. Please send full name, city, and address again.)"
                )

        if channel:
            if order_was_saved:
                reset_trust_score(channel.id, sender)
                expire_chat_session(channel, sender)
                # Trigger Google Sheets sync when order was saved via AI (uses channel.owner config; idempotent)
                if saved_order and getattr(saved_order, "pk", None):
                    try:
                        from discount.services.google_sheets_service import sync_order_to_google_sheets
                        import threading
                        def _sync_saved_order():
                            try:
                                sync_order_to_google_sheets(saved_order.pk)
                            except Exception as e:
                                logger.warning("Google Sheets sync after AI order (order_id=%s): %s", saved_order.pk, e)
                        t = threading.Thread(target=_sync_saved_order, daemon=True)
                        t.start()
                    except Exception as sheet_err:
                        logger.warning("Google Sheets export after AI order: %s", sheet_err)
                # Legacy: flow-based export when flow/user exist (may duplicate if same config)
                try:
                    flow = getattr(current_node, "flow", None)
                    user = getattr(flow, "user", None) if flow else None
                    if flow and user and (not saved_order or not getattr(saved_order, "pk", None)):
                        _run_google_sheets_export(current_node, flow, sender, channel, user)
                except Exception as sheet_err:
                    logger.warning("Google Sheets export (flow) after AI order: %s", sheet_err)
            else:
                increment_trust_score(channel.id, sender)
        if order_was_saved and saved_order:
            reply_text = format_order_confirmation(saved_order)
        if not reply_text:
            # Only use order confirmation fallback when we actually saved an order (avoid false "order registered")
            if order_was_saved and saved_order:
                reply_text = get_order_confirmation_fallback(market)
            else:
                reply_text = "كيف يمكنني مساعدتك؟"  # neutral fallback when AI returned empty and no order

        reply_text, send_media_ids = parse_and_strip_send_media(reply_text)
        reply_text, send_product_image = parse_and_strip_send_product_image(reply_text)
        base_url = (getattr(settings, "SITE_URL", "") or "").rstrip("/")
        VIDEO_SIZE_LIMIT = 16 * 1024 * 1024
        for mid in send_media_ids:
            if not allow_multi_modal:
                continue
            try:
                media_obj = NodeMedia.objects.filter(id=mid, node=current_node).first()
                if media_obj and media_obj.file:
                    fallback_caption = (media_obj.description or "").strip() or "صورة/فيديو من المنتج"
                    is_video = (media_obj.file_type or "").lower() == "video"
                    file_size = getattr(media_obj.file, "size", None) or 0
                    if is_video and file_size > VIDEO_SIZE_LIMIT:
                        output_messages.append({"type": "text", "content": fallback_caption, "delay": 0})
                        continue
                    media_url = base_url + media_obj.file.url if base_url else media_obj.file.url
                    msg_type = "video" if is_video else "image"
                    output_messages.append({
                        "type": msg_type, "media_url": media_url, "content": "",
                        "delay": 0, "fallback_caption": fallback_caption,
                    })
            except Exception as me:
                logger.warning("SEND_MEDIA %s failed: %s", mid, me)
        if send_product_image and current_node:
            try:
                ai_cfg = getattr(current_node, "ai_model_config", None) or {}
                product_id = ai_cfg.get("product_id") if isinstance(ai_cfg, dict) else None
                if product_id is not None:
                    first_img = ProductImage.objects.filter(product_id=int(product_id)).order_by("order", "id").first()
                    if first_img and first_img.image:
                        media_url = base_url + first_img.image.url if base_url else first_img.image.url
                        output_messages.append({
                            "type": "image", "media_url": media_url, "content": "",
                            "delay": 0, "fallback_caption": "صورة المنتج",
                        })
            except Exception as pe:
                logger.warning("SEND_PRODUCT_IMAGE failed: %s", pe)

        response_mode = getattr(current_node, "response_mode", None) or ""
        voice_enabled_legacy = getattr(current_node, "voice_enabled", False)
        word_count = len((reply_text or "").split())
        use_voice = (
            (response_mode == "AUDIO_ONLY") or
            (response_mode == "AUTO_SMART" and word_count >= 15) or
            (response_mode not in ("TEXT_ONLY", "AUDIO_ONLY", "AUTO_SMART") and voice_enabled_legacy)
        )

        if reply_text:
            if use_voice and channel:
                try:
                    from discount.whatssapAPI.voice_engine import generate_voice
                    from django.core.files.storage import default_storage
                    import uuid
                    voice_settings = _voice_settings_for_node(channel, current_node)
                    audio_path = generate_voice(reply_text, voice_settings)
                    if audio_path and os.path.exists(audio_path):
                        name = f"flow_audio/{uuid.uuid4().hex}.mp3"
                        with open(audio_path, "rb") as f:
                            default_storage.save(name, f)
                        try:
                            os.remove(audio_path)
                        except OSError:
                            pass
                        media_url = (base_url + default_storage.url(name).lstrip("/")) if base_url else default_storage.url(name)
                        output_messages.append({"type": "audio", "media_url": media_url, "content": "", "delay": current_node.delay or 0})
                    else:
                        output_messages.append({"type": "text", "content": reply_text, "delay": current_node.delay or 0})
                except Exception as ve:
                    logger.exception("AI_AGENT voice fallback: %s", ve)
                    output_messages.append({"type": "text", "content": reply_text, "delay": current_node.delay or 0})
            else:
                output_messages.append({"type": "text", "content": reply_text, "delay": current_node.delay or 0})
    except Exception as e:
        logger.exception("run_ai_agent_node failed: %s", e)
    return output_messages


def execute_flow(flow, sender, channel=None, user=None):
    """
    Execute flow and return clean WhatsApp-ready messages
    
    Args:
        flow: التدفق المراد تنفيذه
        sender: رقم المرسل
        channel: القناة (اختياري) - للتحقق من الصلاحيات
        user: المستخدم (اختياري) - للتحقق من الصلاحيات
    """
    try:
        # التحقق من الصلاحيات إذا كان channel و user موجودين
        if channel and user:
            has_permission, error = check_user_channel_permission(user, channel)
            if not has_permission:
                print(f"❌ Permission denied for flow execution: {error}")
                return None
        
        nodes = flow.nodes.all().order_by("id")
        connections = flow.connections.all()

        if not flow.start_node:
            print("❌ No start node defined for this flow")
            return None

        # Skip trigger node → Jump to next actual node
        current_node = flow.start_node
        if current_node.node_type == "trigger":
            next_conn = connections.filter(from_node=current_node).first()
            if not next_conn:
                print("❌ Trigger node has no outgoing connection")
                return None
            current_node = next_conn.to_node

        visited = set()
        output_messages = []

        while current_node and current_node.id not in visited:
            visited.add(current_node.id)

            # TEXT MESSAGE
            if current_node.node_type == "text-message":
                clean_text = (current_node.content_text or "").strip()

                if clean_text:
                    output_messages.append({
                        "type": "text",
                        "content": clean_text,
                        "delay": current_node.delay or 0
                    })

            # MEDIA MESSAGE
            elif current_node.node_type == "media-message":
                
                if current_node.content_media_url:
                    media_type = current_node.media_type or "image"  # أضف هذا
                    output_messages.append({
                        "type":media_type ,
                        "media_url": current_node.content_media_url,
                        "content": (current_node.content_text or "").strip(),
                        "delay": current_node.delay or 0
                    })

            # MIXED (text + media)
            elif current_node.node_type == "mixed":

                # Text first
                if current_node.content_text:
                    output_messages.append({
                        "type": "text",
                        "content": current_node.content_text.strip(),
                        "delay": current_node.delay or 0
                    })

                # Media second
                if current_node.content_media_url:
                    media_type = current_node.media_type or "image"  # أضف هذا
                    output_messages.append({
                        "type": media_type,
                        "media_url": current_node.content_media_url,
                        "content": "",
                        "delay": 0
                    })

            # AI AGENT (delegate to run_ai_agent_node; session expiry on order is handled inside)
            elif current_node.node_type == "ai-agent":
                output_messages.extend(run_ai_agent_node(current_node, sender, channel, state_header=None))

            # FOLLOW-UP NODE: schedule task only; no immediate message
            elif current_node.node_type == "follow-up":
                try:
                    from discount.whatssapAPI.follow_up import create_follow_up_task
                    create_follow_up_task(current_node, channel, sender)
                except Exception as e:
                    logger.warning("create_follow_up_task: %s", e)

            # GOOGLE SHEETS NODE: export order/conversation data asynchronously (no immediate message)
            elif current_node.node_type == "google-sheets":
                try:
                    _run_google_sheets_export(current_node, flow, sender, channel, user)
                except Exception as e:
                    logger.warning("Google Sheets export: %s", e)

            # Get next node
            next_conn = connections.filter(from_node=current_node).first()
            if not next_conn:
                break

            current_node = next_conn.to_node

        return output_messages

    except Exception as e:
        logger.error(f"❌ execute_flow error: {e}", exc_info=True)
        print(f"❌ execute_flow error: {e}")
        import traceback
        traceback.print_exc()
        return None


def _build_order_data_for_sheets(channel, sender):
    """
    Build a flat dict for Google Sheets export from ChatSession.context_data and latest SimpleOrder.
    Keys should match column_mapping variable names (e.g. customer_name, phone, city, total_price).
    """
    from discount.models import SimpleOrder
    data = {}
    if channel:
        session = get_active_session(channel, sender)
        if session and getattr(session, "context_data", None):
            data.update(session.context_data)
        latest = (
            SimpleOrder.objects.filter(channel=channel, customer_phone=sender)
            .order_by("-created_at")
            .first()
        )
        if latest:
            data.setdefault("customer_name", latest.customer_name)
            data.setdefault("customer_phone", latest.customer_phone)
            data.setdefault("phone", latest.customer_phone)
            data.setdefault("customer_city", latest.customer_city)
            data.setdefault("city", latest.customer_city)
            data.setdefault("address", latest.customer_city)
            data.setdefault("customer_country", latest.customer_country)
            data.setdefault("product_name", latest.product_name)
            data.setdefault("product", latest.product_name)
            data.setdefault("price", latest.price)
            data.setdefault("quantity", latest.quantity)
            if latest.price is not None and latest.quantity is not None:
                try:
                    data.setdefault("total_price", float(latest.price) * float(latest.quantity))
                except (TypeError, ValueError):
                    data.setdefault("total_price", latest.price)
            data.setdefault("order_id", latest.order_id)
            data.setdefault("sku", latest.sku)
    data.setdefault("phone", sender)
    data.setdefault("customer_phone", sender)
    return data


def _run_google_sheets_export(current_node, flow, sender, channel, user):
    """
    Run Google Sheets export in a background thread so the WhatsApp flow is not blocked.
    Uses flow.user's GoogleSheetsConfig and Global Service Account (or per-user credentials).
    """
    from discount.models import GoogleSheetsConfig, GoogleSheetsNode, SimpleOrder
    from discount.services.google_sheets_service import export_to_google_sheets, get_client_for_config

    config = None
    try:
        config = getattr(flow, "user", None) and GoogleSheetsConfig.objects.filter(user=flow.user).first()
    except Exception:
        pass
    if not config or not (getattr(config, "spreadsheet_id", None) or "").strip():
        logger.info("Google Sheets node: no config or spreadsheet_id for user %s", getattr(flow.user_id, "", ""))
        return
    if not get_client_for_config(config):
        logger.info("Google Sheets node: no credentials (set GOOGLE_SHEETS_CREDENTIALS_JSON or add credentials) for user %s", getattr(flow.user_id, "", ""))
        return
    order_data = _build_order_data_for_sheets(channel, sender)
    latest_order = None
    if channel:
        latest_order = (
            SimpleOrder.objects.filter(channel=channel, customer_phone=sender)
            .order_by("-created_at")
            .first()
        )
        if latest_order:
            try:
                latest_order.sheets_export_status = "pending"
                latest_order.save(update_fields=["sheets_export_status"])
            except Exception:
                pass

    def _do_export():
        try:
            export_to_google_sheets(
                user_id=flow.user_id,
                order_data=order_data,
                config=config,
                order_instance=latest_order,
            )
        except Exception as e:
            logger.exception("Google Sheets export (background): %s", e)
            if latest_order:
                try:
                    latest_order.sheets_export_status = "failed"
                    latest_order.save(update_fields=["sheets_export_status"])
                except Exception:
                    pass

    t = threading.Thread(target=_do_export, daemon=True)
    t.start()


def get_conversation_history(sender, channel, limit=25):
    """Build conversation_messages for GPT from Message model (sender + channel)."""
    qs = Message.objects.filter(sender=sender).order_by("-timestamp")
    if channel:
        qs = qs.filter(channel=channel)
    messages = list(qs[:limit])
    messages.reverse()
    return [
        {"role": "agent" if m.is_from_me else "customer", "body": (m.body or "").strip() or "[media]"}
        for m in messages
    ]


def try_ai_voice_reply(sender, body, channel):
    """
    When no flow matches: if channel.ai_auto_reply is on, get GPT sales-agent reply
    (with optional save_order and [ORDER_DATA: ...] tag), then send as voice (with
    channel.voice_delay_seconds) or text. Fallback to text if TTS fails.
    Hard-guard: plan must allow auto_reply and (if voice) ai_voice at execution time.
    """
    if not channel:
        return
    ai_on = getattr(channel, "ai_auto_reply", False)
    if not ai_on and not os.environ.get("AI_VOICE_AUTO_REPLY_ENABLED", "").strip().lower() in ("1", "true", "yes"):
        return
    store = getattr(channel, "owner", None)
    try:
        from django.core.exceptions import PermissionDenied
        from discount.services.security_check import verify_plan_access, FEATURE_AUTO_REPLY, FEATURE_AI_VOICE
        verify_plan_access(store, FEATURE_AUTO_REPLY)
    except PermissionDenied:
        logger.info("AI auto-reply skipped: plan does not allow auto_reply")
        return
    except ImportError as e:
        logger.warning("AI voice reply imports failed: %s", e)
        return
    try:
        from discount.whatssapAPI.voice_engine import generate_audio_file, process_and_send_voice
        from discount.orders_ai import (
            save_order_from_ai,
            extract_order_data_from_reply,
            is_order_cap_reached,
            should_accept_order_data,
            get_trust_score,
            increment_trust_score,
            reset_trust_score,
            looks_like_order_confirmation_without_data,
        )
        from ai_assistant.services import generate_reply_with_tools
    except ImportError as e:
        logger.warning("AI voice reply imports failed: %s", e)
        return

    conversation = get_conversation_history(sender, channel)
    if not conversation or conversation[-1].get("role") != "customer":
        conversation.append({"role": "customer", "body": body or ""})

    # Dynamic market/tone: from prior conversation dialect, else from phone (no node/product here)
    from ai_assistant.services import infer_market_from_conversation, infer_market_from_phone
    has_prior = len(conversation) > 1 and any(
        m.get("role") == "customer" and (m.get("body") or "").strip() and (m.get("body") or "").strip() != "[media]"
        for m in conversation
    )
    market = infer_market_from_conversation(conversation) if has_prior else infer_market_from_phone(sender)
    if market not in ("MA", "SA", "GCC"):
        market = "MA"

    # No product selected: give the AI the full catalog so it can answer "what do you have?" and suggest closest matches.
    catalog_context = get_channel_catalog_context(channel) if channel else ""
    product_context_for_reply = catalog_context or None
    custom_instruction = (
        "You have the STORE CATALOG below (all products this store has). Use it to answer what we have. "
        "If the customer asks for a product we don't have exactly (e.g. moringa and we only have gastro-balance supplement), "
        "call search_products with their request and suggest the closest products we do have (same category or similar use). "
        "CRITICAL: Do NOT call save_order or record_order in this chat. Do NOT output [ORDER_DATA: ...]. "
        "If they want to order, tell them to choose a product from the catalog first."
    )
    if is_order_cap_reached(channel):
        custom_instruction = (
            "The store's monthly order limit has been reached. Do not call save_order and do not add [ORDER_DATA: ...]. "
            "Politely tell the customer that the store will get back to them."
        )
    if _conversation_already_has_order_confirmation(conversation):
        post_order_note = (
            "The customer already placed an order in this chat. Do NOT repeat 'تم تسجيل طلبك. سنتواصل معك قريباً.'. "
            "Answer their current question (e.g. delivery, another product) normally."
        )
        custom_instruction = (custom_instruction + " " + post_order_note) if custom_instruction else post_order_note

    trust_score = get_trust_score(channel.id, sender)
    try:
        result = generate_reply_with_tools(
            conversation,
            custom_instruction=custom_instruction,
            product_context=product_context_for_reply,
            trust_score=trust_score,
            market=market,
        )
    except Exception as e:
        logger.exception("generate_reply_with_tools failed: %s", e)
        return

    # Execute info tools (track_order, check_stock, apply_discount, search_products) and get final reply
    tool_calls = result.get("tool_calls") or []
    info_tools = [tc for tc in tool_calls if tc.get("name") in ("track_order", "check_stock", "apply_discount", "search_products")]
    if info_tools and channel:
        raw_msg = result.get("raw_message") or {}
        tool_calls_from_api = raw_msg.get("tool_calls") or []
        tool_results = []
        for tc in tool_calls_from_api:
            tcid = tc.get("id")
            fn = tc.get("function", {})
            name = fn.get("name")
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except Exception:
                args = {}
            if name == "track_order":
                content = _execute_track_order(channel, args.get("customer_phone") or sender)
                tool_results.append({"tool_call_id": tcid, "content": content})
            elif name == "check_stock":
                content = _execute_check_stock(channel, product_id=args.get("product_id"), sku=args.get("sku"))
                tool_results.append({"tool_call_id": tcid, "content": content})
            elif name == "apply_discount":
                content = _execute_apply_discount(channel, args.get("coupon_code"))
                tool_results.append({"tool_call_id": tcid, "content": content})
            elif name == "search_products":
                content = _execute_search_products(channel, args.get("query") or "")
                tool_results.append({"tool_call_id": tcid, "content": content})
        if tool_results:
            try:
                from ai_assistant.services import continue_after_tool_calls, get_agent_name_for_node
                result = continue_after_tool_calls(
                    conversation,
                    first_assistant_message=raw_msg,
                    tool_results=tool_results,
                    custom_instruction=custom_instruction,
                    product_context=product_context_for_reply,
                    trust_score=trust_score,
                    market=market,
                    agent_name=get_agent_name_for_node(False, None, market=market),
                )
                order_tools = [t for t in tool_calls if t.get("name") in ("save_order", "record_order")]
                if order_tools:
                    result["tool_calls"] = list(result.get("tool_calls") or []) + order_tools
            except Exception as cont_err:
                logger.warning("continue_after_tool_calls (voice) failed: %s", cont_err)

    reply_text = (result.get("reply") or "").strip()
    current_stage = result.get("stage")
    order_was_saved = False
    saved_order = None

    # CRITICAL: This path has NO product context (no flow/product selected). Do NOT save orders —
    # the AI could hallucinate product/price. Orders are only allowed when the customer is in a
    # product flow (run_ai_agent_node with product_context).
    if False:  # disabled: never save order in voice/fallback path (no product context)
        for tc in result.get("tool_calls") or []:
            if tc.get("name") == "save_order" and getattr(channel, "ai_order_capture", True):
                args = tc.get("arguments") or {}
                args["customer_phone"] = normalize_customer_phone_for_order(args.get("customer_phone"), sender)
                args.setdefault("agent_name", "AI Agent")
                args.setdefault("bot_session_id", f"{getattr(channel, 'id', '')}:{sender}"[:100])
                if should_accept_order_data(conversation, args, current_stage=current_stage, trust_score=trust_score):
                    save_res = save_order_from_ai(channel, **args)
                    if save_res is not None and not isinstance(save_res, dict):
                        saved_order = save_res
                        order_was_saved = True

    reply_text, order_data = extract_order_data_from_reply(reply_text)
    # Do NOT save from [ORDER_DATA] when out of context (no product selected) — would be wrong product / 0 price.
    # Orders are only saved when customer is in a product flow (run_ai_agent_node with product_context).
    if looks_like_order_confirmation_without_data(reply_text):
        reply_text = (
            "عذراً، لم نستلم تفاصيل التوصيل كاملة. من فضلك أرسل الاسم الكامل، المدينة، والعنوان مرة أخرى."
            " (Sorry, we didn't get full delivery details. Please send full name, city, and address again.)"
        )

    if order_was_saved:
        reset_trust_score(channel.id, sender)
        expire_chat_session(channel, sender)
        if saved_order and getattr(saved_order, "pk", None):
            try:
                from discount.services.google_sheets_service import sync_order_to_google_sheets
                import threading
                def _sync_saved_order_voice():
                    try:
                        sync_order_to_google_sheets(saved_order.pk)
                    except Exception as e:
                        logger.warning("Google Sheets sync after AI order (voice path order_id=%s): %s", saved_order.pk, e)
                threading.Thread(target=_sync_saved_order_voice, daemon=True).start()
            except Exception as e:
                logger.warning("Google Sheets export after AI order (voice): %s", e)
    else:
        increment_trust_score(channel.id, sender)

    if order_was_saved and saved_order:
        reply_text = format_order_confirmation(saved_order)
    if not reply_text:
        # Only show order confirmation when we actually saved; use market/tone_desc for dynamic fallback
        if order_was_saved and saved_order:
            try:
                from ai_assistant.services import get_order_confirmation_fallback
                reply_text = get_order_confirmation_fallback(market)
            except Exception:
                reply_text = "تم تسجيل طلبك. سنتواصل معك قريباً."
        else:
            reply_text = "كيف يمكنني مساعدتك؟"

    if not reply_text:
        return

    use_voice = getattr(channel, "ai_voice_enabled", False)
    if use_voice:
        try:
            verify_plan_access(store, FEATURE_AI_VOICE)
        except PermissionDenied:
            use_voice = False
    if use_voice:
        try:
            process_and_send_voice(sender, reply_text, channel, send_whatsapp_audio_file)
        except Exception as e:
            logger.warning("process_and_send_voice failed, falling back to text: %s", e)
            send_automated_response(sender, [{"type": "text", "content": reply_text}], channel=channel)
    else:
        send_automated_response(sender, [{"type": "text", "content": reply_text}], channel=channel)










# -----------------------------------------------msg_process------------------
import re

def validate_user_state(user):
    """
    التحقق من حالة المستخدم بشكل شامل
    
    Args:
        user: المستخدم المراد التحقق منه
    
    Returns:
        tuple: (is_valid, error_message)
        - إذا نجح: (True, None)
        - إذا فشل: (False, error_message)
    """
    if not user:
        logger.warning("User validation failed: User is required")
        return False, "User is required"
    
    if not user.is_authenticated:
        logger.warning(f"User validation failed: User {user.id if hasattr(user, 'id') else 'unknown'} is not authenticated")
        return False, "User is not authenticated"
    
    # التحقق من أن المستخدم نشط
    if hasattr(user, 'is_active') and not user.is_active:
        logger.warning(f"User validation failed: User {user.id} account is inactive")
        return False, "User account is inactive"
    
    # التحقق من أن المستخدم مفعّل (إذا كان هناك حقل is_verified)
    if hasattr(user, 'is_verified') and not user.is_verified:
        logger.warning(f"User validation failed: User {user.id} account is not verified")
        return False, "User account is not verified"
    
    logger.debug(f"User {user.id} validation successful")
    return True, None


def check_user_channel_permission(user, channel):
    """
    التحقق من صلاحيات المستخدم على قناة معينة
    
    Args:
        user: المستخدم
        channel: القناة
    
    Returns:
        tuple: (has_permission, error_message)
    """
    if not user or not channel:
        logger.warning("Permission check failed: User and channel are required")
        return False, "User and channel are required"
    
    # التحقق من حالة المستخدم أولاً
    is_valid, error = validate_user_state(user)
    if not is_valid:
        logger.warning(f"Permission check failed for user {user.id if hasattr(user, 'id') else 'unknown'} on channel {channel.id}: {error}")
        return False, error
    
    # التحقق من أن القناة نشطة
    if not channel.is_active:
        logger.warning(f"Permission check failed: Channel {channel.id} is not active")
        return False, "Channel is not active"
    
    # استخدام method من المودل للتحقق من الصلاحيات
    has_permission = channel.has_user_permission(user)
    
    if not has_permission:
        logger.warning(f"Permission check failed: User {user.id} does not have permission to access channel {channel.id}")
        return False, "User does not have permission to access this channel"
    
    logger.debug(f"Permission check successful: User {user.id} has access to channel {channel.id}")
    return True, None


def validate_channel_id(channel_id, user=None):
    """
    التحقق من صحة channel_id والتحقق من صلاحيات المستخدم
    
    Args:
        channel_id: معرف القناة
        user: المستخدم (اختياري) - للتحقق من الصلاحيات
    
    Returns:
        tuple: (channel_object, error_message)
        - إذا نجح: (channel, None)
        - إذا فشل: (None, error_message)
    """
    try:
        # التحقق من وجود القناة
        channel = WhatsAppChannel.objects.get(id=channel_id)
        
        # التحقق من أن القناة نشطة
        if not channel.is_active:
            return None, "Channel is not active"
        
        # التحقق من صلاحيات المستخدم (إذا كان user موجود)
        if user:
            has_permission, error = check_user_channel_permission(user, channel)
            if not has_permission:
                return None, error
        
        # التحقق من وجود access_token و phone_number_id
        if not channel.access_token or not channel.phone_number_id:
            return None, "Channel configuration incomplete: Missing Token or Phone Number ID"
        
        return channel, None
        
    except WhatsAppChannel.DoesNotExist:
        return None, "Channel not found"
    except Exception as e:
        return None, f"Error validating channel: {str(e)}"


def remove_emojis(text):
    if not text:
        return ""
    # الإبقاء فقط على الأحرف التي تدعمها قواعد بيانات UTF8 العادية (3 بايت)
    # هذا يبقي العربية والإنجليزية ويحذف الإيموجي الحديثة
    return "".join(c for c in text if c <= '\uFFFF')

@csrf_exempt

def whatsapp_webhook(request):
    """
    ويب هوك واتساب محسن - يدعم الإعلانات ويحل مشكلة الإيموجي
    """
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
                    # 🔥 1. استخراج معرف الرقم الذي استقبل الرسالة 🔥
                    metadata = value.get('metadata', {})
                    phone_number_id = metadata.get('phone_number_id')
                    

                    
                    # 🔥 2. البحث عن القناة في قاعدة بياناتنا 🔥
                    try:
                        active_channel = WhatsAppChannel.objects.get(phone_number_id=phone_number_id)
                    except WhatsAppChannel.DoesNotExist:
                        print(f"❌ رسالة لرقم غير مسجل عندنا: {phone_number_id}")
                        continue  
                    
                    created= None
                    
                    if 'contacts' in value:
                        contact_data = value.get('contacts', [{}])[0]
                        phone = contact_data.get('wa_id')
                        raw_name = contact_data.get('profile', {}).get('name', '')
                        
                        safe_name = remove_emojis(raw_name)

                        if phone:
                            try:
                                active_channel = WhatsAppChannel.objects.filter(phone_number_id=phone_number_id).first()
                               
                            except WhatsAppChannel.DoesNotExist:
                                print(f"❌ Error: Channel not found for ID {phone_number_id}")
                                return HttpResponse("Channel not found", status=200) 
                            channel_owner = active_channel.owner
                            
                            contact, created = Contact.objects.get_or_create(
                            phone=phone,
                            channel=active_channel,
                            defaults={
                                'user': channel_owner,       
                                'name': safe_name,
                                'assigned_agent': active_channel.assigned_agents.first()
                            }
                        )

                       
                        if not created and not contact.channel:
                            contact.channel = active_channel
                            contact.user = channel_owner
                            pipeline_stage=Contact.PipelineStage.NEW
                            contact.pipeline_stage = pipeline_stage
                            contact.save()        
                           
                            if safe_name and (created or contact.name != safe_name):
                                contact.name = safe_name
                                contact.last_interaction = timezone.now()
                                contact.save()
                 
                    if 'messages' in value:
                        process_messages(value.get("messages", []) , channel=active_channel , name = raw_name )

                    if 'statuses' in value:

                        process_message_statuses(value['statuses'] , channel=active_channel)

            return HttpResponse("EVENT_RECEIVED", status=200)
            
        except Exception as e:
            print(f"❌ Webhook error: {e}")
            import traceback
            traceback.print_exc()
            return HttpResponse("ERROR", status=500)


def process_messages(messages , channel = None , name = None):
    """
    معالجة الرسائل الواردة - تدعم الإعلانات (Referral)
    """
    for msg in messages:
        try:
            sender = msg["from"]
            message_type = msg.get("type", "text")
            body = ""
            is_referral = False
            body_override = None
            transcription_failed = False

            # --- AI Ears: Audio (STT) and Image (Vision) ---
            access_token = None
            if channel and getattr(channel, "access_token", None):
                access_token = channel.access_token
            if not access_token:
                access_token = ACCESS_TOKEN

            if message_type in ("audio", "voice") and access_token:
                # Full Autopilot must be on to run Whisper (no transcription when autopilot is off)
                if channel and not getattr(channel, "ai_auto_reply", False):
                    pass  # Skip STT entirely: no download, no Whisper, no clean_transcription
                else:
                    media_id = (msg.get("voice") or msg.get("audio") or {}).get("id")
                    if media_id:
                        media_content = download_whatsapp_media(media_id, access_token)
                        if media_content:
                            try:
                                from ai_assistant.stt_service import (
                                    transcribe_audio,
                                    clean_transcription,
                                    STT_UNINTELLIGIBLE,
                                )
                                # Use active session node language or channel default for STT
                                voice_language_hint = "AUTO"
                                if channel and sender:
                                    sess = get_active_session(channel, sender)
                                    if sess and getattr(sess, "active_node", None):
                                        voice_language_hint = (
                                            getattr(sess.active_node, "node_language", None) or ""
                                        ).strip() or getattr(channel, "voice_language", "AUTO")
                                    else:
                                        voice_language_hint = getattr(channel, "voice_language", "AUTO")
                                body_override = transcribe_audio(
                                    media_content,
                                    voice_language_hint=voice_language_hint,
                                )
                                if body_override == STT_UNINTELLIGIBLE:
                                    body_override = ""
                                    transcription_failed = True
                                elif body_override and body_override.strip():
                                    body_override = clean_transcription(
                                        body_override,
                                        target_language=voice_language_hint or "AUTO",
                                    )
                            except Exception as e:
                                logger.exception("STT transcribe_audio: %s", e)
                            if body_override is None:
                                body_override = ""
                                transcription_failed = True
                        else:
                            transcription_failed = True
                    else:
                        transcription_failed = True
                    if body_override is not None:
                        body = body_override

            elif message_type == "image" and access_token:
                media_id = (msg.get("image") or {}).get("id")
                if media_id:
                    media_content = download_whatsapp_media(media_id, access_token)
                    if media_content:
                        try:
                            from ai_assistant.vision_service import analyze_image
                            body_override = analyze_image(media_content)
                        except Exception as e:
                            logger.exception("Vision analyze_image: %s", e)
                        if body_override:
                            body = body_override

            # --- استخراج محتوى الرسالة بذكاء ---
            
            # 1. حالة النص العادي
            if message_type == "text":
                body = msg.get("text", {}).get("body", "")
            
            # 2. حالة الأزرار والقوائم
            elif message_type == "interactive":
                int_type = msg.get("interactive", {}).get("type")
                if int_type == "button_reply":
                    body = msg["interactive"]["button_reply"]["title"]
                elif int_type == "list_reply":
                    body = msg["interactive"]["list_reply"]["title"]


            elif message_type == 'button':
    
                button_data = msg.get('button', {})
       
                body_text = button_data.get('text') 
                body = body_text
                # (اختياري) Payload مفيد لو كنت تريد تنفيذ كود خاص بناء عليه
                payload = button_data.get('payload')
 
            if "referral" in msg:
                is_referral = True
                ref_data = msg["referral"]
                headline = ref_data.get("headline", "Ad Click")
                body = ref_data.get("body", "") # نص الإعلان نفسه
                print(f"📢 Incoming Ad Referral: {headline}")
                if not body and message_type == "text": 
                     body = msg.get("text", {}).get("body", "")  
                
   
               

            
            print(f"📩 Processing from {sender}: '{body}' (Type: {message_type}, Referral: {is_referral})")

            # Stop logic: cancel any pending follow-up tasks when customer replies
            if channel and sender:
                try:
                    from discount.whatssapAPI.follow_up import cancel_pending_follow_up_tasks_for_customer
                    cancel_pending_follow_up_tasks_for_customer(channel, sender)
                except Exception as e:
                    logger.warning("cancel_pending_follow_up_tasks_for_customer: %s", e)
            
            # حفظ الرسالة (مع نص من STT/Vision إن وجد)
            save_incoming_message(
                msg, message_type=message_type, channel=channel, name=name,
                body_override=body_override if body_override is not None else None,
            )

            # Full Autopilot must be on to send any automated reply (trigger match, session, or fallback)
            if channel and not getattr(channel, "ai_auto_reply", False):
                continue

            # HITL gatekeeper: if this session has AI disabled, normally skip AI and notify merchant.
            # Sales-intent reset: if the customer sends a clear sales/greeting message, re-enable AI so we respond (no repeated handover message).
            if channel and sender:
                session_for_hitl = (
                    ChatSession.objects.filter(channel=channel, customer_phone=sender)
                    .order_by("-last_interaction")
                    .first()
                )
                if session_for_hitl and not getattr(session_for_hitl, "ai_enabled", True):
                    try:
                        from ai_assistant.services import message_shows_sales_intent
                        if body and message_shows_sales_intent(body):
                            session_for_hitl.ai_enabled = True
                            session_for_hitl.handover_reason = ""
                            session_for_hitl.save(update_fields=["ai_enabled", "handover_reason"])
                        else:
                            team_id = getattr(channel, "owner_id", None) or (getattr(channel, "owner", None) and getattr(channel.owner, "id", None))
                            if team_id:
                                send_socket(
                                    "handover_new_message",
                                    {
                                        "channel_id": channel.id,
                                        "customer_phone": sender,
                                        "reason": getattr(session_for_hitl, "handover_reason", "") or "Human takeover",
                                    },
                                    group_name=f"team_updates_{team_id}",
                                )
                            continue
                    except Exception as e:
                        logger.warning("HITL/sales-intent reset: %s", e)
                        continue

            # إذا فشل التحويل الصوتي، نرسل رداً ثابتاً ولا نشغل الفلو
            if transcription_failed:
                send_automated_response(
                    sender,
                    [{"type": "text", "content": "عذراً، لم أسمع المقطع الصوتي جيداً، هل يمكنك إعادة إرساله أو كتابة طلبك؟", "delay": 0}],
                    channel=channel,
                )
                continue
 
            flow = None

            if is_referral:
                flows_start = Flow.objects.filter(active=True, trigger_on_start=True)
                if channel:
                    flows_start = flows_start.filter(channel=channel)
                flow = flows_start.first()
                if not flow and body:
                    flow = get_matching_flow(sender, body, channel=channel)
            else:
                flow = get_matching_flow(sender, body, channel=channel)

            # Step A: If trigger matched, check for continuation (same flow already in session)
            session = get_active_session(channel, sender) if (flow and channel) else None
            same_flow_continuation = (
                flow and channel and session and getattr(session, "active_node", None)
                and getattr(session.active_node, "flow_id", None) == flow.id
            )

            if same_flow_continuation:
                # User already in this flow — continue conversation (don't re-run from trigger)
                try:
                    session.last_interaction = timezone.now()
                    session.save(update_fields=["last_interaction"])
                except Exception:
                    pass
                ctx = getattr(session, "context_data", None) or {}
                state_header = _build_state_header_from_product_context(
                    getattr(session.active_node, "product_context", None),
                    sales_stage=ctx.get("sales_stage"),
                    sentiment=ctx.get("sentiment"),
                )
                output_messages = run_ai_agent_node(
                    session.active_node, sender, channel, state_header=state_header
                )
                if output_messages:
                    send_automated_response(sender, output_messages, channel=channel)
                    flow.usage_count += 1
                    flow.last_used = timezone.now()
                    flow.save()
                else:
                    try_ai_voice_reply(sender, body, channel)
            elif flow:
                # New trigger or different flow: bind session and run full flow
                if channel:
                    ai_node = get_flow_first_ai_agent_node(flow)
                    if ai_node:
                        update_chat_session_on_trigger(channel, sender, ai_node)
                print(f"🚀 Executing Flow: {flow.name}")
                output_messages = execute_flow(flow, sender, channel=channel)

                if output_messages:
                    send_automated_response(sender, output_messages, channel=channel)
                    flow.usage_count += 1
                    flow.last_used = timezone.now()
                    flow.save()
                    # Keep session active (touch) so next message without trigger still finds it
                    if channel:
                        _touch_session_last_interaction(channel, sender)
            else:
                # Step B: No trigger matched — catalog choice, active session, or fallback voice
                session = get_active_session(channel, sender) if channel else None

                # B1: If we previously sent the catalog, try to resolve product choice
                catalog_pending = _get_catalog_pending(channel, sender) if channel else None
                if catalog_pending and body:
                    products_list = catalog_pending.get("products") or []
                    resolved = _resolve_product_choice(body, products_list)
                    if resolved:
                        node_id, product_name = resolved
                        chosen_node = Node.objects.filter(id=node_id).first() if node_id else None
                        _clear_catalog_pending(channel, sender)
                        if chosen_node:
                            update_chat_session_on_trigger(channel, sender, chosen_node)
                            state_header = _build_state_header_from_product_context(
                                getattr(chosen_node, "product_context", None),
                                sales_stage=None,
                                sentiment=None,
                            )
                            output_messages = run_ai_agent_node(chosen_node, sender, channel, state_header=state_header)
                            if output_messages:
                                send_automated_response(sender, output_messages, channel=channel)
                            else:
                                try_ai_voice_reply(sender, body, channel)
                        else:
                            try_ai_voice_reply(sender, body, channel)
                        continue
                    # Not a clear choice — clear catalog pending and fall through
                    _clear_catalog_pending(channel, sender)

                # B2: No session and user is asking for available products — send catalog and store state
                if not (session and getattr(session, "active_node", None)) and body and _is_catalog_intent(body):
                    catalog_products = get_channel_products_with_nodes(channel) if channel else []
                    if catalog_products:
                        payload = [{"product_id": p["product_id"], "name": p["name"], "node_id": p["node_id"]} for p in catalog_products]
                        _set_catalog_pending(channel, sender, payload)
                        _send_catalog_reply(sender, catalog_products, channel)
                        continue
                    # No products with nodes — fall through to voice reply

                # B3: Active session — continue same product
                if session and getattr(session, "active_node", None):
                    try:
                        session.last_interaction = timezone.now()
                        session.save(update_fields=["last_interaction"])
                    except Exception:
                        pass
                    ctx = getattr(session, "context_data", None) or {}
                    state_header = _build_state_header_from_product_context(
                        getattr(session.active_node, "product_context", None),
                        sales_stage=ctx.get("sales_stage"),
                        sentiment=ctx.get("sentiment"),
                    )
                    output_messages = run_ai_agent_node(
                        session.active_node, sender, channel, state_header=state_header
                    )
                    if output_messages:
                        send_automated_response(sender, output_messages, channel=channel)
                    else:
                        try_ai_voice_reply(sender, body, channel)
                else:
                    try_ai_voice_reply(sender, body, channel)
                
        except Exception as e:
            print(f"❌ Error in process_messages: {e}")
            import traceback
            traceback.print_exc()









def process_message_statuses(statuses, channel=None) :
    """
    معالجة حالات الرسائل (مثل تم التسليم، تم القراءة)
    
    Args:
        statuses: قائمة حالات الرسائل
        channel: القناة (اختياري) - للبحث في الرسائل الخاصة بالقناة فقط
    """
    for status in statuses:
        try:
            message_id = status.get('id')
            status_value = status.get('status')
            recipient_id = status.get('recipient_id')
            timestamp = status.get('timestamp')
            
            
            
            # تحديث حالة الرسالة في قاعدة البيانات إذا لزم الأمر
            if message_id:
                try:
                    message_filter = Message.objects.filter(message_id=message_id)
                    if channel:
                        message_filter = message_filter.filter(channel=channel)
                    
                    message = message_filter.first()
                    if message:
                        message.status = status_value
                        message.status_timestamp = _dt.datetime.now(_dt.timezone.utc)
                        message.save()
                    payload={
                                            'message_id': message.id,
                                            'status': status_value,
                                            'phone': status['recipient_id'] 
                                        }

                    team_id = channel.owner.id 

                    dynamic_group_name = f"team_updates_{team_id}"

                    send_socket(
                        data_type='message_status_update',
                     payload = payload ,
                     group_name =  dynamic_group_name
                                        )


#                                           contact_payload = {
#             "channel_id": channel.id if channel else None, # هام للفرونت إند - مع التحقق من None
#             "phone": message_obj.sender,
#             "name": name if name else message_obj.sender, # أو الاسم المخزن في جدول Contact
#             "snippet": snippet,
#             "unread": unread_count,
#             "last_id": message_obj.id,
#             "timestamp": message_obj.created_at.strftime("%H:%M") 
#         }

#         # 3. إرسال باكيج موحد يحتوي على الاثنين
#         full_payload = {
#             "contact": contact_payload,
#             "message": msg_payload
#         }
#         team_id = channel.owner.id 

# # 2. بناء اسم المجموعة الديناميكي (يجب أن يطابق تماماً ما كتبناه في consumers.py)
#         dynamic_group_name = f"team_updates_{team_id}"

#         send_socket(
#             data_type="new_message_received", # اسم نوع جديد وواضح
#             payload=full_payload ,
#             group_name = dynamic_group_name
#         )


                     
                except Message.DoesNotExist:
                    pass
                    
        except Exception as e:
            print(f"❌ Error processing message status: {e}")


























import os
import json
import base64
import mimetypes
import tempfile
import requests
from django.core.files.base import ContentFile
from django.utils import timezone

from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from discount.models import Message
import tempfile
import subprocess

def send_error_to_user(message, channel_name):
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.send)(
        channel_name,
        {
            "type": "broadcast_event",
            "message": message,
            "sender": "system"
        }
    )


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
    

def send_whatsapp_audio_file(recipient, audio_path, channel, user=None, group_name=None):
    """
    Read local audio file (e.g. from TTS), convert to OGG, send via Meta WhatsApp,
    then delete temporary file(s). Uses send_message_socket with media_upload.
    Returns result dict from send_message_socket; caller can check result.get("ok").
    """
    if not audio_path or not os.path.exists(audio_path):
        logger.warning("send_whatsapp_audio_file: missing or invalid audio_path")
        return {"ok": False, "error": "invalid_path"}
    user = user or (getattr(channel, "owner", None) if channel else None)
    group_name = group_name or (f"team_updates_{channel.owner.id}" if channel and getattr(channel, "owner", None) else "webhook_events")
    temp_ogg_path = None
    try:
        temp_ogg_path = convert_audio_to_ogg(audio_path)
        path_to_send = temp_ogg_path if temp_ogg_path else audio_path
        with open(path_to_send, "rb") as f:
            raw_bytes = f.read()
        b64 = base64.b64encode(raw_bytes).decode("ascii")
        message = {
            "data": b64,
            "filename": "voice_message.ogg",
            "mime": "audio/ogg",
            "body": "",
            "type": "audio",
        }
        result = send_message_socket(
            recipient, user, channel.id, message, "media_upload",
            group_name=group_name, request=None,
        )
        return result
    finally:
        for p in (temp_ogg_path, audio_path):
            try:
                if p and os.path.exists(p):
                    os.remove(p)
            except Exception as e:
                logger.warning("send_whatsapp_audio_file cleanup %s: %s", p, e)


# from process_messages.send_message_socket 

def send_message_socket(sreciver,  user ,channel_id ,  message, msg_type,
                        group_name,
                        channel_name=None,
                        request=None):


    def _cleanup_paths(*paths):
        for p in paths:
            try:
                if p and os.path.exists(p):
                    os.remove(p)
            except Exception:
                pass

    # متغيرات عامة
    media_id = None
    media_type = "text"
    body = ""
    to = sreciver
    uploaded_file = None
    temp_input_path = None
    temp_converted_path = None
    saved_local_bytes = None
    saved_mime = None
    saved_filename = None
    template_data = None
    r = None

    # تحقق إعداد - التحقق من channel_id والصلاحيات باستخدام دالة التحقق
    channel, error_msg = validate_channel_id(channel_id, user)
    if not channel:
        send_socket("error",  {"error": error_msg}, group_name=group_name, )
        return {"ok": False, "error": error_msg.lower().replace(" ", "_")}
    
    ACCESS_TOKEN  = channel.access_token
    PHONE_NUMBER_ID = channel.phone_number_id

    
    # if not ACCESS_TOKEN or not PHONE_NUMBER_ID:
    #     send_socket("error", {"error": "Server configuration error: Missing Token or ID"})
    #     return {"ok": False, "error": "Server configuration missing"}

    try:
        media_url = message.get("media_url") or message.get("file")
        media_id = message.get("media_id")
    
    # تحديد نوع الميديا إذا كان media_upload (سنحتاج لتغييره لاحقاً إلى image/video...)
        final_msg_type = msg_type
        has_upload_data = False
        if request is not None and request.FILES.get("file"):
            has_upload_data = True
        elif isinstance(message, dict) and message.get("data"):
            has_upload_data = True ,
        body_text = message.get("body", "" ) 
     
        if msg_type == "media_upload":
            media_url =''
            if request is not None:
                body = request.POST.get("body", "")
                media_type = request.POST.get("type", "text")
                file_obj = request.FILES.get("file")
                if not file_obj:
                    send_socket("error", {"error": "No file uploaded in request"} , group_name=group_name)
                    return {"ok": False, "error": "no_file"}
                # نستخدم file_obj (InMemoryUploadedFile/File)
                uploaded_file = file_obj
                saved_filename = getattr(uploaded_file, "name", "uploaded")
                saved_mime = getattr(uploaded_file, "content_type", None)
            else:
                # نتوقع message dict مع مفاتيح data (base64 or dataURL), filename, mime, body, type
                if not isinstance(message, dict):
                    send_socket("error", {"error": "Invalid message payload for media_upload"} , group_name=group_name)
                    return {"ok": False, "error": "invalid_payload"}

                body = message.get("body", "")
                media_type = message.get("type", "text")
                data = message.get("data")  # base64 or dataURL
                saved_filename = message.get("filename", "file")
                saved_mime = message.get("mime")

                if not data:
                    send_socket("error", {"error": "missing data for media_upload"} , group_name=group_name)
                    return {"ok": False, "error": "missing_data"}

                # دعم data URI مثل data:image/png;base64,AAA...
                if data.startswith("data:"):
                    header, b64 = data.split(",", 1)
                    saved_mime = header.split(";")[0].split("data:")[1]
                    raw_bytes = base64.b64decode(b64)
                else:
                    raw_bytes = base64.b64decode(data)

                # احفظ بايت مؤقتًا في ملف حتى يمكن رفعه لواتساب
                fd, tmp_path = tempfile.mkstemp(suffix=os.path.splitext(saved_filename)[1] or "")
                os.close(fd)
                with open(tmp_path, "wb") as f:
                    f.write(raw_bytes)
                temp_input_path = tmp_path
                uploaded_file = None  # نستخدم temp_input_path لاحقًا

            # حفظ مؤقت من uploaded_file إلى temp_input_path إن كان FileObj
            if uploaded_file and not temp_input_path:
                try:
                    if hasattr(uploaded_file, "temporary_file_path"):
                        temp_input_path = uploaded_file.temporary_file_path()
                    else:
                        fd, tmp_path = tempfile.mkstemp(suffix=os.path.splitext(saved_filename)[1] or "")
                        os.close(fd)
                        with open(tmp_path, "wb") as out_f:
                            for chunk in uploaded_file.chunks():
                                out_f.write(chunk)
                        temp_input_path = tmp_path
                except Exception as e:
                    _cleanup_paths(temp_input_path)
                    send_socket("error", {"error": "failed to save uploaded file", "details": str(e)} , group_name=group_name)
                    return {"ok": False, "error": "failed_save", "details": str(e)}

            # تحويل للصيغ المطلوبة إن لزم (مثلاً audio -> ogg)
            if media_type == "audio":
                try:
                    temp_conv = convert_audio_to_ogg(temp_input_path)   
                    if temp_conv:
                        temp_input_path = temp_conv
                        saved_filename = "voice_message.ogg"
                        saved_mime = "audio/ogg"

                except Exception as e:
                    print("Audio conversion failed:", e)

            # إعداد الميتا
            if not saved_mime:
                saved_mime = mimetypes.guess_type(saved_filename)[0] or "application/octet-stream"

            # رفع الملف إلى WhatsApp
            fb_upload_url = f"https://graph.facebook.com/v22.0/{PHONE_NUMBER_ID}/media"
            params = {"messaging_product": "whatsapp", "access_token": ACCESS_TOKEN}

            try:
                with open(temp_input_path, "rb") as fh:
                    files = {"file": (saved_filename, fh, saved_mime)}
                    fb_res = requests.post(fb_upload_url, params=params, files=files, timeout=80)
            except Exception as e:
                _cleanup_paths(temp_input_path, temp_converted_path)
                send_socket("error", {"error": "upload connection failed", "details": str(e)} , group_name=group_name)
                return {"ok": False, "error": "upload_failed", "details": str(e)}

            if fb_res.status_code not in (200, 201):
                _cleanup_paths(temp_input_path, temp_converted_path)
                send_socket("error", {"error": "whatsapp upload rejected", "details": fb_res.text} , group_name=group_name)
                return {"ok": False, "error": "upload_rejected", "details": fb_res.text}

            fb_json = fb_res.json()
            media_id = fb_json.get("id")

            # اقرأ الملف ليحفظ محلياً لاحقاً
            try:
                with open(temp_input_path, "rb") as fh:
                    saved_local_bytes = fh.read()
            except Exception:
                saved_local_bytes = None

        
        elif msg_type in ['image', 'video', 'audio', 'document'] and media_url:
            final_msg_type = msg_type
            media_type = final_msg_type
            captions = message.get("caption")
            # print('media_url', media_url , ' media_type ', media_type)

            media_object = {}
            
            # الأولوية 1: الـ ID (سواء جاء من الرفع في الخطوة 2 أو كان موجوداً مسبقاً)
            if media_id:
                media_object["id"] = media_id
            
            # الأولوية 2: الرابط (للردود السريعة)
            elif media_url:
                media_object["link"] = media_url
                
            
            # إذا فشلنا في إيجاد أي منهما لنوع ميديا
            elif final_msg_type in ['image', 'video', 'audio', 'document']:
                send_socket("error", {"error": "Missing both media_id and media_url"}, group_name=group_name)
                return {"ok": False, "error": "missing_media_source"}

            # بناء الجيسون
            data_payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to":to,
                "type": final_msg_type
            }

            # إضافة النص (Caption)
            body_text = message.get("body", "")
            if body_text and final_msg_type != 'audio': # الصوت لا يقبل caption
                media_object["caption"] = body_text

            # دمج كائن الميديا في الرسالة
            if final_msg_type in ['image', 'video', 'audio', 'document']:
                data_payload[final_msg_type] = media_object
            elif final_msg_type == 'text':
                data_payload["text"] = {"body": body_text}

      
        else:
            if request is not None:
                payload = json.loads(request.body.decode("utf-8") or "{}")
                 
            else:
                # نتوقع message dict
                payload = message if isinstance(message, dict) else {}
                print("Payload from request:", payload)

            to = payload.get("to", sreciver)
            media_type = payload.get("media_type") or payload.get("type") or "text"

            if not to:
                send_socket("error", {"error": "missing 'to' field"} , group_name=group_name)
                return {"ok": False, "error": "missing_to"}

            if media_type == "template":
                template_data = payload.get("template")
                # media_type = payload.get("media_type") or payload.get("type") or "text"
            else:
                body = payload.get("body", "")
                media_id = payload.get("media_id")

    except Exception as e:
        _cleanup_paths(temp_input_path, temp_converted_path)
        send_socket("error", {"error": "request processing error", "details": str(e)} ,group_name=group_name)
        return {"ok": False, "error": "processing_error", "details": str(e)}

    # ----------------------------------------
    # بناء بايلود واتساب
    # ----------------------------------------
    try:
        send_payload = {"messaging_product": "whatsapp", "to": to}

        if (not media_type) or media_type == "text":
            send_payload["type"] = "text"
            send_payload["text"] = {"body": body or ""}


        elif media_type in ("image", "audio", "video", "document"):
                media_url = message.get("media_url")  
                print('message' , message.get('body') , ' media_url ', media_url)

                # 2. بناء كائن الميديا بذكاء (ID or Link)
                media_object = {}

                if media_id:
                    media_object["id"] = media_id
                elif media_url:
                    media_object["link"] = media_url
                else:
                    # 3. الخطأ يظهر فقط إذا غاب الاثنان معاً
                    _cleanup_paths(temp_input_path, temp_converted_path)
                    send_socket("error", {"error": "missing both media_id and media_url"} , group_name=group_name)
                    return {"ok": False, "error": "missing_media_source"}

                # 4. إضافة الكائن للـ Payload
                send_payload["type"] = media_type
                send_payload[media_type] = media_object
                
                # إضافة الشرح (Caption)
                if body_text and media_type != "audio":
                    send_payload[media_type]["caption"] = body_text

        elif media_type == "template":
                if "template_name" in payload:
                    template_data = {
                        "name": payload.get("template_name"),
                        "language": payload.get("language"),
                        "components": payload.get("components", [])
                    }

        else:
            _cleanup_paths(temp_input_path, temp_converted_path)
            send_socket("error", {"error": f"unsupported type: {media_type}"} ,group_name=group_name)
            return {"ok": False, "error": "unsupported_type"}

        # إرسال لواتساب (HTTP)
        url = f"https://graph.facebook.com/v22.0/{PHONE_NUMBER_ID}/messages"
        headers = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}
        r = requests.post(url, headers=headers, json=send_payload, timeout=30)
        print('payload to sent',send_payload)
        
    except Exception as e:
        _cleanup_paths(temp_input_path, temp_converted_path)
        send_socket("error", {"error": "api connection failed", "details": str(e)}, group_name=group_name)
        return {"ok": False, "error": "api_connection_failed", "details": str(e), }


    saved_message_id = None
    status_code = getattr(r, "status_code", 500)
 
    
    if status_code in (200, 201):
        try:
            msg_kwargs = {"sender": to, "is_from_me": True}
            
          
            try:
                # 1. تحويل الرد إلى JSON
                response_data = r.json() 
                print('response_data',response_data)
                
                # 2. استخراج المعرف من: {"messages":[{"id":"wamid..."}]}
                if 'messages' in response_data and len(response_data['messages']) > 0:
                    wa_message_id = response_data['messages'][0].get('id')
                    
                    # 3. إضافته لقائمة الحفظ
                    # تأكد أن اسم الحقل في المودل هو 'message_id'
                    msg_kwargs["message_id"] = wa_message_id 
                    
                  
            except Exception as json_err:
                print(f"⚠️ Failed to extract WhatsApp ID: {json_err}")
            # ========================================================

            if media_type == "template":
                tpl_name = template_data.get('name', 'Template')
                msg_kwargs["body"] = f"[Template: {tpl_name}]"
            else:
                msg_kwargs["body"] = body or ""
                if media_type != "text":
                    msg_kwargs["media_type"] = media_type
                    msg_kwargs["captions"] = body_text
                    msg_kwargs["type"] = media_type
                if media_id:
                    msg_kwargs["media_id"] = media_id

            saved_message = Message.objects.create(channel=channel, **msg_kwargs)

            saved_message_id = saved_message.id
            if channel and to:
                try:
                    session = ChatSession.objects.filter(channel=channel, customer_phone=str(to).strip()).order_by("-last_interaction").first()
                    if session:
                        session.last_manual_message_at = timezone.now()
                        session.save(update_fields=["last_manual_message_at"])
                except Exception:
                    pass
            # media_url = ""
             
            if saved_message_id:
                try:
                 
                    msg_obj = Message.objects.get(id=saved_message_id)
                     
                    if msg_obj.media_file:
                        media_url = msg_obj.media_file.url
                   
 
                except Exception:
                    pass
 
            if saved_local_bytes and hasattr(saved_message, "media_file"):
                 
                try:
                    ext = ""
                    if saved_mime:
                        if "ogg" in saved_mime or "opus" in saved_mime: ext = ".ogg"
                        elif "mp4" in saved_mime: ext = ".mp4"
                        elif "jpeg" in saved_mime or "jpg" in saved_mime: ext = ".jpg"
                        elif "png" in saved_mime: ext = ".png"
                        elif "pdf" in saved_mime: ext = ".pdf"
                        if not ext:
                            if media_type == 'audio': ext = ".mp3"   # فرض mp3 للصوت
                            elif media_type == 'image': ext = ".jpg" # فرض jpg للصور
                            elif media_type == 'video': ext = ".mp4" # فرض mp4 للفيديو


                    fname = f"{media_id or 'file'}{ext}"
                    saved_message.media_file.save(fname, ContentFile(saved_local_bytes), save=True)
                    media_url = saved_message.media_file.url
                except Exception as ex_save:
                    print("Error saving media to DB:", ex_save)
            else:
                # 🔥 التصحيح هنا 🔥
                # الحالة: لدينا رابط خارجي (S3) ولا يوجد ملف محلي (bytes)
                
                 
                
                # 1. إذا كان المودل يحتوي على حقل لتخزين الرابط النصي، نحفظه فيه
                # (تأكد أن المودل لديك فيه حقل بهذا الاسم، وإلا احذف السطر التالي)
                if hasattr(saved_message, "media_url"): 
                    saved_message.media_url = media_url
                    saved_message.save() # لا تنسَ الحفظ
                pass

            if hasattr(saved_message, "created_at") and not saved_message.created_at:
                saved_message.created_at = timezone.now()
                saved_message.save()

        except Exception as e:
            print("Error saving to DB:", e)
    # تنظيف نهائي
    _cleanup_paths(temp_input_path, temp_converted_path)
    snippet = body or ""
    if media_type == 'image': snippet = 'image'
    elif media_type == 'video': snippet = 'vedio'
    elif media_type == 'audio': snippet = 'audio'
    elif media_type == 'template': 
        tpl_name = template_data.get('name') if template_data else "Template"
        snippet = f"📄 {tpl_name}"

    final_payload = {
        "status": status_code,
        "whatsapp_response": r.text if hasattr(r, "text") else str(r),
        "saved_message_id": saved_message_id,
        "media_id": media_id,
        "body": body or body_text,
        "to": to,
        "captions": body_text,
        "media_type": media_type,
        "url": media_url,  # ✅ أضفنا الرابط هنا لكي يعرضه المتصفح
        "media_url": media_url # ✅ نسخة احتياطية حسب تسمية الجافاسكربت لديك
    }
    sidebar_payload = {
        "phone": to, 
        "name": to,  # سيتم تحسينه في الفرونت إند إذا كان الاسم موجوداً
        "snippet": snippet,
        "timestamp": timezone.now().strftime("%H:%M"),
        "unread": 0,       # 0 لأننا نحن المرسلون
        "last_status": "sent",
        "fromMe": True,    # ضروري لظهور أيقونة الصح
        "channel_id": channel_id ,
         
    }
 
    send_socket("finished",final_payload , group_name= group_name)
    send_socket("update_sidebar_contact", sidebar_payload , group_name = group_name)


    # للإستخدام الداخلي نعيد dict
    return {"ok": status_code in (200,201), "result": final_payload}


# ---------------------------------------------------------------------------
# HITL: Chat session AI toggle & Re-enable AI API
# ---------------------------------------------------------------------------
def _get_channel_for_hitl(request, channel_id):
    """Resolve channel for current user (for HITL APIs)."""
    try:
        from discount.whatssapAPI.views import get_target_channel
        return get_target_channel(request.user, channel_id)
    except Exception:
        return None


@require_GET
def api_chat_session_status(request):
    """
    GET ?channel_id=&customer_phone=
    Returns { ai_enabled, handover_reason } for the chat session (for UI badge and toggle).
    """
    from django.contrib.auth.decorators import login_required as _login_required
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=401)
    channel_id = request.GET.get("channel_id")
    customer_phone = (request.GET.get("customer_phone") or "").strip()
    if not channel_id or not customer_phone:
        return JsonResponse({"ai_enabled": True, "handover_reason": ""})
    channel = _get_channel_for_hitl(request, channel_id)
    if not channel:
        return JsonResponse({"error": "Channel not found"}, status=404)
    session = (
        ChatSession.objects.filter(channel=channel, customer_phone=customer_phone)
        .order_by("-last_interaction")
        .first()
    )
    return JsonResponse({
        "ai_enabled": getattr(session, "ai_enabled", True) if session else True,
        "handover_reason": (getattr(session, "handover_reason", None) or "") if session else "",
    })


@require_http_methods(["POST"])
def api_chat_session_reenable_ai(request):
    """
    POST channel_id= & customer_phone=
    Set ai_enabled=True for this session so the AI resumes. Clears handover_reason.
    """
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=401)
    channel_id = request.POST.get("channel_id") or request.GET.get("channel_id")
    customer_phone = (request.POST.get("customer_phone") or request.GET.get("customer_phone") or "").strip()
    if not channel_id or not customer_phone:
        return JsonResponse({"error": "channel_id and customer_phone required"}, status=400)
    channel = _get_channel_for_hitl(request, channel_id)
    if not channel:
        return JsonResponse({"error": "Channel not found"}, status=404)
    session = (
        ChatSession.objects.filter(channel=channel, customer_phone=customer_phone)
        .order_by("-last_interaction")
        .first()
    )
    if session:
        session.ai_enabled = True
        session.handover_reason = ""
        session.save(update_fields=["ai_enabled", "handover_reason"])
    return JsonResponse({"success": True, "ai_enabled": True})


@require_http_methods(["POST"])
def api_chat_session_toggle_ai(request):
    """
    POST channel_id= & customer_phone= & ai_enabled= (true/false)
    Merchant toggles AI on/off for this chat. When turning off, set last_manual_message_at.
    """
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=401)
    channel_id = request.POST.get("channel_id") or request.GET.get("channel_id")
    customer_phone = (request.POST.get("customer_phone") or request.GET.get("customer_phone") or "").strip()
    raw = (request.POST.get("ai_enabled") or request.GET.get("ai_enabled") or "true").strip().lower()
    ai_enabled = raw in ("1", "true", "yes")
    if not channel_id or not customer_phone:
        return JsonResponse({"error": "channel_id and customer_phone required"}, status=400)
    channel = _get_channel_for_hitl(request, channel_id)
    if not channel:
        return JsonResponse({"error": "Channel not found"}, status=404)
    session = (
        ChatSession.objects.filter(channel=channel, customer_phone=customer_phone)
        .order_by("-last_interaction")
        .first()
    )
    if not session:
        session = ChatSession.objects.create(
            channel=channel,
            customer_phone=customer_phone,
            ai_enabled=ai_enabled,
            last_manual_message_at=timezone.now() if not ai_enabled else None,
        )
    else:
        session.ai_enabled = ai_enabled
        session.handover_reason = "" if ai_enabled else (session.handover_reason or "Merchant took over")
        if not ai_enabled:
            session.last_manual_message_at = timezone.now()
        session.save(update_fields=["ai_enabled", "handover_reason", "last_manual_message_at"])
    return JsonResponse({"success": True, "ai_enabled": session.ai_enabled})
