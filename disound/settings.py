
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent

import os
import dj_database_url
from dotenv import load_dotenv
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
load_dotenv(os.path.join(BASE_DIR, '.env'))

# Google Sheets: support JSON in env (multi-line .env can be truncated by load_dotenv) or path to file
_gs_json = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_JSON", "").strip()
if not _gs_json or "client_email" not in _gs_json:
    _gs_file = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_FILE", "").strip()
    if _gs_file and os.path.isfile(_gs_file):
        with open(_gs_file, "r", encoding="utf-8") as _f:
            _gs_json = _f.read().strip()
    elif not _gs_json or "client_email" not in _gs_json:
        _env_path = os.path.join(BASE_DIR, ".env")
        if os.path.isfile(_env_path):
            with open(_env_path, "r", encoding="utf-8") as _f:
                _content = _f.read()
            _key = "GOOGLE_SHEETS_CREDENTIALS_JSON"
            _idx = _content.find(_key)
            if _idx >= 0:
                _eq = _content.find("=", _idx + len(_key))
                if _eq < 0:
                    _eq = _idx + len(_key)
                _start = _eq + 1
                while _start < len(_content) and _content[_start] in " \t\r\n":
                    _start += 1
                _quote = _content[_start : _start + 1] if _start < len(_content) else ""
                if _quote in ("'", '"'):
                    _end = _start + 1
                    while _end < len(_content):
                        _ch = _content[_end]
                        if _ch == _quote and _content[_end - 1 : _end] != "\\":
                            break
                        _end += 1
                    _gs_json = _content[_start + 1 : _end].strip()
GOOGLE_SHEETS_CREDENTIALS_JSON = _gs_json if _gs_json else ""

# Display-only: service account email for Integrations UI. Set from env or extract from JSON.
_gs_email = os.environ.get("GOOGLE_SHEETS_SERVICE_ACCOUNT_EMAIL", "").strip()
if not _gs_email and _gs_json:
    try:
        import json as _json
        _parsed = _json.loads(_gs_json)
        if isinstance(_parsed, dict):
            _gs_email = (_parsed.get("client_email") or "").strip()
    except Exception:
        pass
GOOGLE_SHEETS_SERVICE_ACCOUNT_EMAIL = _gs_email or ""

SECRET_KEY = 'django-insecure-8*lzwv5+jl80b65ev5=atx-bn2&-bf^jk7)y&886_xbf2)m_%('

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

# Admin: allow editing user Plan from Django admin. Set to False in production to lock plan changes.
ALLOW_ADMIN_PLAN_EDITS = os.environ.get("ALLOW_ADMIN_PLAN_EDITS", "true").lower() in ("true", "1", "yes")

# ALLOWED_HOSTS = []
CSRF_TRUSTED_ORIGINS = [
   'https://rufus-unshotted-corina.ngrok-free.dev' ,
   'https://rufus-unshotted-corina.ngrok-free.dev/',
   'app.waselytics.com'
   
]

# APPEND_SLASH=False
# Application definition

INSTALLED_APPS = [
    #  'discount.apps.DiscountConfig',  # يجب أن يكون قبل 'django.contrib.admin'
    'daphne',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'discount',
    'orders',
    'reputation',
    'ai_assistant',
    'corsheaders',
    'channels',
    'storages',
    'anymail',
    'django_filters',
]

 
MIDDLEWARE = [
        'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    "whitenoise.middleware.WhiteNoiseMiddleware",
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'discount.middleware.AccountActivationMiddleware',
]

ROOT_URLCONF = 'disound.urls'
CORS_ALLOW_ALL_ORIGINS = True


TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': ['templates'],
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

WSGI_APPLICATION = 'disound.wsgi.application'
ASGI_APPLICATION = 'disound.asgi.application'


# CHANNEL_LAYERS = {
#     "default": {
#         "BACKEND": "channels_redis.core.RedisChannelLayer",
#         "CONFIG": {
#             "hosts": [("127.0.0.1", 6379)],
#         },
#     },
# }

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [os.environ.get('REDIS_URL', 'redis://127.0.0.1:6379')],
        },
    },
}

 
DATABASES = {
    'default': dj_database_url.config(
        default=os.environ.get('DATABASE_URL', f'sqlite:///{BASE_DIR / "db.sqlite3"}'),
        conn_max_age=600
    )
}


 



# Password validation
# https://docs.djangoproject.com/en/4.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/4.2/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True

# ✅ الإعدادات الجديدة والصحيحة لـ Django 4.2+
 
 

# STATIC_URL = 'static/'
# STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
# STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')]


# DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
# STATICFILES_STORAGE = 'whitenoise.storage.CompressedStaticFilesStorage'

# STATICFILES_STORAGE = 'whitenoise.storage.CompressedStaticFilesStorage'
EMAIL_PORT = 587

 
ALLOWED_HOSTS = ['*']  
 

DATA_UPLOAD_MAX_MEMORY_SIZE = 104857600  # 100 MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 104857600  # 100 MB

 
 
 
 
 
ALLOWED_HOSTS = ['*']
CSRF_TRUSTED_ORIGINS = ['https://*.up.railway.app', 'https://app.waselytics.com',
'https://*waselytics.com', 'https://waselytics.com', 'https://*.127.0.0.1', 'https://*.localhost']


 # قراءة المفاتيح من Railway/Environment
# AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID')
# AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')
# AWS_STORAGE_BUCKET_NAME = os.environ.get('AWS_STORAGE_BUCKET_NAME')
# AWS_S3_REGION_NAME = 'eu-north-1' # ⚠️ استبدلها بالمنطقة التي اخترتها في الخطوة 2

# # إعدادات الملفات
# AWS_S3_FILE_OVERWRITE = False     # لا تحذف الملف القديم إذا رفعنا ملفاً بنفس الاسم
# AWS_DEFAULT_ACL = 'public-read'   # اجعل الملفات عامة ومقروءة للجميع
# AWS_S3_VERIFY = True
# AWS_QUERYSTRING_AUTH = False      # اجعل الرابط مباشراً ونظيفاً بدون توقيعات مؤقتة

# # إخبار Django باستخدام S3 للميديا فقط
# STORAGES = {
#     "default": {
#         "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
#     },
#     "staticfiles": {
#         "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
#     },
# }

# الرابط الأساسي للميديا
# MEDIA_URL = f'https://{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com/'
 
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
if not DEBUG:
    #  (HTTPS)
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_BROWSER_XSS_FILTER = True
else:
    # (HTTP)
    SECURE_SSL_REDIRECT = False
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False


AUTH_USER_MODEL = 'discount.CustomUser'


# EAALZBubBgmq0BQHmIewxaHrZBwF67lMsRRj012KOo8hNl8ab6agSmVSHqkzZCNbhHZChionX5hJwiXHMYu7pLI7ZANqxFKoBZAgrBv6X0jarDAwIyMBEYoEvQNXzWKrQocyG7cR7m8Hftt9fTtvPAZCimPA9qMKfXo20qz0MQlzjzUnLbyVzx5PSzbaYA7oyfNK6AZDZD



KEY = 'k76TMkpykna7wyWyNS4KYdZC-NK_XfoXvWMPLacwVAY='

 
 
# EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
# EMAIL_HOST = 'smtp.hostinger.com'       
# EMAIL_PORT = 587                        
# EMAIL_USE_SSL = True                    
# EMAIL_USE_TLS = False                   


 
# EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER') 
# EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD')


# DEFAULT_FROM_EMAIL = EMAIL_HOST_USER 
#  'Waselytics Security <support@waselytics.com>'
# SERVER_EMAIL = 'support@waselytics.com'

EMAIL_BACKEND = "anymail.backends.brevo.EmailBackend"
ANYMAIL = {
    "BREVO_API_KEY": os.environ.get('BREVO_API_KEY'),
}

 

# ✅ 3. تأكد أن هذا البريد مطابق للذي وثقته في SendGrid
DEFAULT_FROM_EMAIL = "Waselytics Support <support@waselytics.com>"
SERVER_EMAIL = "support@waselytics.com"

# AI Assistant (OpenAI)
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")









if DEBUG:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        }
    }
else:
    # في الإنتاج نستخدم Redis
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': os.environ.get('REDIS_URL', 'redis://127.0.0.1:6379'),
        }
    }




# ==========================================
#  STATIC & MEDIA FILES SETTINGS (CLEANED)
# ==========================================

# 1. إعدادات الروابط (يجب أن تبدأ بـ / دائماً)
STATIC_URL = '/static/'  # ✅ تم التصحيح: أضيفت الشرطة المائلة في البداية
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')]

# 2. إعدادات S3 (للميديا فقط - الصور والفيديوهات)
AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')
AWS_STORAGE_BUCKET_NAME = os.environ.get('AWS_STORAGE_BUCKET_NAME')
AWS_S3_REGION_NAME = 'eu-north-1' # تأكد أن المنطقة صحيحة
AWS_S3_FILE_OVERWRITE = False
AWS_DEFAULT_ACL = 'public-read'
AWS_S3_VERIFY = True
AWS_QUERYSTRING_AUTH = False

# 3. نظام التخزين الجديد (Django 4.2+)
STORAGES = {
    "default": {
        # تخزين الميديا (الصور) على S3
        "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
    },
    "staticfiles": {
        # تخزين ملفات CSS/JS محلياً مع ضغط WhiteNoise (بدون Manifest لتجنب الأخطاء)
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}

# 4. متغير التوافق (هام جداً لمنع أخطاء المكتبات الخارجية)
# نضعه كنص عادي لكي تجده أي مكتبة تبحث عنه بالطريقة القديمة
STATICFILES_STORAGE = 'whitenoise.storage.CompressedStaticFilesStorage'

# 5. رابط الميديا النهائي
if AWS_STORAGE_BUCKET_NAME:
    MEDIA_URL = f'https://{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com/'
    MEDIA_ROOT = os.path.join(BASE_DIR, 'media') # احتياطي
else:
    MEDIA_URL = '/media/'
    MEDIA_ROOT = os.path.join(BASE_DIR, 'media')



# settings.py
# يسمح لنافذة فيسبوك بالتحدث مع نافذة موقعك
SECURE_CROSS_ORIGIN_OPENER_POLICY = 'same-origin-allow-popups'




META_APP_ID = os.getenv('META_APP_ID', '843023434947245')
META_APP_SECRET = os.getenv('META_APP_SECRET')
META_API_VERSION = 'v24.0'


import os
GOOGLE_SHEETS_CREDENTIALS_JSON = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_JSON", "")