"""
WSGI config for disound project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'disound.settings')

application = get_wsgi_application()








import os
from django.core.wsgi import get_wsgi_application

# 1. استيراد WhiteNoise
from whitenoise import WhiteNoise 

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'disound.settings')

application = get_wsgi_application()

# 2. تغليف التطبيق بـ WhiteNoise يدوياً
# هذا يجبر السيرفر على استخدام WhiteNoise لخدمة الملفات الساكنة
# ويحدد المسار الصحيح للملفات المجمعة
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
static_root = os.path.join(base_dir, 'staticfiles')

application = WhiteNoise(application, root=static_root)
# (اختياري) إضافة ضغط وتخزين مؤقت
application.add_files(static_root, prefix='static/')