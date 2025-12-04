
import json
import os
import logging
from django.conf import settings
from django.http import HttpResponse
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

from discount.models import CustomUser, Flow, Message ,Contact , WhatsAppChannel
from django.utils import timezone
from ..channel.socket_utils import send_socket





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
                    else:
                        # حفظ الرسالة المرسلة في قاعدة البيانات
                        try:
                            body = item.get("content", "")
                            media_url = item.get("media_url")
                            media_id = item.get("media_id" , None)
                            
                            Message.objects.create(
                                channel=channel if channel else None,
                                sender=recipient,
                                body=body,
                                is_from_me=True,
                                media_type=msg_type if msg_type in ["image", "video", "audio", "document"] else None,
                                media_id= media_id,
                                media_url = media_url , 
                                message_id= res.json().get("messages", [{}])[0].get("id")
                            )
                            payload ={
                                'sender':recipient,
                                'body': body,
                                'is_from_me':True,
                                'media_type':msg_type if msg_type in ["image", "video", "audio", "document"] else None,
                               'media_id': media_id,
                                'media_url' : media_url , 
                                'message_id': res.json().get("messages", [{}])[0].get("id")
                           }
                            send_socket("new_contact" ,payload)
                             
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
def save_incoming_message(msg , sender = None , channel = None):
    """
    حفظ الرسالة الواردة في قاعدة البيانات
    """
    try:
        if not sender :
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
            channel= channel if channel else None ,
            sender=sender ,
            body=body,
            is_from_me=False,
            media_type=media_type,
            media_id=media_id,
            message_id=message_id,
            timestamp=parsed_timestamp,
            # save msg url if msg is media
            media_url = media_id,
        )
         
 


        # معالجة الوسائط إذا وجدت - استخدام access_token من channel إذا كان موجوداً
        access_token_to_use = None
        if channel and channel.access_token:
            access_token_to_use = channel.access_token
        elif ACCESS_TOKEN:
            access_token_to_use = ACCESS_TOKEN
            
        if media_id and access_token_to_use:
            media_content = download_whatsapp_media(media_id, access_token_to_use)
            if media_content:
                filename = f"{media_id}_{media_type}.{get_media_extension(media_type)}"
                message_obj.media_file.save(filename, ContentFile(media_content))
                message_obj.save()

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

        unread_count = Message.objects.filter(sender=message_obj.sender, is_read=False).count()

        contact_payload = {
            "channel_id": channel.id if channel else None, # هام للفرونت إند - مع التحقق من None
            "phone": message_obj.sender,
            "name": message_obj.sender, # أو الاسم المخزن في جدول Contact
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

        send_socket(
            data_type="new_message_received", # اسم نوع جديد وواضح
            payload=full_payload
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
        from datetime import timedelta
        if timezone.now() - last_msg.timestamp > timedelta(hours=24):
            is_new_conversation = True

    flows = Flow.objects.filter(active=True)

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
            print('👀🥰😘 recived' , data)
        
            print("📨 Received WhatsApp webhook:", data) 
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

                    # 🔥 3. تمرير القناة لدالة الحفظ 🔥
                    # if 'messages' in value:
                    #     for msg in value['messages']:
                    #         save_incoming_message(msg, channel=active_channel) # نمرر كائن القناة


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
                            defaults={
                                'user': channel_owner,       
                                'channel': active_channel,  
                                'name': safe_name     
                            }
                        )

                       
                        if not created and not contact.channel:
                            contact.channel = active_channel
                            contact.user = channel_owner
                            contact.save()        
                           
                            if safe_name and (created or contact.name != safe_name):
                                contact.name = safe_name
                                contact.last_interaction = timezone.now()
                                contact.save()
                 
                    if 'messages' in value:
                        process_messages(value.get("messages", []) , channel=active_channel)

                    if 'statuses' in value:

                        process_message_statuses(value['statuses'] , channel=active_channel)

            return HttpResponse("EVENT_RECEIVED", status=200)
            
        except Exception as e:
            print(f"❌ Webhook error: {e}")
            import traceback
            traceback.print_exc()
            return HttpResponse("ERROR", status=500)


def process_messages(messages , channel = None):
    """
    معالجة الرسائل الواردة - تدعم الإعلانات (Referral)
    """
    for msg in messages:
        try:
            sender = msg["from"]
            message_type = msg.get("type", "text")
            body = ""
            is_referral = False

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
 
            if "referral" in msg:
                is_referral = True
                ref_data = msg["referral"]
                headline = ref_data.get("headline", "Ad Click")
                body = ref_data.get("body", "") # نص الإعلان نفسه
                print(f"📢 Incoming Ad Referral: {headline}")
                
                # إذا لم يكن هناك نص مرفق مع الإعلان، نعتبرها "بداية محادثة" صريحة
                if not body and message_type == "text": 
                     body = msg.get("text", {}).get("body", "") # محاولة جلب النص مرة أخرى

            
            print(f"📩 Processing from {sender}: '{body}' (Type: {message_type}, Referral: {is_referral})")
            
            # حفظ الرسالة (تأكد من أن دالة الحفظ لديك تدعم الحقول الفارغة)
            save_incoming_message(msg , channel = channel ) 
 
            flow = None
            
            if is_referral:

                flow = Flow.objects.filter(active=True, trigger_on_start=True).first()
                if not flow and body:
                     # إذا لم نجد فلو بداية، نبحث في نص الإعلان
                     flow = get_matching_flow(sender, body, channel=channel)
            else:
                # رسالة عادية
                flow = get_matching_flow(sender, body, channel=channel)
            
            # --- التنفيذ ---
            if flow:
                print(f"🚀 Executing Flow: {flow.name}")
                output_messages = execute_flow(flow, sender, channel=channel)
                
                if output_messages:
                    send_automated_response(sender, output_messages, channel=channel)
                    
                    flow.usage_count += 1
                    flow.last_used = timezone.now()
                    flow.save()
            else:
                print("ℹ️ No matching flow found.")
                
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
            
            print(f"📊 Message status: {message_id} -> {status_value}")
            print("message id"  ,  timestamp)
            
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
                    send_socket(
                        data_type='message_status_update',
                     payload = payload
                                        )
                    print("payload  sent to skovket " ,payload)
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
    



def send_message_socket(sreciver,  user ,channel_id ,  message, msg_type,
                        group_name="webhook_events",
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
        send_socket("error", {"error": error_msg})
        return {"ok": False, "error": error_msg.lower().replace(" ", "_")}
    
    ACCESS_TOKEN  = channel.access_token
    PHONE_NUMBER_ID = channel.phone_number_id

    
    # if not ACCESS_TOKEN or not PHONE_NUMBER_ID:
    #     send_socket("error", {"error": "Server configuration error: Missing Token or ID"})
    #     return {"ok": False, "error": "Server configuration missing"}

    try:
     
        if msg_type == "media_upload":
            media_url =''
            if request is not None:
                body = request.POST.get("body", "")
                media_type = request.POST.get("type", "text")
                file_obj = request.FILES.get("file")
                if not file_obj:
                    send_socket("error", {"error": "No file uploaded in request"})
                    return {"ok": False, "error": "no_file"}
                # نستخدم file_obj (InMemoryUploadedFile/File)
                uploaded_file = file_obj
                saved_filename = getattr(uploaded_file, "name", "uploaded")
                saved_mime = getattr(uploaded_file, "content_type", None)
            else:
                # نتوقع message dict مع مفاتيح data (base64 or dataURL), filename, mime, body, type
                if not isinstance(message, dict):
                    send_socket("error", {"error": "Invalid message payload for media_upload"})
                    return {"ok": False, "error": "invalid_payload"}

                body = message.get("body", "")
                media_type = message.get("type", "text")
                data = message.get("data")  # base64 or dataURL
                saved_filename = message.get("filename", "file")
                saved_mime = message.get("mime")

                if not data:
                    send_socket("error", {"error": "missing data for media_upload"})
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
                    send_socket("error", {"error": "failed to save uploaded file", "details": str(e)})
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
                send_socket("error", {"error": "upload connection failed", "details": str(e)})
                return {"ok": False, "error": "upload_failed", "details": str(e)}

            if fb_res.status_code not in (200, 201):
                _cleanup_paths(temp_input_path, temp_converted_path)
                send_socket("error", {"error": "whatsapp upload rejected", "details": fb_res.text})
                return {"ok": False, "error": "upload_rejected", "details": fb_res.text}

            fb_json = fb_res.json()
            media_id = fb_json.get("id")

            # اقرأ الملف ليحفظ محلياً لاحقاً
            try:
                with open(temp_input_path, "rb") as fh:
                    saved_local_bytes = fh.read()
            except Exception:
                saved_local_bytes = None

        # ----------------------------------------
        # الحالة JSON (نص أو template) كما في القديم
        # ----------------------------------------
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
                send_socket("error", {"error": "missing 'to' field"})
                return {"ok": False, "error": "missing_to"}

            if media_type == "template":
                template_data = payload.get("template")
                # media_type = payload.get("media_type") or payload.get("type") or "text"
            else:
                body = payload.get("body", "")
                media_id = payload.get("media_id")

    except Exception as e:
        _cleanup_paths(temp_input_path, temp_converted_path)
        send_socket("error", {"error": "request processing error", "details": str(e)})
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
            if not media_id:
                _cleanup_paths(temp_input_path, temp_converted_path)
                send_socket("error", {"error": "missing media_id"})
                return {"ok": False, "error": "missing_media_id"}

            send_payload["type"] = media_type
            send_payload[media_type] = {"id": media_id}
            if body and media_type != "audio":
                send_payload[media_type]["caption"] = body

        elif media_type == "template":
                if "template_name" in payload:
                    template_data = {
                        "name": payload.get("template_name"),
                        "language": payload.get("language"),
                        "components": payload.get("components", [])
                    }

        else:
            _cleanup_paths(temp_input_path, temp_converted_path)
            send_socket("error", {"error": f"unsupported type: {media_type}"})
            return {"ok": False, "error": "unsupported_type"}

        # إرسال لواتساب (HTTP)
        url = f"https://graph.facebook.com/v22.0/{PHONE_NUMBER_ID}/messages"
        headers = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}
        r = requests.post(url, headers=headers, json=send_payload, timeout=30)
        
    except Exception as e:
        _cleanup_paths(temp_input_path, temp_converted_path)
        send_socket("error", {"error": "api connection failed", "details": str(e)})
        return {"ok": False, "error": "api_connection_failed", "details": str(e)}


    saved_message_id = None
    status_code = getattr(r, "status_code", 500)
 
    
    if status_code in (200, 201):
        try:
            msg_kwargs = {"sender": to, "is_from_me": True}
            
          
            try:
                # 1. تحويل الرد إلى JSON
                response_data = r.json() 
                
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
                if media_id:
                    msg_kwargs["media_id"] = media_id

            saved_message = Message.objects.create(channel = channel , **msg_kwargs)

            saved_message_id = saved_message.id
            media_url = ""
            print('saved_message' , saved_message.media_type , saved_message.media_url , saved_message.media_file)
            if saved_message_id:
                try:
                 
                    msg_obj = Message.objects.get(id=saved_message_id)
                    print('🥰😜😜😜msg' , msg_obj)
                    if msg_obj.media_file:
                        media_url = msg_obj.media_file.url

                except Exception:
                    pass
 
            if saved_local_bytes and hasattr(saved_message, "media_file"):
                try:
                    ext = ""
                    if saved_mime:
                        if "ogg" in saved_mime: ext = ".ogg"
                        elif "mp4" in saved_mime: ext = ".mp4"
                        elif "jpeg" in saved_mime or "jpg" in saved_mime: ext = ".jpg"
                        elif "png" in saved_mime: ext = ".png"
                        elif "pdf" in saved_mime: ext = ".pdf"
                    fname = f"{media_id or 'file'}{ext}"
                    saved_message.media_file.save(fname, ContentFile(saved_local_bytes), save=True)
                    media_url = saved_message.media_file.url
                except Exception as ex_save:
                    print("Error saving local file:", ex_save)

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
        "body": body,
        "to": to,
        "media_type": media_type,
        "url": media_url,  # ✅ أضفنا الرابط هنا لكي يعرضه المتصفح
        "media_url": media_url # ✅ نسخة احتياطية حسب تسمية الجافاسكربت لديك
    }
    sidebar_payload = {
        "phone": to, # رقم المستقبل
        "name": to,  # أو ابحث عن الاسم في Contact إذا أردت
        "snippet": snippet,
        "timestamp": timezone.now().strftime("%H:%M"),
        "unread": 0, # رسالة صادرة، إذاً المقروء 0
        "last_status": "sent", # الحالة المبدئية
        "fromMe": True, # مهم جداً لإظهار الأيقونة
        "channel_id": channel_id
    }
    send_socket("finished",final_payload)
    send_socket(
        "new_message_received", # نستخدم نفس النوع لكي يعالجها الفرونت إند بنفس الطريقة (نقل للأعلى)
        {
            "contact": sidebar_payload,
             "message": None 
        })


    # للإستخدام الداخلي نعيد dict
    return {"ok": status_code in (200,201), "result": final_payload}
