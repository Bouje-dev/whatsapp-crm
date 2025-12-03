# from tkinter import CASCADE
from urllib import request
from django.db import models
from django.conf import settings # لاستخدام AUTH_USER_MODEL

class CODProduct(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='cod_products')
    project = models.CharField(max_length=200, blank=True, null=True)  # اسم المشروع
    country = models.CharField(max_length=200 , blank=True )
    cod_id = models.CharField(max_length=100, unique=True)  # معرف المنتج في COD
    name = models.CharField(max_length=200)
    original_price = models.DecimalField(max_digits=10, decimal_places=2)
    stock = models.IntegerField(default=0)
    image_url = models.URLField(blank=True, null=True)
    is_active = models.BooleanField(default=True)  # هل المنتج متاح للعرض؟
    last_updated = models.DateTimeField(auto_now=True)  # تاريخ آخر تحديث
    product_cost= models.DecimalField(max_digits=10 ,decimal_places=2,blank=True, null=True)
    sku = models.CharField(max_length=200, unique=True  ,blank=True )

    updated =models.BooleanField(default=False)
    productImage = models.ImageField(upload_to='products/', null=True, blank=True)



    # custom_name = models.CharField(max_length=255, blank=True, null=True)
    # custom_image = models.URLField(blank=True, null=True)

    # created_at = models.DateTimeField(auto_now_add=True ,blank=True, null=True)
    # updated_at = models.DateTimeField(auto_now=True ,blank=True, null=True)
    def __str__(self):
        return self.name


class Order(models.Model):
    user = models.ForeignKey('CustomUser', on_delete=models.CASCADE, related_name='orders' )
  
    
    # 🔥 الإضافة الجديدة والضرورية 🔥
    channel = models.ForeignKey(
        'WhatsAppChannel', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='orders'
    )
    product_price = models.DecimalField(max_digits=10, decimal_places=2 , blank=True, null=True)
    product_quantity = models.IntegerField(default=1 , blank=True, null=True)
    customer_name = models.CharField(max_length=255 , blank=True, null=True)
    customer_country= models.CharField(max_length=255 , blank=True, null=True)
    customer_phone = models.CharField(max_length=20 , blank=True, null=True)
    customer_city = models.CharField(max_length=100, blank=True, null=True)
    product = models.CharField(max_length=255)
    gift_chosen = models.ForeignKey(CODProduct, on_delete=models.SET_NULL, null=True, related_name='chosen_gift')
    order_date = models.DateTimeField(auto_now_add=True)
    confirmed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)










    from django.db import models
from django.utils.translation import gettext_lazy as _












# user data 

# models.py
from django.db import models
from django.contrib.auth.models import AbstractUser
from .crypto import encrypt_token, decrypt_token

# models.py
 
# models.py
from django.contrib.auth.models import AbstractUser, Group, Permission

# discount/models.py

class CustomUser(AbstractUser):
    class Meta:
        db_table = 'discount_customuser'  # تحديد اسم الجدول صراحة

    # تغيير related_name لتجنب التعارضات
    groups = models.ManyToManyField(
        Group,
        related_name='custom_users',
        blank=True,
        verbose_name='groups',
        help_text='The groups this user belongs to.',
    )
    user_permissions = models.ManyToManyField(
        Permission,
        related_name='custom_users',
        blank=True,
        verbose_name='user permissions',
        help_text='Specific permissions for this user.',
    )
    
    # الحقول الإضافية
    email = models.EmailField(unique=True)
    user_name = models.CharField(max_length=255, blank=True, null=True, unique=False)  # يمكن استخدام هذا الحقل كاسم المستخدم
    phone = models.CharField(max_length=15, blank=True, null=True)
    is_verified = models.BooleanField(default=False)
     
    stuff_momber  = models.BooleanField(default=False)
    is_team_admin = models.BooleanField(default=False)
    email_verification_code = models.CharField(max_length=6, blank=True, null=True)
  # لتحديد إن كان الأدمين
    team_admin = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='team_members'
    )

    def is_staff_member(self):
        return self.team_admin is not None

    def generate_verification_code(self):
        import random
        code = str(random.randint(100000, 999999))  # OTP من 6 أرقام
        self.email_verification_code = code
        self.save()
        return code
    
    def can_access_channel(self, channel):
        """
        التحقق من أن المستخدم يمكنه الوصول إلى قناة معينة
        
        Args:
            channel: القناة المراد التحقق منها
        
        Returns:
            bool: True إذا كان يمكنه الوصول
        """
        if not channel:
            return False
        
        return channel.has_user_permission(self)
    
    def get_accessible_channels(self):
        """
        الحصول على جميع القنوات التي يمكن للمستخدم الوصول إليها
        
        Returns:
            QuerySet: قائمة القنوات
        """
        # استيراد WhatsAppChannel من نفس الملف (سيتم تعريفه لاحقاً في الملف)
        # استخدام lazy import لتجنب مشاكل الاستيراد الدائري
        from django.apps import apps
        WhatsAppChannel = apps.get_model('discount', 'WhatsAppChannel')
        
        # إذا كان المستخدم admin أو staff، يمكنه الوصول لجميع القنوات النشطة
        if self.is_superuser or self.is_staff or self.is_team_admin:
            return WhatsAppChannel.objects.filter(is_active=True).distinct()
        
        # خلاف ذلك، القنوات التي هو مالكها أو مخصص كـ agent لها
        from django.db.models import Q
        return WhatsAppChannel.objects.filter(
            Q(owner=self) | Q(assigned_agents=self),
            is_active=True
        ).distinct()


    class Meta:
        verbose_name = 'Custom User'
        verbose_name_plural = 'Custom Users'

    def __str__(self):
        return self.username
    



