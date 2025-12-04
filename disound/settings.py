"""
Django settings for disound project.
Cleaned & Optimized for Railway + Brevo + Cloudinary
"""

import os
from pathlib import Path
import dj_database_url
from dotenv import load_dotenv # تأكد من تثبيت: pip install python-dotenv

# 1. تحميل المتغيرات المحلية من ملف .env (لن يؤثر على السيرفر)
load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# =========================================================
# 🔐 الأمان والإعدادات الأساسية
# =========================================================

# قراءة المفتاح من البيئة، أو استخدام مفتاح احتياطي للتطوير فقط
SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-dev-key-change-in-prod')

# تحديد وضع التطوير (في Railway اجعل المتغير DEBUG = False)
DEBUG = os.environ.get('DEBUG', 'True') == 'True'

# السماح بجميع النطاقات (يمكنك تحديدها لاحقاً للأمان)
ALLOWED_HOSTS = ['*']

# النطاقات الموثوقة لـ CSRF (ضروري لـ Railway و Ngrok)
CSRF_TRUSTED_ORIGINS = [
    'https://*.up.railway.app',
    'https://*.ngrok-free.dev',
    'http://localhost:8000',
    'http://127.0.0.1:8000',
]

# =========================================================
# 📦 التطبيقات المثبتة
# =========================================================

INSTALLED_APPS = [
    # --- تطبيقات خارجية (يجب أن تكون في البداية للملفات الثابتة) ---
    'daphne',            # للسوكيت (يجب أن يكون الأول)
    'cloudinary_storage',# لتخزين الميديا
    'django.contrib.staticfiles',
    'cloudinary',        # مكتبة كلاوديناري

    # --- تطبيقات جانغو الأساسية ---
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',

    # --- تطبيقاتك ---
    'discount',
    
    # --- أدوات أخرى ---
    'corsheaders',
    'channels',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    "whitenoise.middleware.WhiteNoiseMiddleware", # للملفات الثابتة
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'disound.urls'
CORS_ALLOW_ALL_ORIGINS = True

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# إعدادات السيرفر (WSGI / ASGI)
WSGI_APPLICATION = 'disound.wsgi.application'
ASGI_APPLICATION = 'disound.asgi.application'


# =========================================================
# 🗄️ قاعدة البيانات (Database)
# =========================================================

DATABASES = {
    'default': dj_database_url.config(
        # في السيرفر سيقرأ DATABASE_URL، وفي جهازك سينشئ db.sqlite3
        default=os.environ.get('DATABASE_URL', f'sqlite:///{BASE_DIR / "db.sqlite3"}'),
        conn_max_age=600
    )
}

# مودل المستخدم المخصص (الحل لمشكلة الرفع السابقة)
AUTH_USER_MODEL = 'discount.CustomUser'


# =========================================================
# ⚡ Redis & Channels (WebSockets)
# =========================================================

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [os.environ.get('REDIS_URL', 'redis://127.0.0.1:6379')],
        },
    },
}

# =========================================================
# 📧 إعدادات البريد (Brevo SMTP) - المصححة
# =========================================================

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = os.environ.get('EMAIL_HOST', 'smtp-relay.brevo.com')
# نقرأ المنفذ من البيئة، الافتراضي 587 (لكن في Railway سنغيره لـ 2525)
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', 587)) 
EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', 'True') == 'True'
EMAIL_USE_SSL = os.environ.get('EMAIL_USE_SSL', 'False') == 'True'

EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD')
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', EMAIL_HOST_USER)


# =========================================================
# ☁️ Cloudinary (Media Storage)
# =========================================================

CLOUDINARY_STORAGE = {
    'CLOUD_NAME': os.environ.get('CLOUDINARY_CLOUD_NAME'),
    'API_KEY': os.environ.get('CLOUDINARY_API_KEY'),
    'API_SECRET': os.environ.get('CLOUDINARY_API_SECRET'),
}

# استخدام Cloudinary للميديا فقط (الصور/الفيديو)
DEFAULT_FILE_STORAGE = 'cloudinary_storage.storage.MediaCloudinaryStorage'

# استخدام Whitenoise للملفات الثابتة (CSS/JS)
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'


# =========================================================
# 📂 الملفات الثابتة (Static & Media)
# =========================================================

STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')]

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')


# =========================================================
# 🔐 إعدادات الأمان (HTTPS) - تعمل تلقائياً في السيرفر
# =========================================================

if not DEBUG:
    # إعدادات السيرفر (HTTPS)
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https') # 🔥 هذا هو السطر المنقذ
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_BROWSER_XSS_FILTER = True
else:
    # إعدادات Localhost
    SECURE_SSL_REDIRECT = False
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False
# إعدادات أخرى
DATA_UPLOAD_MAX_MEMORY_SIZE = 104857600  # 100 MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 104857600  # 100 MB
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'