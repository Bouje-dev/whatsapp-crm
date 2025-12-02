import json 
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
# from django.contrib.auth.models import User
from discount.models import GroupMessages , groupchat
from  discount.models import CustomUser as User




class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()
    

 
from asgiref.sync import sync_to_async
 

from ..whatssapAPI.process_messages import send_message_socket  


 
class WebhookConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.channel_layer.group_add("webhook_events", self.channel_name)
        self.user = self.scope["user"]
        await self.accept()

      

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard("webhook_events", self.channel_name)
       

    async def receive(self, text_data=None, bytes_data=None):
        """
        استقبال الرسائل من الواجهة (frontend).
        نتوقع JSON يضبط الحقول:
          - type: "text" | "media_upload" | "client_message" | ...
          - reciver (أو to)
          - body (نص)
          - file (base64 string) -- في حالة media_upload
          - filename, mime (اختياريان)
        """
        try:
            if text_data:
                data = json.loads(text_data)
                
            else:
                # لا نتعامل هنا مع bytes_data في هذا المثال
                await self.send(json.dumps({"type": "error", "message": "No text data received"}))
                return
        except Exception as e:
            await self.send(json.dumps({"type": "error", "message": f"invalid json: {e}"}))
            return
        command_type = data.get('type')
        payload_content = data.get('payload', {})
        # socket_type = payload_content.get("type")
        reciver = None
        body = None
        msg_type = None
        c_id = payload_content.get('channel_id')
        
        if not c_id :
            return await self.send(json.dumps({"type" :"error" , "message" : "missing Channel ID "}))
        
        if command_type == 'send_message':
            msg_type = payload_content.get("msg_type") or payload_content.get("type") or "text"
            reciver = payload_content.get("reciver") or payload_content.get("to")
            body = payload_content.get("body", "")
            file_b64 = payload_content.get("file")
            filename = payload_content.get("filename")
            mime = payload_content.get("mime")
             

      
        if not reciver:
            await self.send(json.dumps({"type": "error", "message": "missing 'reciver' (or 'to') field"}))
            return
        try:
            if msg_type == "media_upload":
                if not file_b64:
                    await self.send(json.dumps({"type": "error", "message": "missing file data for media_upload"}))
                    return
                # نبني كائن message لتمريره إلى send_message_socket
                message_payload = {
                    "data": file_b64,
                    "filename": filename or "file",
                    "mime": mime,
                    "body": body,
                    "type": payload_content.get("type") or payload_content.get("file_type") or "unknown"
                }
            else:
                # نص أو template أو غيره
                message_payload = {
                    "body": body,
                    "media_id": payload_content.get("media_id"),
                    "template": payload_content.get("template"),
                    "media_type": payload_content.get("media_type", "text")
                }

            # استدعاء دالتك المتزامنة بطريقة غير محجوزة (تشغيل في threadpool)
            # 🔥 تصحيح ترتيب المعاملات: (sreciver, user, channel_id, message, msg_type, ...)
            result = await sync_to_async(send_message_socket)(
                reciver,           # sreciver
                self.user,         # user
                c_id,              # channel_id
                message_payload,   # message
                msg_type           # msg_type
            )

        
            if isinstance(result, dict):
              
                status = 200 if result.get("ok") else 400
                payload = result.get("result") or {"info": result}
                await self.send(text_data=json.dumps({
                    "type": "send_result",
                    "status": status,
                    "payload": payload
                }))
            else:
                # حالة عامة
                await self.send(text_data=json.dumps({
                    "type": "send_result",
                    "status": 200,
                    "payload": {"message": str(result)}
                }))

        except Exception as e:
            # لو في استثناء أثناء المعالجة نعيد رسالة خطأ للواجهة
            await self.send(text_data=json.dumps({
                "type": "error",
                "message": f"server processing error: {str(e)}"
            }))

    # async def broadcast_event(self, event):
    #     """
    #     استقبال أحداث المجموعة (group_send) — هذا يرسل للعميل النهائي.
    #     نتوقع event يحتوي على الحقول: status, payload, sender (كما صممنا سابقًا)
    #     """
    #     status = event.get("status")
    #     payload = event.get("payload", {})
    #     sender = event.get("sender")
 
    #     print("WebhookConsumer received event:", status, sender, payload)

    #     # إرسال للعميل
    #     await self.send(text_data=json.dumps({
    #         "type": "webhook_message",
    #         "status": status,
    #         "payload": payload,
    #         "sender": sender
    #     }))
    
    async def broadcast_event(self, event):
        
        
        dynamic_type = event['data_type'] 
        payload_data = event['payload']
      
        await self.send(text_data=json.dumps({
            
            "data_type": dynamic_type, 
            "payload": payload_data
        }))