class ExternalTokenmodel(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='external_tokens')
    platform = models.CharField(max_length=100)  # اسم المنصة
    token_name = models.CharField(max_length=100, null=True)  # اسم التوكن
    access_token = models.TextField()  # تخزين التوكن بشكل مشفر
    token_status = models.BooleanField(default=True)  # حالة التوكن (مفعل/معطل)
    created_at = models.DateTimeField(auto_now_add=True)  # تاريخ الإنشاء










from django.contrib.auth import get_user_model
import uuid
class Products(models.Model):
    admin = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='Products')
    project = models.CharField(max_length=200, blank=True, null=True)  # اسم المشروع

    name = models.CharField(max_length=100)
    sku = models.CharField(max_length=100, unique=True)
    stock = models.IntegerField(default=0)

CustomUsers = get_user_model()




from django.db import models
from django.conf import settings  # <--- هام جداً: استيراد الإعدادات
import uuid

class TeamInvitation(models.Model):
    ROLE_CHOICES = [
        ('viewer', 'مشاهد'),
        ('editor', 'محرر'),
        ('manager', 'مشرف'),
    ]

    email = models.EmailField()
    
    # التعديل هنا: استخدمنا settings.AUTH_USER_MODEL بدلاً من كتابة اسم الكلاس
    admin = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='sent_invitations'
    )
    
    token = models.UUIDField(default=uuid.uuid4, unique=True)
    is_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    name = models.CharField(max_length=255, blank=True, null=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='viewer')
    
    # تأكد من أن اسم مودل المنتجات صحيح أيضاً (Products أو Product)
    products = models.ManyToManyField('Products', blank=True, related_name='invited_users')

    def __str__(self):
        return f"Invitation to {self.email}"


# team Permission 

class UserProductPermission(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='product_permissions')
    product = models.ForeignKey(Products, on_delete=models.CASCADE, related_name='user_permissions')
    daily_order_limit = models.IntegerField(default=0)
    ROLE_CHOICES = TeamInvitation.ROLE_CHOICES
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='viewer')
    
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'product')  # يمنع تكرار نفس الصلاحية لنفس المنتج

    def __str__(self):
        return f"{self.user} - {self.product.name} ({self.role})"


class UserPermissionSetting(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='permission_setting')
    can_create_orders = models.BooleanField(default=False)
    can_view_analytics = models.BooleanField(default=False)
    extra = models.JSONField(default=dict, blank=True)  # للحاجات الإضافية لاحقًا

    def __str__(self):
        return f"Permissions for {self.user}"
        

class SimpleOrder(models.Model):
    product = models.ForeignKey(
        Products,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='orders',
        verbose_name='المنتج المرتبط'
    )

    PENDING = 'pending'
    SHIPPED = 'shipped'
    DELIVERED = 'delivered'
    CANCELLED = 'cancelled'
    RETURNED = 'returned'
    
    # الخيارات المعروضة (الإنجليزية فقط)
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('shipped', 'Shipped'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
        ('returned', 'Returned'),
    ]
    
    status = models.CharField(max_length=20)
    customer_city = models.CharField(max_length=100, verbose_name=_('مدينة العميل'), blank=True, null=True)
    customer_country = models.CharField(max_length=100, verbose_name=_(' coutry'), blank=True, null=True) 
    order_id = models.CharField(max_length=100, unique=True, verbose_name=_('رقم الطلبية'))
    tracking_number = models.CharField(max_length=100, verbose_name=_('رقم التتبع')  , null=True)
    sku = models.CharField(max_length=100, verbose_name=_('SKU'))
    customer_name = models.CharField(max_length=200, verbose_name=_('اسم العميل'))
    customer_phone = models.CharField(max_length=20, verbose_name=_('هاتف العميل'))
    product_name = models.CharField(max_length=200, verbose_name=_('اسم المنتج'))
    created_at = models.DateTimeField(auto_now_add=False, verbose_name=_('تاريخ الإنشاء'))
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0 ,verbose_name=_('السعر'))
    currency = models.CharField(max_length=10, default='SAR', null=True ,blank=True ,   verbose_name=_('العملة'))
    class Meta:
        verbose_name = _('طلب مبسط')
        verbose_name_plural = _('طلبات مبسطة')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.tracking_number} - {self.customer_name}"
    











