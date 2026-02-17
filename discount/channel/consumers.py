import json
from tokenize import group 
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
# from django.contrib.auth.models import User
from discount.models import GroupMessages , groupchat
from  discount.models import CustomUser as User
# from discount.models import CustomUser
from django.utils import timezone



class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()
    

 
from asgiref.sync import sync_to_async
 

from ..whatssapAPI.process_messages import send_message_socket  


 
# class WebhookConsumer(AsyncWebsocketConsumer):
#     async def connect(self):
         
#         self.user = self.scope["user"]
        
        
#         if self.user.is_authenticated:
  
#             await self.update_user_status(self.user, True)
#             await self.channel_layer.group_add(
#             "admin_updates",  # نفس اسم الجروب الذي ترسل له
#             self.channel_name
#         )
            
#             if hasattr(self.user, 'is_team_admin') and self.user.is_team_admin:
              
#                 self.team_id = self.user.is_team_admin.id
#             else:
              
#                 self.team_id = self.user.id

#             self.team_group_name = f"team_updates_{self.team_id}"

#             await self.channel_layer.group_add(self.team_group_name, self.channel_name)


#             await self.channel_layer.group_send(
#                 self.team_group_name , 
#                 {
#                     "type": "user_status_change",
#                     "user_id": self.user.id,
#                     "status": "online"
#                 }
#             )
               
#         await self.accept()

      

#     async def disconnect(self, close_code):
#         if self.user.is_authenticated:
#             # 1. تحديث الحالة إلى "غير متصل"
#             await self.update_user_status(self.user, False)
            
#             # 2. إبلاغ الأدمن
#             await self.channel_layer.group_send(
#                 self.team_group_name , 
#                 {
#                     "type": "user_status_change",
#                     "user_id": self.user.id,
#                     "status": "offline"
#                 }
#             )
#         await self.channel_layer.group_discard("webhook_events", self.channel_name)
       

#     async def receive(self, text_data=None, bytes_data=None):
      
#         try:
#             if text_data:
#                 data = json.loads(text_data)
                
#             else:
#                 # لا نتعامل هنا مع bytes_data في هذا المثال
#                 await self.send(json.dumps({"type": "error", "message": "No text data received"}))
#                 return
#         except Exception as e:
#             await self.send(json.dumps({"type": "error", "message": f"invalid json: {e}"}))
#             return
#         is_internal_note = data.get('is_internal_note', False)
#         command_type = data.get('type')
#         payload_content = data.get('payload', {})
#         # socket_type = payload_content.get("type")
#         reciver = None
#         body = None
#         msg_type = None
#         c_id = payload_content.get('channel_id')
        
#         if not c_id :
#             return await self.send(json.dumps({"type" :"error" , "message" : "missing Channel ID "}))
        
        # if command_type == 'send_message':
        #     msg_type = payload_content.get("msg_type") or payload_content.get("type") or "text"
        #     reciver = payload_content.get("reciver") or payload_content.get("to")
        #     body = payload_content.get("body", "")
        #     file_b64 = payload_content.get("file")
        #     filename = payload_content.get("filename")
        #     mime = payload_content.get("mime")
             

      
        # if not reciver:
        #     await self.send(json.dumps({"type": "error", "message": "missing 'reciver' (or 'to') field"}))
        #     return
        # try:
        #     if msg_type == "media_upload":
        #         if not file_b64:
        #             await self.send(json.dumps({"type": "error", "message": "missing file data for media_upload"}))
        #             return
        #         # نبني كائن message لتمريره إلى send_message_socket
        #         message_payload = {
        #             "data": file_b64,
        #             "filename": filename or "file",
        #             "mime": mime,
        #             "body": body,
        #             "type": payload_content.get("type") or payload_content.get("file_type") or "unknown"
        #         }
        #     else:
        #         # نص أو template أو غيره
        #         message_payload = {
        #             "body": body,
        #             "media_id": payload_content.get("media_id"),
        #             "template": payload_content.get("template"),
        #             "media_type": payload_content.get("media_type", "text")
        #         }
