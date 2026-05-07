# import os
# from django.core.asgi import get_asgi_application
# from channels.routing import ProtocolTypeRouter, URLRouter
# from channels.auth import AuthMiddlewareStack

# from discount.channel import routing

# os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'disound.settings')

# django_asgi_app = get_asgi_application()

# application = ProtocolTypeRouter({
#     "http": django_asgi_app,
#     "websocket": AuthMiddlewareStack(
#         URLRouter(
#             routing.websocket_urlpatterns
#         )
#     ),
# })



import os
import django # 1. استيراد جانغو

# 2. ضبط متغير البيئة أولاً (قبل أي استيراد آخر)
# تأكد أن 'disound.settings' هو المسار الصحيح لملف settings.py الخاص بك
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'disound.settings')

# 3. تهيئة جانغو يدوياً (هذا هو السطر السحري الذي يحل المشكلة)
django.setup()

# 4. الآن يمكننا استيراد المكتبات التي تعتمد على المودلز والإعدادات
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from discount.channel import routing # تأكد أن هذا المسار يطابق هيكل ملفاتك

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        URLRouter(
            routing.websocket_urlpatterns
        )
    ),
})

 
# /Users/pro/Desktop/disound/disound/settings.py