# tracking stuff activity hee



from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

class Activity(models.Model):
    # المستخدم الذي قام بالنشاط
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='activities', null=True, blank=True)
    
    # نوع النشاط (مثلاً: 'login', 'logout', 'order_created', 'order_updated', 'user_added', 'user_deleted')
    # يمكنك تعريف قائمة ثابتة لأنواع الأنشطة لتجنب الأخطاء الإملائية
    ACTIVITY_TYPES = (
        ('login', 'User Login'),
        ('logout', 'User Logout'),
        ('order_created', 'Order Created'),
        ('order_updated', 'Order Updated'),
        ('order_deleted', 'Order Deleted'),
        ('user_created', 'User Created'),
        ('user_updated', 'User Updated'),
        ('user_deleted', 'User Deleted'),
        ('product_filter', 'Product Filterd'),
        ('password_changed', 'Password Changed'),
        ('2fa_enabled', 'Two-Factor Auth Enabled'),
        ('2fa_disabled', 'Two-Factor Auth Disabled'),
        ('search_performed', 'Search Performed'), # مثال لأنشطة لوحة التحكم
        ('filter_applied', 'Filter Applied'),
        # أضف المزيد حسب حاجتك
    )
    activity_type = models.CharField(max_length=50, choices=ACTIVITY_TYPES, db_index=True)

    # وصف إضافي للنشاط (اختياري)
    description = models.TextField(blank=True, null=True)

    # وقت حدوث النشاط
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    # عنوان IP للمستخدم (اختياري، لكنه مفيد جداً للأمان)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    # معلومات حول الكائن الذي تأثر بالنشاط (باستخدام GenericForeignKey)
    # هذا يسمح لك بربط النشاط بأي نموذج في مشروعك (مثلاً: Order, User)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    content_object = GenericForeignKey('content_type', 'object_id')

    active_time = models.TimeField(null=True, blank=True)


    class Meta:
        ordering = ['-timestamp'] # ترتيب الأنشطة من الأحدث للأقدم
        verbose_name = "Activity Log"
        verbose_name_plural = "Activity Logs"

    def __str__(self):
        if self.user:
            return f"[{self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}] {self.user.username} - {self.get_activity_type_display()}"
        return f"[{self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}] {self.get_activity_type_display()}"

    def get_related_object_display(self):
        """
        يعيد تمثيلاً نصياً للكائن المرتبط، مفيد للعرض في لوحة التحكم.
        """
        if self.content_object:
            return str(self.content_object)
        return "N/A"









# models.py
 







class Lead(models.Model):
    product = models.ForeignKey(Products, on_delete=models.SET_NULL, null=True, blank=True, related_name='leads', verbose_name=_('المنتج'))
    name = models.CharField(max_length=255, verbose_name=_(' client name'))
    phone = models.CharField(max_length=20, verbose_name=_(' phone number'))
    message = models.TextField(verbose_name=_('message'))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_(' created at'))
    status = models.CharField(max_length=20, verbose_name=_('status'), default='processing')
    calls = models.IntegerField(default=0, verbose_name=_(' calls count'))
    lead_inputs = models.JSONField(default=dict, verbose_name=_('lead inputs'))  # لتخزين المدخلات المخصصة للعميل
    items=models.JSONField(default=dict, verbose_name=_('items'))
    history = models.JSONField(default=list, verbose_name=_('history'))  # لتخزين تاريخ التحديثات


    class Meta:
        verbose_name = _('Lead')
        verbose_name_plural = _('Leads')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} - {self.phone}"
    











# new updte for order tracking to understand marketing platfrom for better experience






"""
Models أساسية:
- CampaignVisit: تخزين السجل المؤقت لرقم الهاتف وUTM وقت إدخال العميل.
- ExternalOrder: تمثيل الطلب الوارد من (Shopify / Yokan / COD) مع تاريخ الإنشاء، رقم التتبع، وحالة التوصيل.
"""

import uuid
from django.db import models

# from django.contrib.postgres.fields import JSONField  # or models.JSONField in Django >=3.1

