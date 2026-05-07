from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

def send_socket(data_type, payload, group_name, channel_name=None):
    """
    دالة مركزية لإرسال الأحداث من أي مكان في الباك إند إلى الويب سوكت
    """
    layer = get_channel_layer()
    
    # تجهيز الحدث الذي سيفهمه الـ Consumer
    event = {
        "type": "broadcast_event", # اسم الدالة التي سنضيفها في الـ Consumer بالأسفل
        "data_type": data_type,    # المفتاح الذي يعتمد عليه الـ JS Switch
        "payload": payload
    }

    try:
        if channel_name:
            
            async_to_sync(layer.send)(channel_name, event)
        else:
            
            async_to_sync(layer.group_send)(group_name, event)
          
            
    except Exception as e:
        print(f"❌ Failed to send socket event: {e}")