#             if not is_internal_note:
#                 result = await sync_to_async(send_message_socket)(
#                 reciver,           
#                 self.user,        
#                 c_id,              
#                 message_payload,   
#                 msg_type    )
#             else: 
#                 await self.channel_layer.group_send(
#                 self.team_group_name , 
#                 event ={
#                     "type": "broadcast_event",
#                     "data_type": "internal_Note",
#                     "payload": save_message(self, self.user, message_payload, is_internal_note)
#                 }
#             )
#                 @database_sync_to_async
#                 def save_message(self, user, content, is_internal):
#                     from discount.models import Message
#                     return Message.objects.create(

#                         user=user,
#                         content=content,
#                         is_internal= is_internal, 
#                         channel_id=c_id,
#                         message_type=msg_type,
#                         reciver=reciver,
#                         body=body,
#                         media_id=payload_content.get("media_id"),
#                         template=payload_content.get("template"),
#                         media_type=payload_content.get("media_type", "text"),
#                     )
                
 

        
#             if isinstance(result, dict):
              
#                 status = 200 if result.get("ok") else 400
#                 payload = result.get("result") or {"info": result}
#                 await self.send(text_data=json.dumps({
#                     "type": "send_result",
#                     "status": status,
#                     "payload": payload
#                 }))
#             else:
#                 # حالة عامة
#                 await self.send(text_data=json.dumps({
#                     "type": "send_result",
#                     "status": 200,
#                     "payload": {"message": str(result)}
#                 }))

#         except Exception as e:
#             # لو في استثناء أثناء المعالجة نعيد رسالة خطأ للواجهة
#             await self.send(text_data=json.dumps({
#                 "type": "error",
#                 "message": f"server processing error: {str(e)}"
#             }))

 
    
#     async def broadcast_event(self, event):
        
        
#         dynamic_type = event['data_type'] 
#         payload_data = event['payload']
      
#         await self.send(text_data=json.dumps({
            
#             "data_type": dynamic_type, 
#             "payload": payload_data
#         }))

#     async def user_status_change(self, event):
#         # 1. استقبال البيانات من الجروب
#         user_id = event['user_id']
#         status = event['status']
 
#         # 2. إرسالها فعلياً للمتصفح (Frontend) عبر السوكيت
#         await self.send(text_data=json.dumps({
#             'data_type': 'user_status_change',  
#             'user_id': user_id,
#             'status': status
#         }))


#     @database_sync_to_async
#     def update_user_status(self, user, status):
#         # نعيد جلب المستخدم للتأكد
#         u = User.objects.get(id=user.id)
#         u.is_online = status
#         u.last_seen = timezone.now()
#         u.save()



import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone
from asgiref.sync import sync_to_async

# تأكد من استيراد المودلز الخاصة بك بشكل صحيح
from django.contrib.auth import get_user_model
# from discount.models import Message, WhatsAppChannel # استورد المودلز الخاصة بك هنا

User = get_user_model()

class WebhookConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope["user"]
        
        if self.user.is_authenticated:
            # 1. تحديث الحالة
            await self.update_user_status(self.user, True)
            
            # 2. الانضمام لجروب الأدمن العام (اختياري حسب منطقك)
            await self.channel_layer.group_add("admin_updates", self.channel_name)

            # 3. 🔥 تحديد معرف الفريق (Team ID) بالطريقة الصحيحة 🔥
            
            # الحالة أ: هل المستخدم هو مدير الفريق نفسه؟
            if self.user.is_team_admin:
                self.team_id = self.user.id
            
            elif self.user.team_admin_id: 
                self.team_id = self.user.team_admin_id
                
            # الحالة ج: مستخدم عادي مستقل
            else:
                self.team_id = self.user.id

            # 4. تكوين اسم المجموعة
            self.team_group_name = f"team_updates_{self.team_id}"

            # 5. الانضمام وإرسال الحالة
            await self.channel_layer.group_add(self.team_group_name, self.channel_name)

            await self.channel_layer.group_send(
                self.team_group_name, 
                {
                    "type": "user_status_change",
                    "user_id": self.user.id,
                    "status": "online"
                }
            )
            
        await self.accept()


    async def disconnect(self, close_code):
        if self.user.is_authenticated:
            # 1. تحديث الحالة إلى "غير متصل"
            await self.update_user_status(self.user, False)
            
            # 2. إبلاغ الفريق (باستخدام نفس اسم المجموعة الديناميكي)
            # نتحقق من وجود السمة لتجنب الأخطاء إذا فشل الاتصال من البداية
            if hasattr(self, 'team_group_name'):
                await self.channel_layer.group_send(
                    self.team_group_name, 
                    {
                        "type": "user_status_change",
                        "user_id": self.user.id,
                        "status": "offline"
                    }
                )
                
                # مغادرة المجموعة
                await self.channel_layer.group_discard(
                    self.team_group_name,
                    self.channel_name
                )

    async def receive(self, text_data=None, bytes_data=None):
        try:
            if text_data:
                data = json.loads(text_data)
                 
            else:
                await self.send(json.dumps({"type": "error", "message": "No text data received"}))
                return
        except Exception as e:
            await self.send(json.dumps({"type": "error", "message": f"invalid json: {e}"}))
            return

        # استخراج البيانات الأساسية
         
        command_type = data.get('type')
        payload_content = data.get('payload', {}) or data  
        
       
        c_id = payload_content.get('channel_id') or data.get('channel_id')
        is_internal_note = payload_content.get('is_internal_note' , False)

        if command_type == 'chat_activity':
            
            action = payload_content.get('action') # 'enter' or 'leave'
            chat_id = payload_content.get('phone_number') # أو contact_id حسب هيكلتك
            
            if chat_id:
                # اسم مجموعة المحادثة (يجب أن يكون فريداً لكل محادثة)
                # نستخدم prefix مختلف لتجنب التداخل مع مجموعات أخرى
                room_group_name = f"activity_chat_{chat_id}"

                # 1. إذا كان الفعل دخول -> نضم المستخدم للمجموعة
                if action == 'enter':
                    await self.channel_layer.group_add(
                        room_group_name,
                        self.channel_name
                    )
                
                # 2. إذا كان الفعل خروج -> نزيله من المجموعة
                elif action == 'leave':
                    await self.channel_layer.group_discard(
                        room_group_name,
                        self.channel_name
                    )

                if action in ['enter', 'leave', 'presence_sync']:
                    await self.channel_layer.group_send(
                        room_group_name,
                        {
                    "type": "broadcast_event", # نستخدم نفس دالة البث الموحدة
                    "data_type": "collision_update", # نوع البيانات للفرونت إند
                    "payload": {
                        "chat_id": chat_id,
                        "user_id": self.user.id,
                        "user_name": self.user.first_name or self.user.user_name or self.user.username or "Agent",
                        "action": action # 'enter' or 'leave'
                    }
                }
            )


        if not c_id:
            return await self.send(json.dumps({"type": "error", "message": "missing Channel ID"}))
        # داخل دالة receive في WebhookConsumer
         


      
         
        if command_type == 'send_message':
            msg_type = payload_content.get("msg_type") or payload_content.get("type") or "text"
            reciver = payload_content.get("reciver") or payload_content.get("to")
            body = payload_content.get("body", "") 
            caption = payload_content.get("caption", "") 
            file_b64 = payload_content.get("file")
            filename = payload_content.get("filename")
            mime = payload_content.get("mime")
             

            if not reciver:
                await self.send(json.dumps({"type": "error", "message": "missing 'reciver' (or 'to') field"}))
                return
            
            if msg_type == "media_upload":
                if not file_b64:
                    await self.send(json.dumps({"type": "error", "message": "missing file data for media_upload"}))
                    return
                
                message_payload = {
                    "data": file_b64,
                    "filename": filename or "file",
                    "mime": mime,
                    "body": body,
                    "type": payload_content.get("type") or payload_content.get("file_type") or "unknown"
                }
            elif msg_type in ['image', 'video', 'audio', 'document']:
                message_payload = {
                    "body": caption,
                    "media_id": payload_content.get("media_id"),
                    "template": payload_content.get("template"),
                    "media_type": msg_type,
                    "media_url": payload_content.get("file") or payload_content.get("media_url"),
                }
            else:
                message_payload = {
                    "body": body,
                    "media_id": payload_content.get("media_id"),
                    "template": payload_content.get("template"),
                }
            try:
                if is_internal_note:
                    # 1. الحفظ في قاعدة البيانات
                    saved_msg = await self.save_message_db(
                        self.user, 
                        c_id, 
                        reciver, 
                        message_payload, 
                        is_internal=True 
                    )
                    print('its internal note')

                    # 2. البث للمجموعة (ليراها الموظفون الآخرون)
                    await self.channel_layer.group_send(
                        self.team_group_name,
                        {
                            "type": "broadcast_event", # الموجه الموحد
                            "data_type": "note_message", # نوع البيانات للفرونت إند
                            "payload": {
                                "id": saved_msg.id,
                                "body": body,
                                "sender_id": self.user.id,
                                "sender_name": self.user.first_name or "Agent",
                                "is_internal_note": True,
                                "created_at": saved_msg.created_at.strftime('%Y-%m-%d %H:%M') if hasattr(saved_msg, 'created_at') else "",
                                "channel_id": c_id,
                                "reciver": reciver ,
                                "type": "note",
                                "user" : self.user.username,
                                "timestamp" : saved_msg.created_at.strftime('%Y-%m-%d %H:%M'),
                                "contact":{
                                    "phone" : reciver,
                            
                                }
                            }

                        }
                    )
                    
                    # 3. إعلام المرسل بالنجاح
                    await self.send(json.dumps({
                        "type": "send_result",
                        "status": 200,
                        "payload": {"info": "Internal note saved"}
                    }))

                else:
                     
                    result = await sync_to_async(send_message_socket)(
                        reciver,           
                        self.user,        
                        c_id,              
                        message_payload,   
                        msg_type ,
                        group_name = self.team_group_name
                    )
                    
                    status_code = 200 if isinstance(result, dict) and result.get("ok") else 400
                    await self.send(text_data=json.dumps({
                        "type": "send_result",
                        "status": status_code,
                        "payload": result
                    }))

            except Exception as e:
                print(f"Error processing message: {e}")
                await self.send(text_data=json.dumps({
                    "type": "error",
                    "message": f"Processing error: {str(e)}"
                }))



    # --- Handlers (معالجات الأحداث القادمة من group_send) ---

    async def broadcast_event(self, event):
        """
        دالة عامة لإرسال أي بيانات للفرونت إند
        """
        await self.send(text_data=json.dumps({
            "data_type": event['data_type'], 
            "payload": event['payload']
        }))

    async def user_status_change(self, event):
        """
        خاص بتغيير حالة الاتصال
        """
        await self.send(text_data=json.dumps({
            'data_type': 'user_status_change',  
            'user_id': event['user_id'],
            'status': event['status']
        }))

    # --- Database Helpers (دوال قاعدة البيانات) ---
    
    @database_sync_to_async
    def update_user_status(self, user, status):
        try:
            u = User.objects.get(id=user.id)
            u.is_online = status
            u.last_seen = timezone.now()
            u.save()
            from discount.activites import log_activity_async
            log_activity_async(
                'ws_connect' if status else 'ws_disconnect',
                f"{'Connected' if status else 'Disconnected'}: {u.user_name or u.username}",
                user=u,
            )
        except User.DoesNotExist:
            pass

    @database_sync_to_async
    def save_message_db(self, user, channel_id, reciver, payload, is_internal):
        # استيراد المودلز هنا لتجنب مشاكل AppRegistryNotReady
        from discount.models import Message, WhatsAppChannel, Contact
        
        body = payload.get("body", "")
        msg_type = payload.get("type", "text")
        
        # محاولة جلب كائن القناة
        try:
            channel = WhatsAppChannel.objects.get(id=channel_id)
        except WhatsAppChannel.DoesNotExist:
            channel = None

        # إنشاء الرسالة
        
        msg = Message.objects.create(
            user = user,
            sender= reciver,
            channel=channel,  
            # channel_id=channel_id, # استخدم هذا لو كان الحقل IntegerField
             
            body=body,
            media_type=msg_type,
            is_internal=is_internal,
            is_from_me=True,  
            status='read',
            created_at= timezone.now(),
             
            type = 'note'

            
        )

        #  Message.objects.create(
        #                         channel=channel if channel else None,
        #                         sender=recipient,
        #                         body=body,
        #                         is_from_me=True,
        #                         media_type=msg_type if msg_type in ["image", "video", "audio", "document"] else None,
        #                         media_id= media_id,
        #                         media_url = media_url , 
        #                         message_id= res.json().get("messages", [{}])[0].get("id")
        #                     )
        return msg