class ScriptFlow(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(getattr(settings, 'AUTH_USER_MODEL', 'auth.User'),
                              on_delete=models.CASCADE, related_name='script_flows')
    name = models.CharField(max_length=200, blank=True)
    api_key = models.CharField(max_length=128, unique=True)  # store token (or hashed - see notes)
    allowed_domains = models.TextField(blank=True, help_text="Comma separated domains allowed (e.g. shop.com,myshop.com)")
    config = models.JSONField(blank=True, null=True)  # store flow config snapshot
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    script = models.TextField(blank=True, null=True)   # <--- store generated script


    def allowed_domains_list(self):
        return [d.strip().lower() for d in (self.allowed_domains or "").split(',') if d.strip()]

    def __str__(self):
        return f"{self.name or str(self.id)} - {self.owner}"

# update CampaignVisit to reference flow




# your_app/models.py
from django.conf import settings
from django.utils import timezone

class CampaignVisit(models.Model):
    """
    Records each attempt to enter a phone on product/checkout with UTM.
    Used later to match orders by phone and nearest time.
    """
    user = models.ForeignKey(getattr(settings, 'AUTH_USER_MODEL', 'auth.User'),
                             on_delete=models.CASCADE,
                             related_name='campaign_visits',
                             null=True, blank=True)
    flow = models.ForeignKey(ScriptFlow, on_delete=models.SET_NULL, null=True, blank=True, related_name='visits')
    visit_id = models.CharField(max_length=255, null=True, blank=True)
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    raw_phone = models.CharField(max_length=64, blank=True, null=True)
    phone_normalized = models.CharField(max_length=32, db_index=True, blank=True, null=True)
    utm_campaign = models.CharField(max_length=200, blank=True, null=True)
    utm_source = models.CharField(max_length=200, blank=True, null=True)
    utm_medium = models.CharField(max_length=200, blank=True, null=True)
    ad_id = models.CharField(max_length=200, blank=True, null=True)
    site_source_name = models.CharField(max_length=200, blank=True, null=True)  # e.g. 'shopify'
    ad_adset_name = models.CharField(max_length=300, blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ('-created_at',)
        indexes = [
            models.Index(fields=['phone_normalized']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"{self.phone_normalized or 'unknown'} @ {self.utm_campaign or '-'} ({self.created_at.isoformat()})"


class ExternalOrder(models.Model):
    """
    يمثل أي طلب يأتي من منصة الطلبات أو شركة التوصيل أو تُسترد من API.
    - external_order_id: المعرف الذي تعطينا إياه المنصة/الشركة (Shopify ID أو COD ID).
    - order_ref: مرجع إضافي إذا وُجد (مثلاً order_ref الذي ترسله COD).
    - tracking_number: رقم التتبع الذي توفره شركة الشحن (مهم للتتبع في الوقت الفعلي).
    - matched_visit: FK إلى CampaignVisit بعد المطابقة.
    - meta: حفظ كامل الـ payload من API للرجوع إليه لاحقًا.
    """
    STATUS_CHOICES = [
        ('created','created'),
        ('confirmed','confirmed'),
        ('shipped','shipped'),
        ('delivered','delivered'),
        ('cancelled','cancelled'),
        ('unknown','unknown'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    platform = models.CharField(max_length=50, default='unknown')  # shopify, yokan, cod, etc
    external_order_id = models.CharField(max_length=200, db_index=True)
    order_ref = models.CharField(max_length=200, blank=True, null=True)
    raw_phone = models.CharField(max_length=64, blank=True, null=True)
    phone_normalized = models.CharField(max_length=32, db_index=True)
    customer_name = models.CharField(max_length=255, blank=True, null=True)
    tracking_number = models.CharField(max_length=200, blank=True, null=True)  # رقم تتبع شركة الشحن المباشرة
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='unknown')
    created_at = models.DateTimeField()         # الوقت كما في المصدر
    fetched_at = models.DateTimeField(auto_now_add=True)  # وقت استرجاعنا للبيانات
    matched_visit = models.ForeignKey(CampaignVisit, null=True, blank=True, on_delete=models.SET_NULL)
    meta = models.JSONField(default=dict, blank=True)    # أي بيانات إضافية

    class Meta:
        indexes = [
            models.Index(fields=['phone_normalized', 'created_at']),
            models.Index(fields=['external_order_id']),
            models.Index(fields=['tracking_number']),
        ]

    def __str__(self):
        return f"{self.external_order_id} ({self.platform}) - {self.status}"









from django.db import models

class Advertiser(models.Model):
    page_id = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=255)
    domain = models.CharField(max_length=255, null=True, blank=True)
    page_url = models.URLField(null=True, blank=True)
    ad_account = models.CharField(max_length=64, null=True, blank=True)
   
    def __str__(self):
        return f"{self.name} ({self.page_id})"

class CTA(models.Model):
    # Master list for CTAs so we can filter reliably
    name = models.CharField(max_length=64, unique=True)

    def __str__(self):
        return self.name

class Country(models.Model):
    code = models.CharField(max_length=8, unique=True)  # 'US', 'MA', 'EU' etc.
    name = models.CharField(max_length=128)

    def __str__(self):
        return self.name

class Tag(models.Model):
    name = models.CharField(max_length=64, unique=True)

    def __str__(self):
        return self.name

class AdCreative(models.Model):
    creative_id = models.CharField(max_length=128, unique=True)
    body = models.TextField(null=True, blank=True)
    # main thumbnail or representative image URL (store full url or path)
    thumbnail_url = models.CharField(max_length=768, null=True, blank=True)
    # keep original fields too
    image_hash = models.CharField(max_length=128, null=True, blank=True)
    video_id = models.CharField(max_length=128, null=True, blank=True)
    video_url = models.URLField(null=True, blank=True)
    # derived flags
    is_video = models.BooleanField(default=False)
    duration_seconds = models.IntegerField(null=True, blank=True)  # for videos
    aspect_ratio = models.CharField(max_length=16, null=True, blank=True)

    def __str__(self):
        return f"Creative {self.creative_id}"

class AdArchive(models.Model):
    ad_id = models.CharField(max_length=128, unique=True)
    advertiser = models.ForeignKey(Advertiser, on_delete=models.SET_NULL, null=True, blank=True)
    page_name = models.CharField(max_length=255, null=True, blank=True)  # fallback if advertiser missing
    # snapshot url + landing url
    ad_snapshot_url = models.URLField(null=True, blank=True)
    landing_url = models.URLField(null=True, blank=True)

    # normalized fields for UI & filtering
    platform = models.CharField(max_length=32, null=True, blank=True)   # facebook, instagram, tiktok
    country = models.ForeignKey(Country, on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=32, null=True, blank=True)     # active, stopped

    # ad timing
    ad_delivery_start_time = models.DateTimeField(null=True, blank=True)
    ad_delivery_stop_time  = models.DateTimeField(null=True, blank=True)
    created_time = models.DateTimeField(auto_now_add=True)

    # metrics (denormalized for fast queries)
    adsets_count = models.IntegerField(null=True, blank=True)
    impressions = models.BigIntegerField(null=True, blank=True)
    spend = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    clicks = models.BigIntegerField(null=True, blank=True)
    ctr = models.FloatField(null=True, blank=True)
    cpc = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    conversions = models.IntegerField(null=True, blank=True)
    cpa = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    roas = models.FloatField(null=True, blank=True)

    creative = models.ForeignKey(AdCreative, on_delete=models.SET_NULL, null=True, blank=True)

    # relations for filtering / UI
    ctas = models.ManyToManyField(CTA, blank=True)
    tags = models.ManyToManyField(Tag, blank=True)

    raw_json = models.JSONField(null=True, blank=True)  # keep original payload

    class Meta:
        indexes = [
            models.Index(fields=['platform']),
            models.Index(fields=['country']),
            models.Index(fields=['status']),
            models.Index(fields=['ad_delivery_start_time']),
            models.Index(fields=['ad_delivery_stop_time']),
            models.Index(fields=['spend']),
            models.Index(fields=['impressions']),
        ]

    def __str__(self):
        return f"Ad {self.ad_id} ({self.advertiser})"

class MetricSnapshot(models.Model):
    # optional time-series snapshots for historical charts
    ad = models.ForeignKey(AdArchive, on_delete=models.CASCADE, related_name='snapshots')
    snapshot_date = models.DateField(db_index=True)
    impressions = models.BigIntegerField(null=True, blank=True)
    spend = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    clicks = models.BigIntegerField(null=True, blank=True)
    conversions = models.IntegerField(null=True, blank=True)

    class Meta:
        unique_together = ('ad','snapshot_date')
        indexes = [models.Index(fields=['snapshot_date'])]

    def __str__(self):
        return f"{self.ad.ad_id} @ {self.snapshot_date}"



class UserSavedAd(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='saved_ads')
    ad_id = models.CharField(max_length=128)                 # المفتاح إلى AdArchive.ad_id
    saved_at = models.DateTimeField(auto_now_add=True)
    note = models.TextField(blank=True, null=True)  




 













# for whatssapAPI Cloud 
from django.db import models
from django.utils import timezone
import json
from django.db import models
from django.contrib.auth.models import User

class WhatsAppChannel(models.Model):
    name = models.CharField(max_length=100, help_text="مثلاً: خدمة العملاء")
    
    # 🔥 المستخدم الذي أنشأ هذه القناة (المالك)
    owner = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="owned_channels",
        verbose_name="المالك",
        help_text="المستخدم الذي أنشأ هذه القناة"
    )
    
    # بيانات الربط مع ميتا (لكل رقم بياناته الخاصة)
    phone_number = models.CharField(max_length=20, unique=True) # الرقم الظاهر (+966...)
    phone_number_id = models.CharField(max_length=100, unique=True) # معرف الرقم من فيسبوك
    business_account_id = models.CharField(max_length=100, null=True, blank=True)
    access_token = models.TextField(help_text="التوكن الدائم الخاص بهذا الرقم")
    api_version = models.CharField(max_length=10, default="v22.0")
    # الصلاحيات: من هم الموظفون المسموح لهم برؤية هذا الرقم؟
    assigned_agents = models.ManyToManyField(CustomUser, related_name="channels", blank=True)
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.phone_number})"

    def has_user_permission(self, user):
        """
        التحقق من أن المستخدم لديه صلاحية على هذه القناة
        
        Args:
            user: المستخدم المراد التحقق منه
        
        Returns:
            bool: True إذا كان لديه صلاحية، False خلاف ذلك
        """
        if not user or not user.is_authenticated:
            return False
        
        # التحقق من أن المستخدم نشط
        if hasattr(user, 'is_active') and not user.is_active:
            return False
        
        # 🔥 التحقق من الصلاحيات (يشمل المالك)
        return (
            # المالك لديه صلاحية كاملة
            (self.owner and self.owner.id == user.id) or
            # الوكلاء المخصصين
            self.assigned_agents.filter(id=user.id).exists() or
            # Admin أو Staff لديهم صلاحية على جميع القنوات
            (hasattr(user, 'is_superuser') and user.is_superuser) or
            (hasattr(user, 'is_staff') and user.is_staff) or
            (hasattr(user, 'is_team_admin') and user.is_team_admin)
        )
    
    def is_configured(self):
        """
        التحقق من أن القناة مُعدة بشكل صحيح
        
        Returns:
            bool: True إذا كانت القناة مُعدة بشكل صحيح
        """
        return bool(self.access_token and self.phone_number_id and self.is_active)
    
    def get_agents_list(self):
        """
        الحصول على قائمة جميع الوكلاء المخصصين لهذه القناة
        
        Returns:
            QuerySet: قائمة المستخدمين
        """
        return self.assigned_agents.all()
    
    def add_agent(self, user):
        """
        إضافة وكيل جديد للقناة
        
        Args:
            user: المستخدم المراد إضافته
        
        Returns:
            bool: True إذا تمت الإضافة بنجاح
        """
        if user and user.is_authenticated:
            self.assigned_agents.add(user)
            return True
        return False
    
    def remove_agent(self, user):
        """
        إزالة وكيل من القناة
        
        Args:
            user: المستخدم المراد إزالته
        
        Returns:
            bool: True إذا تمت الإزالة بنجاح
        """
        if user:
            self.assigned_agents.remove(user)
            return True
        return False
    
    def is_owner(self, user):
        """
        التحقق من أن المستخدم هو مالك هذه القناة
        
        Args:
            user: المستخدم المراد التحقق منه
        
        Returns:
            bool: True إذا كان المالك
        """
        return self.owner and self.owner.id == user.id
    
    def can_manage(self, user):
        """
        التحقق من أن المستخدم يمكنه إدارة هذه القناة (مالك أو admin/staff)
        
        Args:
            user: المستخدم المراد التحقق منه
        
        Returns:
            bool: True إذا كان يمكنه الإدارة
        """
        if not user or not user.is_authenticated:
            return False
        
        # المالك يمكنه الإدارة
        if self.is_owner(user):
            return True
        
        # Admin أو Staff يمكنهم الإدارة
        if (hasattr(user, 'is_superuser') and user.is_superuser) or \
           (hasattr(user, 'is_staff') and user.is_staff) or \
           (hasattr(user, 'is_team_admin') and user.is_team_admin):
            return True
        
        return False
 
    # 🔥 الحقل الجديد (هام جداً)
 


class Message(models.Model):
    sender = models.CharField(max_length=50)
    body = models.TextField()
    name = models.CharField(max_length=50, null=True, blank=True)
    timestamp = models.DateTimeField(default=timezone.now)
    is_from_me = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    message_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    channel = models.ForeignKey(
        WhatsAppChannel, 
        on_delete=models.CASCADE, 
        related_name="messages",
        null=True, blank=True # نجعله فارغاً مؤقتاً لتجنب مشاكل البيانات القديمة
    )
    
    media_type = models.CharField(
        max_length=20,
        choices=[('image', 'Image'), ('video', 'Video'), ('audio', 'Audio'), ('document', 'Document')],
        blank=True,
        null=True
    )
    media_id = models.CharField(max_length=100, blank=True, null=True)
    media_file = models.FileField(upload_to='media/', blank=True, null=True)
    media_url = models.CharField(max_length=1000, blank=True, null=True)
    
    # حقول إضافية للتحكم بالحالة
    status = models.CharField(max_length=20, default='sent', choices=[
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('read', 'Read'),
        ('failed', 'Failed')
    ])
    status_timestamp = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['sender', 'timestamp']),
            models.Index(fields=['message_id']),
        ]

    def __str__(self):
        return f"{self.sender}: {self.body[:30]}"

    def save(self, *args, **kwargs):
        if not self.timestamp:
            self.timestamp = timezone.now()
        super().save(*args, **kwargs)


from django.db import models

class Template(models.Model):
    # البيانات الأساسية
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=100, blank=True, null=True)
    language = models.CharField(max_length=50, blank=True, null=True)
    status = models.CharField(max_length=50, blank=True, null=True)
    approval_status = models.CharField(max_length=50, blank=True, null=True)
    version = models.CharField(max_length=50, blank=True, null=True)
    channel = models.ForeignKey(WhatsAppChannel, on_delete=models.CASCADE, related_name='templates')
    user = models.ForeignKey(getattr(settings, 'AUTH_USER_MODEL', 'auth.User'), on_delete=models.CASCADE)
    # معرفات واتساب
    template_id = models.CharField(max_length=100, blank=True, null=True)
    namespace = models.CharField(max_length=255, blank=True, null=True)
    provider = models.CharField(max_length=100, blank=True, null=True)  # meta / twilio / cloud_api

    # جسم القالب
    body = models.TextField(blank=True, null=True)
    footer = models.TextField(blank=True, null=True)

    # الهيدر
    header_type = models.CharField(max_length=50, blank=True, null=True)
    header_text = models.CharField(max_length=255, blank=True, null=True)

    header_image = models.FileField(upload_to='templates/headers/', blank=True, null=True)
    header_video = models.FileField(upload_to='templates/headers/', blank=True, null=True)
    header_audio = models.FileField(upload_to='templates/headers/', blank=True, null=True)

    # المتغيرات
    variables_count = models.IntegerField(default=0)
    variables = models.JSONField(default=list, blank=True)  
    sample_values = models.JSONField(default=dict, blank=True)  

    # الأزرار
    buttons = models.JSONField(default=list, blank=True)

    # المكونات الأصلية من واتساب
    components = models.JSONField(default=dict, blank=True)

    # الاستخدام
    times_used = models.IntegerField(default=0)
    last_used_at = models.DateTimeField(blank=True, null=True)
    last_synced_at = models.DateTimeField(blank=True, null=True)

    # التحكم في التفعيل
    is_active = models.BooleanField(default=True)

    # التواريخ
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name




class AutoReply(models.Model):
    MATCH_EXACT = 'exact'
    MATCH_CONTAINS = 'contains'
    MATCH_STARTS_WITH = 'starts_with'
    MATCH_REGEX = 'regex'
    MATCH_CHOICES = [
        (MATCH_EXACT, 'Exact'),
        (MATCH_CONTAINS, 'Contains'),
        (MATCH_STARTS_WITH, 'Starts with'),
        (MATCH_REGEX, 'Regex'),
    ]

    RESP_TEXT = 'text'
    RESP_IMAGE = 'image'
    RESP_AUDIO = 'audio'
    RESP_VIDEO = 'video'
    RESP_DOCUMENT = 'document'
    RESPONSE_CHOICES = [
        (RESP_TEXT, 'Text'),
        (RESP_IMAGE, 'Image'),
        (RESP_AUDIO, 'Audio'),
        (RESP_VIDEO, 'Video'),
        (RESP_DOCUMENT, 'Document'),
    ]

    trigger = models.CharField(max_length=255, help_text="النص أو النمط الذي نطابقه")
    match_type = models.CharField(
        max_length=20,
        choices=MATCH_CHOICES,
        default=MATCH_CONTAINS,
        help_text="طريقة مطابقة النص الوارد"
    )
    response_type = models.CharField(
        max_length=12,
        choices=RESPONSE_CHOICES,
        default=RESP_TEXT,
        help_text="نوع الرد الذي سيُرسل"
    )
    response_text = models.TextField(blank=True, help_text="نص الرد (إذا كان نوع الرد نص)")
    media_file = models.FileField(upload_to='autoreply_media/', null=True, blank=True, help_text="ملف وسائط يُستخدم في الرد إذا تطلب الأمر")
    
    # حقول إضافية للتحكم
    delay = models.IntegerField(default=0, help_text="تأخير الإرسال بالثواني")
    active = models.BooleanField(default=True)
    priority = models.IntegerField(default=0, help_text="الأولوية (رقم أعلى = أولوية أعلى)")
    
    # إحصائيات
    usage_count = models.IntegerField(default=0, help_text="عدد مرات استخدام هذه القاعدة")
    last_used = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-priority', '-created_at']
        verbose_name = "AutoReply"
        verbose_name_plural = "AutoReplies"

    def __str__(self):
        return f"{self.trigger} -> {self.response_type}"

    def increment_usage(self):
        """زيادة عداد الاستخدام"""
        self.usage_count += 1
        self.last_used = timezone.now()
        self.save(update_fields=['usage_count', 'last_used'])


 








class Flow(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    active = models.BooleanField(default=True)
    channel = models.ForeignKey(WhatsAppChannel, on_delete=models.CASCADE)
    user= models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    
    # --- التعديل هنا: إضافة حقل الكلمات + حقل تفعيل البداية ---
    trigger_keywords = models.TextField(blank=True, help_text="كلمات مفتاحية لتفعيل التدفق (مفصولة بفاصلة)")
    trigger_on_start = models.BooleanField(default=False, help_text="تفعيل هذا التدفق تلقائياً عند بداية المحادثة")
    # -----------------------------------------------------------

    start_node = models.ForeignKey("Node", null=True, blank=True, on_delete=models.SET_NULL, related_name="start_flows")

    # إحصائيات
    usage_count = models.IntegerField(default=0, help_text="عدد مرات استخدام هذا التدفق")
    success_count = models.IntegerField(default=0, help_text="عدد المرات التي أنهى فيها المستخدم التدفق")
    last_used = models.DateTimeField(null=True, blank=True)
    
    config = models.JSONField(default=dict, blank=True)

    def match_trigger(self, message_text: str = "", is_new_conversation: bool = False) -> bool:
        """
        يتحقق مما إذا كان هذا التدفق يجب أن يعمل بناءً على الرسالة أو حدث البداية.
        """
        # 1. إذا كان التدفق مخصصاً لبداية المحادثة، والحدث الحالي هو "محادثة جديدة"
        if self.trigger_on_start and is_new_conversation:
            return True

        # 2. البحث في الكلمات المفتاحية (فقط إذا كان هناك نص)
        if self.trigger_keywords and message_text:
            keywords = [k.strip().lower() for k in self.trigger_keywords.split(",") if k.strip()]
            message_text = message_text.lower()
            return any(kw in message_text for kw in keywords)

        return False

    def save(self, *args, **kwargs):
        # (اختياري) منطق لضمان وجود تدفق واحد فقط مفعل كـ "بداية محادثة" لتجنب التضارب
        if self.trigger_on_start and self.active:
            # قم بإلغاء تفعيل خاصية البداية من التدفقات الأخرى النشطة
            Flow.objects.filter(trigger_on_start=True, active=True).exclude(pk=self.pk).update(trigger_on_start=False)
        
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name





class Node(models.Model):
    # NODE_TYPES = [
    #     ('text', 'Text Message'),
    #     ('media', 'Media Message'),
    #     ('mixed', 'Text + Media'),
    #     ('condition', 'Condition'),
    # ]

    flow = models.ForeignKey(Flow, on_delete=models.CASCADE, related_name='nodes')
    node_type = models.CharField(max_length=30)
    node_id = models.CharField(max_length=100)

    position_x = models.FloatField(default=0)
    position_y = models.FloatField(default=0)
    content_text = models.TextField(blank=True, null=True)
    content_media_url = models.URLField(blank=True, null=True)
    delay = models.IntegerField(default=0)

    started_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    media_type = models.CharField(max_length=20,blank=True, null=True,)
    def __str__(self):
        return f"Node {self.id} ({self.node_type}) in Flow {self.flow.name}"







class Connection(models.Model):
    flow = models.ForeignKey(Flow, on_delete=models.CASCADE, related_name="connections")
    from_node = models.ForeignKey(Node, on_delete=models.CASCADE, related_name="outgoing_connections")
    to_node = models.ForeignKey(Node, on_delete=models.CASCADE, related_name="incoming_connections")
    data = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"{self.from_node.node_id} → {self.to_node.node_id}"






class Contact(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    phone = models.CharField(max_length=30, unique=True)
    name = models.CharField(max_length=255, blank=True, null=True)
    channel = models.ForeignKey(WhatsAppChannel, on_delete=models.CASCADE)

    flow_started = models.BooleanField(default=False)
    last_interaction = models.DateTimeField(auto_now=True)
    last_seen = models.DateField(max_length=255, blank=True, null=True)
        # تصحيح last_seen
    last_seen = models.DateTimeField(blank=True, null=True)

    # صورة العميل
    profile_picture = models.ImageField(
        upload_to='contacts/', 
        blank=True,
        null=True
    )

    def __str__(self):
        return self.phone
























# testing 
class groupchat(models.Model):
    group_name = models.CharField(max_length=333 , unique=True)
    def __str__(self):
        return self.group_name
    
class GroupMessages(models.Model):
    Group= models.ForeignKey(groupchat, related_name='chate_messages' , on_delete=models.CASCADE)
    auther = models.ForeignKey(CustomUser , on_delete=models.CASCADE)
    message = models.TextField(max_length=300)
    created = models.DateTimeField(auto_now_add=True)
    def __str__(self):
        return f'{self.auther.username}: {self.message}'
    class Meta:
        ordering =['-created']