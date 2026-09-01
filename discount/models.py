# from tkinter import CASCADE
from urllib import request
from django.db import models
from django.conf import settings # لاستخدام AUTH_USER_MODEL


def _default_json_list():
    return []


class CODProduct(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='cod_products')
    project = models.CharField(max_length=600, blank=True, null=True)  # اسم المشروع
    country = models.CharField(max_length=600 , blank=True )
    cod_id = models.CharField(max_length=100, unique=True)  # معرف المنتج في COD
    name = models.CharField(max_length=600)
    original_price = models.DecimalField(max_digits=10, decimal_places=2)
    stock = models.IntegerField(default=0)
    image_url = models.TextField(blank=True, null=True , )
    is_active = models.BooleanField(default=True)  # هل المنتج متاح للعرض؟
    last_updated = models.DateTimeField(auto_now=True)  # تاريخ آخر تحديث
    product_cost= models.DecimalField(max_digits=10 ,decimal_places=2,blank=True, null=True)
    sku = models.CharField(max_length=600, unique=True  ,blank=True )

    updated =models.BooleanField(default=False)
    productImage = models.ImageField(upload_to='products/', null=True, blank=True)


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
    gift_chosen = models.ForeignKey(CODProduct, on_delete=models.SET_NULL, null=True, blank=True , related_name='chosen_gift')
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


class Plan(models.Model):
    """Subscription plan controlling access to paid features (AI voice, voice cloning, auto-reply)."""
    name = models.CharField(max_length=50, unique=True)  # e.g. Basic, Premium
    can_use_ai_voice = models.BooleanField(default=False)
    can_use_voice_cloning = models.BooleanField(default=False)
    can_use_cloning = models.BooleanField(default=False, help_text="Alias for voice cloning capability")
    can_use_advanced_tones = models.BooleanField(default=False, help_text="Stability & similarity sliders (PRO)")
    can_use_auto_reply = models.BooleanField(default=False)
    can_use_multi_modal = models.BooleanField(default=False, help_text="AI node media gallery & [SEND_MEDIA] in flows")
    can_use_persona_gallery = models.BooleanField(default=False, help_text="High-quality & cloned personas in Flow Builder")
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0, null=True, blank=True)
    max_monthly_orders = models.PositiveIntegerField(null=True, blank=True, help_text="Cap on auto-created orders per month; null = unlimited")
    max_channels = models.PositiveIntegerField(null=True, blank=True, help_text="Max WhatsApp channels the owner can create; null = unlimited")
    max_team_members = models.PositiveIntegerField(null=True, blank=True, help_text="Max team members (excl. owner/bots); null = unlimited")

    # Map feature_name (string) -> Plan boolean field name; extend this when adding new features
    FEATURE_FIELDS = {
        "ai_voice": "can_use_ai_voice",
        "voice_cloning": "can_use_voice_cloning",
        "cloning": "can_use_cloning",
        "advanced_tones": "can_use_advanced_tones",
        "auto_reply": "can_use_auto_reply",
        "multi_modal": "can_use_multi_modal",
        "persona_gallery": "can_use_persona_gallery",
    }

    def can_use_feature(self, feature_name):
        """Check if this plan allows the given feature (e.g. 'ai_voice', 'voice_cloning', 'auto_reply')."""
        field = self.FEATURE_FIELDS.get(feature_name)
        if not field:
            return False
        return getattr(self, field, False)

    def __str__(self):
        return self.name


class CustomUser(AbstractUser):
    class Meta:
        db_table = 'discount_customuser'  # تحديد اسم الجدول صراحة

    # تغيير related_name لتجنب التعارضات\\
    is_online = models.BooleanField(default=False )
    last_seen = models.DateTimeField(auto_now=True , blank=True, null=True)
    plan = models.ForeignKey(
        Plan,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="users",
        help_text="Subscription plan for API and feature access.",
    )
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
    wallet_balance = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    total_tokens_used = models.PositiveIntegerField(default=0)
    low_balance_alert_enabled = models.BooleanField(default=True)
    stripe_customer_id = models.CharField(max_length=255, blank=True, null=True)
    stripe_subscription_id = models.CharField(max_length=255, blank=True, null=True)
    stripe_subscription_status = models.CharField(max_length=120, blank=True, null=True)
    is_verified = models.BooleanField(default=False)

    # Risk management / kill switch for merchants
    is_suspended = models.BooleanField(default=False)
    suspension_reason = models.TextField(null=True, blank=True)
     
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
    # Virtual Team Member (AI Agent) for order attribution
    is_bot = models.BooleanField(default=False, help_text="Virtual user representing an AI agent; orders created by AI are attributed to this user.")
    agent_role = models.CharField(max_length=120, blank=True, null=True, help_text="Display role e.g. 'Simo - AI Closer' for bot users.")
    bot_owner = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='bot_agents',
        help_text="Merchant who owns this bot (only set when is_bot=True).",
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

    def get_plan(self):
        """Return the user's plan, or the default Basic plan if none set."""
        if self.plan_id:
            return self.plan
        from django.apps import apps
        PlanModel = apps.get_model("discount", "Plan")
        return PlanModel.objects.filter(name="Basic").first()

    def is_feature_allowed(self, feature_name):
        """Check if the user's plan allows the given feature. Zero-bypass: always check on backend."""
        plan = self.get_plan()
        if not plan:
            return False
        return plan.can_use_feature(feature_name)


    class Meta:
        verbose_name = 'Custom User'
        verbose_name_plural = 'Custom Users'

    def __str__(self):
        return self.username


class MerchantRiskEvent(models.Model):
    """
    Auditable incident for Founder HQ risk scoring (complaints, watchdog flags, payment issues).
    """

    EVENT_SUPPORT_COMPLAINT = "support_complaint"
    EVENT_FLAG_REVIEW = "flag_for_review"
    EVENT_PAYMENT_REJECTED = "payment_rejected"
    EVENT_NEGATIVE_SENTIMENT = "negative_sentiment"
    EVENT_CHOICES = [
        (EVENT_SUPPORT_COMPLAINT, "Support complaint"),
        (EVENT_FLAG_REVIEW, "Flagged for review"),
        (EVENT_PAYMENT_REJECTED, "Payment receipt rejected"),
        (EVENT_NEGATIVE_SENTIMENT, "Negative sentiment / rejection"),
    ]

    merchant = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="risk_events",
        limit_choices_to={"is_bot": False},
    )
    channel = models.ForeignKey(
        "WhatsAppChannel",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="risk_events",
    )
    order = models.ForeignKey(
        "SimpleOrder",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="risk_events",
    )
    customer_phone = models.CharField(max_length=30, blank=True, default="")
    event_type = models.CharField(max_length=32, choices=EVENT_CHOICES, db_index=True)
    summary = models.TextField(blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["merchant", "-created_at"]),
            models.Index(fields=["merchant", "event_type", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.event_type} @ {self.merchant_id} ({self.created_at:%Y-%m-%d})"


class FounderRiskAlert(models.Model):
    """Dedupes proactive superadmin alerts (one row per merchant per calendar day per threshold)."""

    merchant = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="founder_risk_alerts",
    )
    alert_date = models.DateField(db_index=True)
    complaints_count = models.PositiveIntegerField(default=0)
    notified_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("merchant", "alert_date")]

    def __str__(self):
        return f"Risk alert {self.merchant_id} {self.alert_date}"


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
    sku = models.CharField(max_length=100, unique=True, blank=True, null=True)
    stock = models.IntegerField(default=0)

    # Product creation from WhatsApp dashboard (required in form: name, price, description, images)
    price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, verbose_name=_('السعر'))
    backup_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_('سعر احتياطي للتفاوض'),
        help_text=_('Optional fallback/negotiation price used by AI when offering a discount.'),
    )
    coupon_code = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        verbose_name=_('كود كوبون'),
        help_text=_('Optional coupon code the AI can use during negotiation.'),
    )
    currency = models.CharField(max_length=10, default='MAD', blank=True, verbose_name=_('العملة'))
    description = models.TextField(blank=True, null=True, verbose_name=_('الوصف'))
    how_to_use = models.TextField(blank=True, null=True, verbose_name=_('طريقة الاستخدام'))
    offer = models.CharField(max_length=500, blank=True, null=True, verbose_name=_('العرض'))
    delivery_options = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        verbose_name=_('خيارات التوصيل'),
        help_text=_('e.g. "Free delivery", "30 MAD", "Free above 200 MAD" — shown to customer when they ask about delivery'),
    )
    return_policy = models.TextField(
        blank=True,
        null=True,
        verbose_name=_('Return / warranty policy'),
        help_text=_(
            'Specific return/warranty policy for this product. If left blank, AI will apply '
            'standard strict delivery rules.'
        ),
    )
    # AI product classification and prompt routing (must match ai_assistant.product_classifier.VALID_CATEGORIES)
    PRODUCT_CATEGORY_CHOICES = [
        ('beauty_and_skincare', _('Beauty & Skincare')),
        ('electronics_and_gadgets', _('Electronics & Gadgets')),
        ('fragrances', _('Fragrances')),
        ('fashion_and_apparel', _('Fashion & Apparel')),
        ('health_and_supplements', _('Health & Supplements')),
        ('home_and_kitchen', _('Home & Kitchen')),
        ('general_retail', _('General')),
        # Legacy (kept for existing DB rows)
        ('beauty', _('Beauty')),
        ('electronics', _('Electronics')),
        ('general', _('General')),
    ]
    category = models.CharField(
        max_length=32,
        choices=PRODUCT_CATEGORY_CHOICES,
        default='general_retail',
        blank=True,
        verbose_name=_('Product category (AI-classified or manual)'),
        help_text=_('Used for dynamic sales persona: beauty, electronics, fragrances, general'),
    )
    seller_custom_persona = models.TextField(
        blank=True,
        null=True,
        verbose_name=_('Custom selling instructions'),
        help_text=_('Optional: seller instructions appended to the AI sales prompt for this product'),
    )
    required_order_fields = models.JSONField(
        blank=True,
        null=True,
        default=list,
        help_text=_(
            'List of order fields the AI must collect for this product (e.g. '
            '["customer_name", "phone_number"] or '
            '["customer_name", "phone_number", "shipping_city", "shipping_address"]).'
        ),
    )
    CHECKOUT_MODE_CHOICES = [
        ('quick_lead',    _('Quick Lead (Name & Phone only)')),
        ('standard_cod',  _('Standard COD (Name, Phone, City)')),
        ('strict_cod',    _('Strict COD (Full Address)')),
        ('digital',       _('Digital Delivery (Name & Email — no shipping address)')),
        ('direct_sale',   _('Direct Sale (No information required — instant submit)')),
    ]
    checkout_mode = models.CharField(
        max_length=20,
        choices=CHECKOUT_MODE_CHOICES,
        default='standard_cod',
        blank=True,
        verbose_name=_('Checkout mode (AI data collection)'),
        help_text=_(
            'Controls what the AI Sales Agent collects before placing an order. '
            'quick_lead = Name+Phone; standard_cod = Name+Phone+City; '
            'strict_cod = Name+Phone+City+Address; digital = Name+Email (no shipping); '
            'direct_sale = No info required — AI submits instantly on purchase intent.'
        ),
    )
    testimonial = models.FileField(
        upload_to='product_testimonials/%Y/%m/',
        blank=True,
        null=True,
        verbose_name=_('شهادة صوت/فيديو/صورة'),
        help_text=_('Optional: audio, video or image testimonial'),
    )


    # ── Digital Product Fields ─────────────────────────────────────────────
    # All three fields default to False / None so that every existing physical
    # product is completely unaffected by these additions.
    is_digital = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name=_('Digital product'),
        help_text=_(
            'Mark True for e-books, courses, licence keys, etc. '
            'When True the AI Agent collects Name + Email instead of a shipping address, '
            'and the checkout_mode is automatically treated as "digital".'
        ),
    )
    digital_file = models.FileField(
        upload_to='digital_assets/',
        blank=True,
        null=True,
        verbose_name=_('Digital file'),
        help_text=_(
            'Upload the deliverable directly (PDF, ZIP, …). '
            'Used when the file is small enough to host on this server.'
        ),
    )
    digital_url = models.URLField(
        blank=True,
        null=True,
        verbose_name=_('Digital download URL'),
        help_text=_(
            'External link (Google Drive, Mega, S3…) for large files. '
            'Sent to the customer after order confirmation.'
        ),
    )
    fulfillment_message = models.TextField(
        blank=True,
        null=True,
        verbose_name=_('Fulfillment message'),
        help_text=_(
            'Custom thank-you message sent automatically to the customer after digital product purchase. '
            'Leave blank for a system default message.'
        ),
    )
    collect_customer_info = models.BooleanField(
        default=True,
        verbose_name=_('Collect customer info'),
        help_text=_(
            'Digital products only. When True the AI Agent asks for Name + Email before delivering the product. '
            'When False the AI triggers the order immediately using the WhatsApp phone number — no questions asked.'
        ),
    )
    DIGITAL_PRODUCT_TYPE_ACCOUNT = 'account'
    DIGITAL_PRODUCT_TYPE_KEY = 'key'
    DIGITAL_PRODUCT_TYPE_IPTV = 'iptv'
    DIGITAL_PRODUCT_TYPE_CHOICES = [
        (DIGITAL_PRODUCT_TYPE_ACCOUNT, _('Account / credentials')),
        (DIGITAL_PRODUCT_TYPE_KEY, _('Activation key / licence')),
        (DIGITAL_PRODUCT_TYPE_IPTV, _('IPTV subscription')),
    ]
    digital_product_type = models.CharField(
        max_length=20,
        choices=DIGITAL_PRODUCT_TYPE_CHOICES,
        blank=True,
        null=True,
        verbose_name=_('Digital product type'),
        help_text=_('Sub-category for digital goods (account, key, or IPTV). Physical products leave this empty.'),
    )
    legal_consent_iptv = models.BooleanField(
        default=False,
        verbose_name=_('IPTV legal consent'),
        help_text=_(
            'Mandatory for IPTV products: seller accepts full legal liability and DMCA enforcement policy.'
        ),
    )
    # ── Dynamic digital stock format ──────────────────────────────────────
    # Tells the fulfillment pipeline how to parse and render each consumed
    # `DigitalAssetStock.asset_content` row:
    #   - 'single' → one opaque value per row (license key, code, link, ...).
    #                Customer sees:   🔑 ABCD-1234
    #                Spoiler field:   {"license": "<value>"}
    #   - 'combo'  → "email:password" per row (split on the first colon).
    #                Customer sees:   📧 user@x.com  /  🔑 pass123
    #                Spoiler field:   {"email": "...", "password": "..."}
    #
    # Static `digital_url` / `digital_file` flow is unchanged when no stock
    # rows exist — it's the legacy fallback.
    STOCK_FORMAT_SINGLE = 'single'
    STOCK_FORMAT_COMBO = 'combo'
    STOCK_FORMAT_IPTV = 'iptv'
    STOCK_FORMAT_CHOICES = (
        (STOCK_FORMAT_SINGLE, _('Single keys/codes (one per line)')),
        (STOCK_FORMAT_COMBO, _('Email & Password (separated by ":")')),
        (STOCK_FORMAT_IPTV, _('IPTV / Xtream / M3U (one per line)')),
    )
    stock_format = models.CharField(
        max_length=16,
        choices=STOCK_FORMAT_CHOICES,
        default=STOCK_FORMAT_SINGLE,
        verbose_name=_('Digital stock format'),
        help_text=_(
            'Controls how each row of bulk-pasted digital stock is parsed '
            'and delivered. "single" stores one opaque value per row; '
            '"combo" expects "email:password" on every line; '
            '"iptv" stores Xtream credentials or M3U links (opaque per line).'
        ),
    )

    def get_required_fields_list(self):
        """Required checkout fields for AI progressive profiling (canonical keys)."""
        from discount.orders_ai import get_required_order_fields_for_product

        return get_required_order_fields_for_product(self)


class ProductImage(models.Model):
    """Product photos (at least one required when creating product from dashboard)."""
    product = models.ForeignKey(
        Products,
        on_delete=models.CASCADE,
        related_name='images',
    )
    image = models.ImageField(upload_to='products/%Y/%m/')
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return f"Image for {self.product.name} (#{self.order})"


class ProductVideo(models.Model):
    """Product videos (optional, from dashboard product form)."""
    product = models.ForeignKey(
        Products,
        on_delete=models.CASCADE,
        related_name='videos',
    )
    video = models.FileField(upload_to='products/videos/%Y/%m/')
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return f"Video for {self.product.name} (#{self.order})"


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
    channels = models.ManyToManyField('WhatsAppChannel', blank=True, related_name='invitations')
    
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
    can_create_templates = models.BooleanField(default=False)
    can_create_channels = models.BooleanField(default=False)
    extra = models.JSONField(default=dict, blank=True)  # للحاجات الإضافية لاحقًا

    def __str__(self):
        return f"Permissions for {self.user}"


class ExtraChannelSlotSubscription(models.Model):
    """
    Paid add-on: each active row grants +1 WhatsApp channel vs the plan base limit.
    Tied to a Stripe subscription; deactivated when that subscription ends.
    """
    billing_owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="extra_channel_slot_subscriptions",
    )
    stripe_subscription_id = models.CharField(max_length=255, unique=True)
    stripe_customer_id = models.CharField(max_length=255, blank=True, null=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["billing_owner", "active"]),
        ]

    def __str__(self):
        return f"Extra channel slot for {self.billing_owner_id} ({self.stripe_subscription_id})"


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
    out_for_delivery='Out for Delivery'
    
    # الخيارات المعروضة (الإنجليزية فقط)
    STATUS_CHOICES = [
        ('pending',              'Pending'),
        ('pending_payment',      'Pending Payment'),      # digital: awaiting customer payment transfer
        ('pending_verification', 'Pending Verification'), # digital: receipt received, awaiting merchant approval
        ('shipped',              'Shipped'),
        ('delivered',            'Delivered'),
        ('completed',            'Completed'),            # digital: file delivered to customer
        ('cancelled',            'Cancelled'),
        ('returned',             'Returned'),
        ('out_for_delivery',     'Out for Delivery'),
    ]
    agent = models.ForeignKey(
        CustomUser, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='simple_orders',
        verbose_name='الموظف المسؤول'
    )
    channel = models.ForeignKey(
        'WhatsAppChannel' , 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='simple_orders'
    )
    
    status = models.CharField(max_length=20)
    customer_city = models.CharField(max_length=100, verbose_name=_('مدينة العميل'), blank=True, null=True)
    customer_country = models.CharField(max_length=100, verbose_name=_(' coutry'), blank=True, null=True) 
    order_id = models.CharField(max_length=100, unique=True, verbose_name=_('رقم الطلبية'))
    tracking_number = models.CharField(max_length=100, verbose_name=_('رقم التتبع')  , null=True)
    sku = models.CharField(max_length=100, verbose_name=_('SKU'))
    customer_name = models.CharField(
        max_length=200, blank=True, null=True, verbose_name=_('اسم العميل'),
        help_text="Blank for Direct-Sale digital orders.",
    )
    customer_phone = models.CharField(max_length=20, verbose_name=_('هاتف العميل'))
    customer_email = models.EmailField(
        max_length=254, blank=True, null=True, verbose_name=_('بريد العميل'),
        help_text="Set for digital products that collect customer info.",
    )
    is_digital = models.BooleanField(
        default=False, db_index=True,
        help_text="Copied from the product at order creation time.",
    )
    product_name = models.CharField(max_length=200, verbose_name=_('اسم المنتج'))
    created_at = models.DateTimeField(auto_now_add=False, verbose_name=_('تاريخ الإنشاء'))
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0 ,verbose_name=_('السعر'))
    currency = models.CharField(max_length=10, default='SAR', null=True ,blank=True ,   verbose_name=_('العملة'))
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    created_by_ai = models.BooleanField(default=False, help_text="Order created via AI [ORDER_DATA] / save_order")
    created_by_bot_session = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Chat/session ID when order was created by AI (for tracing).",
    )
    # Google Sheets export status: blank = not applicable, pending = queued, success = exported, failed = export error (merchant can re-sync)
    sheets_export_status = models.CharField(
        max_length=20, blank=True, null=True,
        choices=[('', '—'), ('pending', 'Pending'), ('success', 'Success'), ('failed', 'Failed')],
        help_text="Google Sheets export status for dashboard re-sync",
    )
    sheets_export_error = models.TextField(
        blank=True, null=True,
        help_text="Last error message when Google Sheets sync failed (e.g. Permission Denied).",
    )
    shipping_company = models.CharField(
        max_length=200, blank=True, null=True,
        verbose_name=_('شركة الشحن'),
        help_text="Name of the shipping/delivery company.",
    )
    expected_delivery_date = models.DateField(
        null=True, blank=True,
        verbose_name=_('تاريخ التوصيل المتوقع'),
        help_text="Expected delivery date.",
    )
    order_notes = models.TextField(
        blank=True,
        null=True,
        verbose_name=_('ملاحظات الطلب'),
        help_text="Delivery timing, alternate phone, and other instructions (appended by AI or staff).",
    )
    # ── Post-sale digital support (replacement / complaint workflow) ────────
    SUPPORT_STATUS_NONE = 'none'
    SUPPORT_STATUS_AWAITING_PROOF = 'awaiting_proof'
    SUPPORT_STATUS_UNDER_REVIEW = 'under_review'
    SUPPORT_STATUS_RESOLVED = 'resolved'
    SUPPORT_STATUS_REJECTED = 'rejected'
    SUPPORT_STATUS_CHOICES = [
        (SUPPORT_STATUS_NONE, 'None'),
        (SUPPORT_STATUS_AWAITING_PROOF, 'Awaiting proof'),
        (SUPPORT_STATUS_UNDER_REVIEW, 'Under review'),
        (SUPPORT_STATUS_RESOLVED, 'Resolved'),
        (SUPPORT_STATUS_REJECTED, 'Rejected'),
    ]
    support_status = models.CharField(
        max_length=20,
        choices=SUPPORT_STATUS_CHOICES,
        default=SUPPORT_STATUS_NONE,
        db_index=True,
        help_text=(
            'Post-sale support state for completed digital orders. '
            'Tracks complaint intake, proof collection, merchant review, and resolution.'
        ),
    )
    complaint_summary = models.TextField(
        blank=True,
        null=True,
        help_text="Brief AI-generated summary of the customer's support issue.",
    )
    payment_rejection_reason = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text=(
            "Merchant-provided reason when a payment receipt was rejected; "
            "cleared on approval. Order returns to pending_payment for resubmission."
        ),
    )
    payment_rejection_notice_text = models.TextField(
        blank=True,
        null=True,
        help_text=(
            "Full localized WhatsApp notice sent to the customer after rejection "
            "(saved when the outbound message is delivered)."
        ),
    )
    class Meta:
        verbose_name = _('طلب مبسط')
        verbose_name_plural = _('طلبات مبسطة')
        ordering = ['-created_at']

    def __str__(self):
        display = self.customer_name or self.customer_phone or str(self.order_id)
        return f"{self.tracking_number} - {display}"


class WhatsAppFlowSubmission(models.Model):
    """A completed native WhatsApp Flow form (lead, feedback, or order)."""

    PURPOSE_LEAD = "lead_generation"
    PURPOSE_FEEDBACK = "feedback"
    PURPOSE_ORDER = "collect_order"
    PURPOSE_CHOICES = [
        (PURPOSE_LEAD, "Generate leads"),
        (PURPOSE_FEEDBACK, "Receive feedback"),
        (PURPOSE_ORDER, "Collect order"),
    ]

    channel = models.ForeignKey(
        "WhatsAppChannel",
        on_delete=models.CASCADE,
        related_name="whatsapp_flow_submissions",
    )
    contact = models.ForeignKey(
        "Contact",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="whatsapp_flow_submissions",
    )
    automation_flow = models.ForeignKey(
        "Flow",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="whatsapp_flow_submissions",
    )
    node = models.ForeignKey(
        "Node",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="whatsapp_flow_submissions",
    )
    product = models.ForeignKey(
        Products,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="whatsapp_flow_submissions",
    )
    order = models.ForeignKey(
        SimpleOrder,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="whatsapp_flow_submissions",
    )
    purpose = models.CharField(max_length=32, choices=PURPOSE_CHOICES, default=PURPOSE_LEAD)
    customer_phone = models.CharField(max_length=30, db_index=True)
    customer_name = models.CharField(max_length=200, blank=True, default="")
    payload = models.JSONField(default=dict, blank=True)
    flow_token = models.CharField(max_length=200, blank=True, default="", db_index=True)
    meta_flow_id = models.CharField(max_length=64, blank=True, default="")
    whatsapp_message_id = models.CharField(max_length=100, blank=True, null=True, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["channel", "created_at"]),
            models.Index(fields=["channel", "customer_phone"]),
        ]
        verbose_name = "WhatsApp Flow submission"
        verbose_name_plural = "WhatsApp Flow submissions"

    def __str__(self):
        return f"{self.get_purpose_display()} · {self.customer_phone} · {self.created_at:%Y-%m-%d %H:%M}"


class UserCheckoutFormCopy(models.Model):
    """Per-user order-form message (header/body/footer/CTA) for a catalog product."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="checkout_form_copies",
    )
    product = models.ForeignKey(
        Products,
        on_delete=models.CASCADE,
        related_name="user_checkout_form_copies",
    )
    header_text = models.CharField(max_length=60, blank=True, default="")
    body_text = models.CharField(max_length=1024, blank=True, default="")
    footer_text = models.CharField(max_length=60, blank=True, default="")
    cta_label = models.CharField(max_length=20, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "product")
        verbose_name = "User checkout form copy"
        verbose_name_plural = "User checkout form copies"

    def __str__(self):
        return f"user={self.user_id} product={self.product_id}"












# tracking stuff activity hee



from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

class Activity(models.Model):
    # المستخدم الذي قام بالنشاط
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='activities', null=True, blank=True)
     
    ACTIVITY_TYPES = (
        # ── Auth ──
        ('login', 'User Login'),
        ('logout', 'User Logout'),
        ('login_failed', 'Login Failed'),
        ('password_changed', 'Password Changed'),
        ('2fa_enabled', 'Two-Factor Auth Enabled'),
        ('2fa_disabled', 'Two-Factor Auth Disabled'),
        ('profile_updated', 'Profile Updated'),

        # ── Team / Users ──
        ('user_created', 'User Created'),
        ('user_updated', 'User Updated'),
        ('user_deleted', 'User Deleted'),
        ('invite_sent', 'Team Invite Sent'),
        ('invite_accepted', 'Team Invite Accepted'),
        ('member_removed', 'Team Member Removed'),

        # ── Orders (CRM) ──
        ('order_created', 'Order Created'),
        ('order_updated', 'Order Updated'),
        ('order_status_changed', 'Order Status Changed'),
        ('order_agent_changed', 'Order Agent Changed'),
        ('order_bulk_assign', 'Orders Bulk Assigned'),
        ('order_imported', 'Orders Imported'),
        ('order_deleted', 'Order Deleted'),

        # ── SimpleOrder (WhatsApp) ──
        ('simple_order_created', 'Simple Order Created'),

        # ── WhatsApp Messaging ──
        ('wa_message_sent', 'WhatsApp Message Sent'),
        ('wa_channel_created', 'WhatsApp Channel Created'),
        ('wa_channel_deleted', 'WhatsApp Channel Deleted'),
        ('wa_channel_updated', 'WhatsApp Channel Settings Updated'),
        ('wa_template_created', 'WhatsApp Template Created'),
        ('wa_template_updated', 'WhatsApp Template Updated'),
        ('wa_contact_assigned', 'Contact Assigned to Agent'),
        ('wa_contact_crm_updated', 'Contact CRM Updated'),

        # ── Flows / AutoReply ──
        ('flow_created', 'Flow Created'),
        ('flow_updated', 'Flow Updated'),
        ('flow_deleted', 'Flow Deleted'),
        ('autoreply_created', 'AutoReply Created'),
        ('autoreply_updated', 'AutoReply Updated'),
        ('autoreply_deleted', 'AutoReply Deleted'),

        # ── Marketing ──
        ('campaign_flow_created', 'Campaign Flow Created'),
        ('campaign_flow_deleted', 'Campaign Flow Deleted'),

        # ── Products ──
        ('product_updated', 'Product Updated'),
        ('product_filter', 'Product Filtered'),

        # ── Online Presence ──
        ('ws_connect', 'WebSocket Connected'),
        ('ws_disconnect', 'WebSocket Disconnected'),

        # ── Misc ──
        ('search_performed', 'Search Performed'),
        ('filter_applied', 'Filter Applied'),
        ('order_tracked', 'Order Tracked'),
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
    token=models.UUIDField(default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    script = models.TextField(blank=True, null=True)   
    description = models.TextField(blank=True, null=True)

    is_active = models.BooleanField(default=True)
    plan_type = models.CharField(max_length=20, default='free')


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
    visit_meta = models.JSONField(default=dict, blank=True, help_text="Full payload from capture_visit (url, referrer, device, event, time_spent, etc.)")

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

# Voice–TTS dialect (LLM output must match the selected ElevenLabs voice accent).
# Must be defined before WhatsAppChannel / VoiceGalleryEntry / VoiceCloneRequest / VoicePersona.
VOICE_DIALECT_CHOICES = [
    ("MA_DARIJA", "Moroccan Darija"),
    ("SA_ARABIC", "Saudi Arabic"),
    ("EG_ARABIC", "Egyptian Arabic"),
    ("MSA", "Modern Standard Arabic"),
    ("LEV_ARABIC", "Levantine Arabic"),
    ("GULF_ARABIC", "Gulf Arabic"),
    ("OTHER", "Other / Multilingual"),
]
VOICE_DIALECT_DEFAULT = "MA_DARIJA"


def dialect_key_to_display(key) -> str:
    """Human label for a dialect choice key (used by APIs and voice_dialect service)."""
    k = (key or "").strip() or VOICE_DIALECT_DEFAULT
    lookup = dict(VOICE_DIALECT_CHOICES)
    return lookup.get(k) or lookup.get(VOICE_DIALECT_DEFAULT, "Moroccan Darija")


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

    # AI Coaching: rules set by Admin via Coach chat; appended at end of sales agent system prompt
    ai_override_rules = models.TextField(
        blank=True,
        default="",
        help_text="Custom sales rules from Admin coaching; overrides default AI behavior for this channel.",
    )

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

    # -------------------------------------------------------------------------
    # Weighted Chat Routing: use ChannelAgentRouting for per-agent routing_percentage
    # and is_accepting_chats. Contact.assigned_agent is the sticky assignment.
    # -------------------------------------------------------------------------

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
         
    # --- 1. إعدادات البروفايل (تزامن مع Meta) ---
    business_about = models.CharField(max_length=130, blank=True, help_text="الحالة النصية في واتساب")
    business_description = models.TextField(blank=True, help_text="وصف النشاط التجاري")
    business_address = models.CharField(max_length=256, blank=True)
    business_email = models.EmailField(blank=True)
    business_website = models.URLField(blank=True)

    # --- 2. إعدادات الأتمتة ---
    enable_welcome_msg = models.BooleanField(default=False)
    welcome_msg_body = models.TextField(blank=True, default="مرحباً بك! كيف يمكننا مساعدتك؟")
    
    # --- 3. إعدادات النظام (System Behavior) ---
    enable_collision_detection = models.BooleanField(default=True, help_text="تفعيل تنبيه التصادم بين الموظفين")
    show_blue_ticks = models.BooleanField(default=True, help_text="إظهار علامة القراءة للعميل عند فتح المحادثة")
    profile_image = models.ImageField(upload_to='channel_profiles/', blank=True, null=True, help_text="Local profile image for dashboard")
    # --- 4. صلاحيات الموظفين ---
    allow_agents_delete_msg = models.BooleanField(default=False, help_text="السماح للموظفين بحذف الرسائل")

    # --- 5. AI Voice & Sales Intelligence ---
    ai_auto_reply = models.BooleanField(default=False, help_text="Full autopilot: AI replies when no flow matches")
    ai_voice_enabled = models.BooleanField(default=False, help_text="Send AI replies as voice messages")
    voice_provider = models.CharField(
        max_length=20,
        choices=[('OPENAI', 'OpenAI TTS'), ('ELEVENLABS', 'ElevenLabs')],
        default='OPENAI',
    )
    voice_gender = models.CharField(
        max_length=10,
        choices=[('MALE', 'Male'), ('FEMALE', 'Female')],
        default='FEMALE',
    )
    voice_delay_seconds = models.PositiveSmallIntegerField(
        default=20,
        help_text="Delay before sending voice (10-30 sec)",
    )
    ai_order_capture = models.BooleanField(default=True, help_text="Automatically extract and save orders from conversations")
    CHANNEL_AI_LLM_ENGINE_CHOICES = [
        ("AUTO", "Auto (dialect-based routing)"),
        ("GPT_4O", "GPT-4o (OpenAI)"),
        ("CLAUDE_3_5", "Claude 3.5 Sonnet (Anthropic)"),
    ]
    ai_llm_engine = models.CharField(
        max_length=20,
        choices=CHANNEL_AI_LLM_ENGINE_CHOICES,
        default="AUTO",
        blank=True,
        help_text="Default LLM for AI agent replies on this channel. Flow node AI Engine overrides when set to GPT or Claude.",
    )
    elevenlabs_api_key = models.CharField(max_length=255, null=True, blank=True)
    voice_cloning_enabled = models.BooleanField(default=False, help_text="Clone your voice (Premium only)")
    # Advanced Voice Studio (StoreSettings)
    VOICE_LANG_CHOICES = [
        ("AUTO", "Auto-Detect"),
        ("AR_MA", "Arabic (Morocco)"),
        ("AR_SA", "Arabic (Saudi)"),
        ("FR_FR", "French (France)"),
        ("EN_US", "English (US)"),
    ]
    voice_language = models.CharField(max_length=10, choices=VOICE_LANG_CHOICES, default="AUTO")
    voice_stability = models.FloatField(default=0.5, help_text="0.0-1.0 Emotion/Stability")
    voice_similarity = models.FloatField(default=0.75, help_text="0.0-1.0 Similarity/Clarity")
    cloned_voice_id = models.CharField(max_length=255, null=True, blank=True, help_text="ElevenLabs cloned voice ID")
    ai_voice_provider = models.CharField(
        max_length=20,
        choices=[("OPENAI", "OpenAI TTS"), ("ELEVENLABS", "ElevenLabs")],
        default="OPENAI",
    )
    # Multilingual v2 & Voice Gallery (native-friendly Arabic)
    elevenlabs_model_id = models.CharField(
        max_length=64,
        default="eleven_multilingual_v2",
        help_text="ElevenLabs model; use eleven_multilingual_v2 for natural Arabic.",
    )
    selected_voice_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="ElevenLabs voice ID from the gallery (e.g. Layla, Rachel).",
    )
    voice_dialect = models.CharField(
        max_length=32,
        choices=VOICE_DIALECT_CHOICES,
        default=VOICE_DIALECT_DEFAULT,
        help_text="Dialect aligned with the current voice (gallery selection or approved clone).",
    )
    voice_preview_url = models.URLField(
        max_length=500,
        null=True,
        blank=True,
        help_text="Sample audio URL for the selected voice in the UI.",
    )
    # Notify channel owner when AI creates an order (Email or WhatsApp)
    ORDER_NOTIFY_CHOICES = [
        ("", "Off"),
        ("EMAIL", "Email"),
        ("WHATSAPP", "WhatsApp"),
    ]
    order_notify_method = models.CharField(
        max_length=20,
        choices=ORDER_NOTIFY_CHOICES,
        default="",
        blank=True,
        help_text="Send owner a notification when AI creates an order.",
    )
    order_notify_email = models.EmailField(
        max_length=254,
        null=True,
        blank=True,
        help_text="Email address for order notifications (when method is Email).",
    )
    order_notify_whatsapp_phone = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        help_text="Phone (with country code) for WhatsApp order notifications.",
    )
    # Weighted Chat Routing: AI share and dynamic redistribution
    ai_routing_percentage = models.PositiveSmallIntegerField(
        default=0,
        help_text="AI share of new leads when Full Autopilot is ON (0-100). Human percentages + this must equal 100.",
    )
    dynamic_offline_redistribution = models.BooleanField(
        default=False,
        help_text="When ON, exclude offline agents and redistribute their percentages among online agents only.",
    )


class VoiceGalleryEntry(models.Model):
    """
    Voices shown in the Voice Gallery (settings UI + API): ElevenLabs IDs or OpenAI TTS names.
    Manage rows in Django Admin: add/remove voices, set preview MP3 filename under
    static/audio/voice-previews/, tags for filters, sort_order, and ``language_code``
    for locale filtering (e.g. AR_MA, FR_FR).
    """

    GENDER_CHOICES = [("MALE", "Male"), ("FEMALE", "Female")]

    PROVIDER_ELEVENLABS = "ELEVENLABS"
    PROVIDER_OPENAI = "OPENAI"
    PROVIDER_CHOICES = [
        (PROVIDER_ELEVENLABS, "ElevenLabs"),
        (PROVIDER_OPENAI, "OpenAI"),
    ]

    provider = models.CharField(
        max_length=20,
        choices=PROVIDER_CHOICES,
        default=PROVIDER_ELEVENLABS,
        help_text="TTS backend: ElevenLabs API or OpenAI audio.speech (tts-1).",
    )

    elevenlabs_voice_id = models.CharField(
        max_length=64,
        unique=True,
        help_text="ElevenLabs voice_id, or OpenAI voice name (alloy, echo, fable, onyx, nova, shimmer) when provider is OpenAI.",
    )
    name = models.CharField(max_length=255, help_text="Short display name.")
    label = models.CharField(
        max_length=255,
        blank=True,
        help_text="Optional longer label; defaults to name if empty.",
    )
    preview_file = models.CharField(
        max_length=255,
        blank=True,
        help_text="Filename only, e.g. rachel.mp3 — file must live under static/audio/voice-previews/",
    )
    preview_audio_file = models.FileField(
        upload_to="voice_gallery_previews/",
        null=True,
        blank=True,
        help_text="Optional MP3 upload for the preview. If set, the gallery uses this file instead of `preview_file`.",
    )
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, default="FEMALE")
    tags = models.JSONField(
        default=_default_json_list,
        blank=True,
        help_text='List of strings, e.g. ["Multilingual", "High Quality"]. Include "French" for French filter.',
    )
    native_arabic = models.BooleanField(
        default=False,
        help_text="If True, voice appears in “Optimized for Arabic” gallery filter.",
    )
    language_code = models.CharField(
        max_length=32,
        blank=True,
        default="",
        db_index=True,
        help_text="Primary locale for filtering, e.g. AR_MA, FR_FR, EN_US (use underscore). "
        "Leave empty for multilingual / any language.",
    )
    dialect = models.CharField(
        max_length=32,
        choices=VOICE_DIALECT_CHOICES,
        default=VOICE_DIALECT_DEFAULT,
        db_index=True,
        help_text="Primary spoken dialect for this voice; drives LLM output to match TTS pronunciation.",
    )
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(
        default=0,
        help_text="Lower numbers appear first in the gallery.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "id"]
        verbose_name = "Voice Gallery entry"
        verbose_name_plural = "Voice Gallery entries"

    def __str__(self):
        return f"{self.name} ({self.elevenlabs_voice_id})"


class VoiceCloneRequest(models.Model):
    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
    ]

    merchant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="voice_clone_requests",
    )
    audio_file = models.FileField(upload_to="voice_clone_requests/%Y/%m/")
    consent_agreed = models.BooleanField(default=False)
    dialect = models.CharField(
        max_length=32,
        choices=VOICE_DIALECT_CHOICES,
        default=VOICE_DIALECT_DEFAULT,
        help_text="Dialect the merchant declares for this sample (stored with the request and applied on approval).",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Voice clone request"
        verbose_name_plural = "Voice clone requests"

    def __str__(self):
        return f"VoiceCloneRequest #{self.id} for {self.merchant_id} ({self.status})"


class CoachConversationMessage(models.Model):
    """
    Persisted messages between an admin (user) and the AI coach for a channel.
    Used to show conversation history when the user opens the Coach again.
    """
    channel = models.ForeignKey(
        WhatsAppChannel,
        on_delete=models.CASCADE,
        related_name="coach_conversation_messages",
    )
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="coach_conversation_messages",
    )
    role = models.CharField(max_length=20, choices=[("user", "user"), ("assistant", "assistant")])
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.channel_id}/{self.user_id} {self.role} @ {self.created_at}"


class ChannelAgentRouting(models.Model):
    """
    Per-channel, per-agent routing config for Weighted Chat Routing.
    Agents are CustomUser; channel is WhatsAppChannel. Sum of routing_percentage
    for all agents in a channel must equal 100 when routing is enabled.
    """
    channel = models.ForeignKey(
        WhatsAppChannel,
        on_delete=models.CASCADE,
        related_name="agent_routing_configs",
    )
    agent = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="channel_routing_configs",
    )
    routing_percentage = models.PositiveSmallIntegerField(
        default=0,
        help_text="Weight for new lead distribution (0-100). Sum for channel must be 100.",
    )
    is_accepting_chats = models.BooleanField(
        default=True,
        help_text="If False, agent is excluded from new assignments; existing sticky assignments remain.",
    )

    class Meta:
        db_table = "discount_channelagentrouting"
        unique_together = [("channel", "agent")]
        verbose_name = "Channel Agent Routing"
        verbose_name_plural = "Channel Agent Routings"

    def __str__(self):
        return f"{self.channel.name} / {getattr(self.agent, 'username', self.agent_id)} ({self.routing_percentage}%)"


class Message(models.Model):
    user = models.ForeignKey(
        CustomUser, 
        on_delete=models.SET_NULL, # إذا حذفنا الموظف، تبقى رسائله لكن بدون رابط
        null=True, 
        blank=True,
        related_name="messages",
        help_text="الموظف الذي أرسل الرسالة أو كتب الملاحظة"
    )
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
    captions = models.TextField(null=True, blank=True)
    
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
    type = models.CharField(max_length=50, blank=True, null=True) 
    
    is_internal = models.BooleanField(default=False, help_text="إذا كانت True، لا تظهر للعميل ولا ترسل للواتساب")

    # Payment receipt flags — set by the webhook when an inbound image/document
    # arrives while the linked order is in 'pending_payment' status.
    is_payment_receipt = models.BooleanField(
        default=False,
        db_index=True,
        help_text="True when the message was identified as a payment receipt from the customer.",
    )
    receipt_status = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        choices=[
            ('pending_review', 'Pending Review'),
            ('approved',       'Approved'),
            ('rejected',       'Rejected'),
        ],
        help_text="Merchant review status for this payment receipt.",
    )

    # ── Digital-product delivery spoiler ──────────────────────────────────
    # `is_digital_delivery` flags an outgoing fulfillment message that
    # contains a sensitive asset (download URL, license key, credentials)
    # which the dashboard MUST hide from non-owner employees.
    #
    # `encrypted_asset` stores the sensitive payload as Fernet ciphertext
    # (see discount.crypto.{encrypt_token, decrypt_token}) so it is never
    # readable at rest or in the chat-list JSON. Plaintext is exposed ONLY
    # via the strict owner-only reveal endpoint.
    #
    # We use TextField (not CharField(500)) because Fernet ciphertext +
    # base64 overhead routinely exceeds 500 chars for the very payloads
    # this feature exists to protect (signed S3 URLs, multi-line keys).
    is_digital_delivery = models.BooleanField(
        default=False,
        db_index=True,
        help_text="True when this outgoing message carries a sensitive digital "
                  "asset (download URL/key) that must be revealed only to the "
                  "store owner via the secure reveal endpoint.",
    )
    encrypted_asset = models.TextField(
        blank=True,
        null=True,
        help_text="Fernet-encrypted sensitive payload (download URL, license "
                  "key, credentials). Never expose at rest or in chat JSON; "
                  "decrypt only inside the owner-gated reveal endpoint.",
    )

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

    # ── Encrypted-asset helpers (mirror StorePaymentMethod's pattern) ─────
    #
    # Storage format on `encrypted_asset`:
    #   • Single sensitive value (legacy)  →  Fernet(plaintext)
    #   • Multi-field credentials          →  Fernet(json.dumps({"_fields": {...}}))
    #
    # The `_fields` envelope discriminator lets `get_decrypted_asset_fields`
    # cleanly distinguish a structured dict from a legacy plain URL so the
    # frontend can render the Telegram-style spoiler with one labelled
    # placeholder per field.
    def set_encrypted_asset(self, raw_value):
        """
        Encrypt `raw_value` at rest using the project's Fernet key.

        Accepts:
          - str: single sensitive value (download URL, license key, …)
          - dict[str, str]: multi-field credentials, e.g.
                {"email": "...", "password": "...", "link": "..."}

        Empty / None / empty-dict input clears the field. The caller is
        responsible for also setting `is_digital_delivery=True` (the two
        go hand in hand).
        """
        if not raw_value:
            self.encrypted_asset = None
            return
        # Lazy import to avoid circular references on app loading.
        from discount.crypto import encrypt_token
        if isinstance(raw_value, dict):
            import json as _json
            normalized = {str(k): ('' if v is None else str(v)) for k, v in raw_value.items()}
            if not normalized:
                self.encrypted_asset = None
                return
            envelope = _json.dumps({"_fields": normalized}, ensure_ascii=False)
            self.encrypted_asset = encrypt_token(envelope)
        else:
            self.encrypted_asset = encrypt_token(str(raw_value))

    def get_decrypted_asset(self):
        """
        Return the plaintext sensitive asset (raw, single value form), or
        '' if absent / corrupted.

        Prefer `get_decrypted_asset_fields()` in new code — it normalizes
        both legacy strings and dict envelopes into a uniform `{key: val}`
        mapping for the frontend spoiler renderer.

        IMPORTANT: this method MUST only ever be called inside a view that
        has already enforced the strict owner-only RBAC check. It will
        never raise on a corrupted ciphertext (e.g. rotated key) — it
        returns '' so reveal endpoints fail closed.
        """
        ciphertext = self.encrypted_asset
        if not ciphertext:
            return ''
        try:
            from discount.crypto import decrypt_token
            return decrypt_token(ciphertext)
        except Exception:
            return ''

    def get_decrypted_asset_fields(self):
        """
        Return a `{field_name: plaintext_value}` dict suitable for the
        Telegram-style spoiler reveal API.

        Storage detection:
          1. Multi-field envelope `{"_fields": {...}}` → return inner dict.
          2. Legacy plaintext URL                       → return `{"link": "<url>"}`.
          3. Empty / corrupted ciphertext              → return `{}` (fails closed).

        Always returns a dict so callers can iterate without type-checking.
        Same RBAC constraint as `get_decrypted_asset`: callers MUST have
        enforced owner-only authorization before invoking this.
        """
        plaintext = self.get_decrypted_asset()
        if not plaintext:
            return {}
        import json as _json
        try:
            parsed = _json.loads(plaintext)
        except (ValueError, TypeError):
            return {"link": plaintext}
        if isinstance(parsed, dict) and isinstance(parsed.get("_fields"), dict):
            return {str(k): str(v) for k, v in parsed["_fields"].items()}
        return {"link": plaintext}


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
    header_document = models.FileField(upload_to='templates/headers/', blank=True, null=True)
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

    @property
    def flow_data(self):
        """Backward compatibility: flow_data as alias for config (nodes/connections JSON)."""
        return self.config if isinstance(self.config, dict) else {}

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


class VoicePersona(models.Model):
    """
    Sales Agent persona for the Flow Builder AI node: name, voice_id, provider, and behavioral prompt.
    System-wide (is_system=True, owner=None) or user-cloned (owner set).
    """
    TIER_STANDARD = "standard"   # Free for all
    TIER_PREMIUM = "premium"     # Requires Premium plan to select
    TIER_CHOICES = [(TIER_STANDARD, "Standard"), (TIER_PREMIUM, "Premium")]

    PROVIDER_ELEVENLABS = "ELEVENLABS"
    PROVIDER_OPENAI = "OPENAI"
    PROVIDER_CHOICES = [(PROVIDER_ELEVENLABS, "ElevenLabs"), (PROVIDER_OPENAI, "OpenAI")]

    name = models.CharField(max_length=120, help_text="e.g. Laila, Sami, Hiba - Luxury Consultant")
    description = models.CharField(max_length=255, blank=True, help_text="e.g. Soft, calm, perfect for cosmetics")
    voice_id = models.CharField(max_length=120, help_text="ElevenLabs or OpenAI voice ID")
    provider = models.CharField(
        max_length=20,
        choices=PROVIDER_CHOICES,
        default=PROVIDER_ELEVENLABS,
        help_text="TTS provider for this voice",
    )
    is_system = models.BooleanField(default=True, help_text="System-wide persona vs user-cloned")
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="cloned_voice_personas",
        help_text="Set for user-cloned voices; null for system personas",
    )
    behavioral_instructions = models.TextField(
        blank=True,
        help_text="e.g. Use high-end vocabulary, be extremely polite, use specific emojis.",
    )
    language_code = models.CharField(max_length=20, default="AR_MA", help_text="AR_MA, FR_FR, EN_US, etc.")
    dialect = models.CharField(
        max_length=32,
        choices=VOICE_DIALECT_CHOICES,
        default=VOICE_DIALECT_DEFAULT,
        help_text="Spoken dialect for this voice (especially user clones); drives LLM/TTS alignment.",
    )
    # System personas only: standard (free) or premium (requires plan)
    tier = models.CharField(
        max_length=20,
        choices=TIER_CHOICES,
        default=TIER_STANDARD,
        help_text="For system personas: standard=free, premium=paid only",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_system", "name"]
        verbose_name = "Voice Persona"
        verbose_name_plural = "Voice Personas"

    def __str__(self):
        return self.name


class Node(models.Model):
    CONTEXT_SOURCE_CHOICES = [
        ('MANUAL', 'Manual'),
        ('URL_SCRAPER', 'URL Scraper'),
    ]
    AI_ENGINE_AUTO = "AUTO"
    AI_ENGINE_GPT_4O = "GPT_4O"
    AI_ENGINE_CLAUDE_3_5 = "CLAUDE_3_5"
    AI_ENGINE_CHOICES = [
        (AI_ENGINE_AUTO, "Auto"),
        (AI_ENGINE_GPT_4O, "GPT-4o"),
        (AI_ENGINE_CLAUDE_3_5, "Claude 3.5"),
    ]

    flow = models.ForeignKey(Flow, on_delete=models.CASCADE, related_name='nodes')
    node_type = models.CharField(max_length=30)
    node_id = models.CharField(max_length=100)

    position_x = models.FloatField(default=0)
    position_y = models.FloatField(default=0)
    content_text = models.TextField(blank=True, null=True)
    content_media_url = models.URLField(max_length=1000, blank=True, null=True)
    delay = models.IntegerField(default=0)

    started_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    media_type = models.CharField(max_length=20, blank=True, null=True)

    # AI Agent node (node_type = 'ai-agent')
    product_context = models.TextField(blank=True, null=True, help_text="Product details: Name, Price, Specs, Shipping")
    context_source = models.CharField(max_length=20, choices=CONTEXT_SOURCE_CHOICES, default='MANUAL', blank=True)
    voice_enabled = models.BooleanField(default=False, help_text="Use voice_engine for response")
    ai_model_config = models.JSONField(default=dict, blank=True, help_text="temperature, model_id, etc.")
    # Per-node voice & response (Elite Sales Consultant / Multi-Modal)
    RESPONSE_MODE_CHOICES = [
        ("TEXT_ONLY", "Text only"),
        ("AUDIO_ONLY", "Audio only"),
        ("AUTO_SMART", "Auto (text for short, audio for pitch/closing)"),
    ]
    response_mode = models.CharField(
        max_length=20, choices=RESPONSE_MODE_CHOICES, default="TEXT_ONLY", blank=True,
        help_text="TEXT_ONLY, AUDIO_ONLY, or AUTO_SMART",
    )
    node_voice_id = models.CharField(max_length=100, blank=True, null=True, help_text="Voice ID for this node (e.g. ElevenLabs) – legacy; prefer persona")
    node_language = models.CharField(max_length=20, blank=True, null=True, help_text="e.g. AR_MA, FR_FR, EN_US")
    node_gender = models.CharField(max_length=10, blank=True, null=True, help_text="FEMALE or MALE")
    ai_engine = models.CharField(
        max_length=20,
        choices=AI_ENGINE_CHOICES,
        default=AI_ENGINE_AUTO,
        blank=True,
        help_text="AI engine selection for this node: Auto, GPT-4o, or Claude 3.5.",
    )
    # Persona gallery: one persona per node (voice + behavioral prompt)
    persona = models.ForeignKey(
        VoicePersona,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="nodes",
        help_text="Sales agent persona (voice + behavior); overrides node_voice_id when set",
    )
    voice_stability = models.FloatField(null=True, blank=True, help_text="0.0–1.0 for ElevenLabs")
    voice_similarity = models.FloatField(null=True, blank=True, help_text="0.0–1.0 for ElevenLabs")
    voice_speed = models.FloatField(null=True, blank=True, help_text="0.5–1.5 for ElevenLabs")

    def __str__(self):
        return f"Node {self.id} ({self.node_type}) in Flow {self.flow.name}"


class NodeMedia(models.Model):
    """Media assets (images/videos) linked to an AI Agent node for multi-modal responses."""
    FILE_TYPE_IMAGE = "Image"
    FILE_TYPE_VIDEO = "Video"
    FILE_TYPE_CHOICES = [(FILE_TYPE_IMAGE, "Image"), (FILE_TYPE_VIDEO, "Video")]

    node = models.ForeignKey(Node, on_delete=models.CASCADE, related_name="media_assets")
    file = models.FileField(upload_to="flow_node_media/%Y/%m/", blank=True, null=True, max_length=500)
    file_type = models.CharField(max_length=10, choices=FILE_TYPE_CHOICES, default=FILE_TYPE_IMAGE)
    description = models.CharField(max_length=255, blank=True, help_text="Label for GPT, e.g. Product Close-up, How-to-use Video")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = "Node media"
        verbose_name_plural = "Node media"

    def __str__(self):
        return f"{self.get_file_type_display()}: {self.description or self.file.name}"


class ChatSession(models.Model):
    """
    Persistent AI Agent session: keeps product context across ALL messages indefinitely.
    Scoped per channel + customer_phone (unique constraint).

    A session is NEVER expired by time — e-commerce users return on payday (20-30 days)
    and must resume seamlessly without re-sending trigger keywords.

    Explicit resolution only:
      is_completed=True  — order successfully submitted (submit_customer_order tool fired)
      is_expired=True    — user explicitly cancelled (reset keyword) or HITL handover

    HITL: ai_enabled=False stops the AI; merchant handles the chat manually.
    """
    channel = models.ForeignKey(
        WhatsAppChannel,
        on_delete=models.CASCADE,
        related_name="chat_sessions",
    )
    customer_phone = models.CharField(max_length=32, db_index=True)
    active_node = models.ForeignKey(
        Node,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="active_sessions",
        help_text="Current product/AI node context",
    )
    active_product = models.ForeignKey(
        Products,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="active_product_sessions",
        help_text="Persistent product memory for AI context (survives prompt truncation).",
    )
    is_expired = models.BooleanField(default=False)
    is_completed = models.BooleanField(
        default=False,
        db_index=True,
        help_text=(
            "True when the customer successfully completed the Node goal "
            "(e.g. order submitted via submit_customer_order). "
            "Session becomes inactive; next message starts fresh trigger evaluation."
        ),
    )
    context_data = models.JSONField(default=dict, blank=True)
    last_interaction = models.DateTimeField(auto_now=True)
    # Human-in-the-Loop (HITL)
    ai_enabled = models.BooleanField(
        default=True,
        help_text="If False, AI does not process messages; merchant handles the chat.",
    )
    handover_reason = models.CharField(
        max_length=120,
        blank=True,
        help_text="e.g. Customer asked for human, Sentiment detected",
    )
    last_manual_message_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the merchant last sent a manual message.",
    )
    # AI Sentinel (cheap intent check after N consecutive user messages)
    consecutive_user_messages = models.PositiveIntegerField(
        default=0,
        help_text="Increments per user message turn; checkpoint runs at threshold.",
    )
    requires_human = models.BooleanField(
        default=False,
        help_text="True when merchant should take over (e.g. sentinel flagged spam/time-wasting).",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["channel", "customer_phone"],
                name="unique_channel_customer_session",
            )
        ]
        indexes = [
            models.Index(fields=["channel", "customer_phone"]),
            models.Index(fields=["channel", "requires_human"]),
        ]
        verbose_name = "Chat session"
        verbose_name_plural = "Chat sessions"

    def __str__(self):
        return f"Session {self.channel_id}:{self.customer_phone} (expired={self.is_expired})"


class HandoverLog(models.Model):
    """Record every handover event (AI → human) for analytics and merchant review."""
    channel = models.ForeignKey(
        WhatsAppChannel,
        on_delete=models.CASCADE,
        related_name="handover_logs",
    )
    customer_phone = models.CharField(max_length=32, db_index=True)
    reason = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["channel", "created_at"])]
        verbose_name = "Handover log"
        verbose_name_plural = "Handover logs"

    def __str__(self):
        return f"Handover {self.customer_phone} @ {self.created_at} ({self.reason})"


class Connection(models.Model):
    flow = models.ForeignKey(Flow, on_delete=models.CASCADE, related_name="connections")
    from_node = models.ForeignKey(Node, on_delete=models.CASCADE, related_name="outgoing_connections")
    to_node = models.ForeignKey(Node, on_delete=models.CASCADE, related_name="incoming_connections")
    data = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"{self.from_node.node_id} → {self.to_node.node_id}"


class FollowUpNode(models.Model):
    """
    Config for the Smart Follow-up flow node. One-to-one with Node (node_type='follow-up').
    Schedules re-engagement after delay_hours if the customer does not reply.
    """
    RESPONSE_TYPE_TEXT = "TEXT"
    RESPONSE_TYPE_AUDIO = "AUDIO"
    RESPONSE_TYPE_IMAGE = "IMAGE"
    RESPONSE_TYPE_VIDEO = "VIDEO"
    RESPONSE_TYPE_CHOICES = [
        (RESPONSE_TYPE_TEXT, "Text"),
        (RESPONSE_TYPE_AUDIO, "Audio"),
        (RESPONSE_TYPE_IMAGE, "Image"),
        (RESPONSE_TYPE_VIDEO, "Video"),
    ]

    node = models.OneToOneField(
        Node,
        on_delete=models.CASCADE,
        related_name="follow_up_config",
    )
    delay_hours = models.PositiveIntegerField(default=6, help_text="Hours to wait before sending follow-up")
    response_type = models.CharField(
        max_length=10,
        choices=RESPONSE_TYPE_CHOICES,
        default=RESPONSE_TYPE_TEXT,
    )
    ai_personalized = models.BooleanField(
        default=False,
        help_text="If True, GPT generates the follow-up based on conversation history",
    )
    file_attachment = models.FileField(
        upload_to="follow_up_media/%Y/%m/",
        blank=True,
        null=True,
        max_length=500,
        help_text="Pre-defined media for AUDIO/IMAGE/VIDEO",
    )
    caption = models.TextField(
        blank=True,
        help_text="Default message text or caption for media",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Follow-up node config"
        verbose_name_plural = "Follow-up node configs"

    def __str__(self):
        return f"Follow-up (node {self.node_id}, {self.delay_hours}h, {self.response_type})"


class GoogleSheetsConfig(models.Model):
    """
    Global Google Sheets connection settings per user (merchant).
    Service Account JSON is stored encrypted. column_mapping maps sheet columns (A, B, C...)
    to conversation/order variable names (e.g. customer_name, phone, city).
    """
    user = models.OneToOneField(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="google_sheets_config",
    )
    spreadsheet_id = models.CharField(
        max_length=128,
        help_text="Spreadsheet ID from the Google Sheets URL",
    )
    sheet_name = models.CharField(max_length=128, default="Orders")
    # Encrypted JSON string of the Service Account credentials (encrypt before save, decrypt when using)
    service_account_json_encrypted = models.TextField(blank=True, null=True)
    # Maps column letter -> variable key, e.g. {"A": "customer_name", "B": "phone", "C": "city"}
    column_mapping = models.JSONField(
        default=dict,
        blank=True,
        help_text='{"A": "customer_name", "B": "phone", "C": "city", ...}',
    )
    # Drag-and-drop field mapping: list of {"field": "customer_name", "header": "Customer Name"}. Order = column order.
    sheets_mapping = models.JSONField(
        default=list,
        blank=True,
        help_text='[{"field": "customer_name", "header": "Customer Name"}, ...]',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Google Sheets config"
        verbose_name_plural = "Google Sheets configs"

    def __str__(self):
        return f"Google Sheets config for user {self.user_id} ({self.sheet_name})"


class GoogleSheetsNode(models.Model):
    """
    Flow node config for Google Sheets export. When the flow reaches this node,
    order/conversation data is exported to the sheet (using the user's GoogleSheetsConfig).
    One-to-one with Node (node_type='google-sheets').
    """
    node = models.OneToOneField(
        Node,
        on_delete=models.CASCADE,
        related_name="google_sheets_config",
    )
    # Optional override: use this config instead of user's global GoogleSheetsConfig (future use)
    config = models.ForeignKey(
        GoogleSheetsConfig,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="nodes",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Google Sheets node config"
        verbose_name_plural = "Google Sheets node configs"

    def __str__(self):
        return f"Google Sheets node (node {self.node_id})"


class FollowUpTask(models.Model):
    """
    Scheduled follow-up to be sent to a customer. Cancelled when they reply or place an order.
    """
    STATUS_PENDING = "PENDING"
    STATUS_SENT = "SENT"
    STATUS_CANCELLED = "CANCELLED"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_SENT, "Sent"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    channel = models.ForeignKey(
        WhatsAppChannel,
        on_delete=models.CASCADE,
        related_name="follow_up_tasks",
    )
    node = models.ForeignKey(
        Node,
        on_delete=models.CASCADE,
        related_name="follow_up_tasks",
        help_text="The follow-up node that created this task",
    )
    customer_phone = models.CharField(max_length=32, db_index=True)
    scheduled_at = models.DateTimeField(db_index=True)
    is_cancelled = models.BooleanField(default=False)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["scheduled_at"]
        indexes = [
            models.Index(fields=["channel", "customer_phone", "status"]),
            models.Index(fields=["status", "scheduled_at"]),
        ]
        verbose_name = "Follow-up task"
        verbose_name_plural = "Follow-up tasks"

    def __str__(self):
        return f"FollowUp {self.customer_phone} @ {self.scheduled_at} ({self.status})"


class FollowUpSentLog(models.Model):
    """Log every sent follow-up for the Analytics dashboard."""
    channel = models.ForeignKey(
        WhatsAppChannel,
        on_delete=models.CASCADE,
        related_name="follow_up_sent_logs",
    )
    customer_phone = models.CharField(max_length=32)
    node_id = models.PositiveIntegerField(null=True, blank=True, help_text="Follow-up Node id")
    response_type = models.CharField(max_length=10, blank=True)
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-sent_at"]
        indexes = [models.Index(fields=["channel", "sent_at"])]
        verbose_name = "Follow-up sent log"
        verbose_name_plural = "Follow-up sent logs"

    def __str__(self):
        return f"Follow-up to {self.customer_phone} at {self.sent_at}"


class Tags(models.Model):
    name = models.CharField(max_length=50, verbose_name="اسم الوسم")
    
    # ربط التاج بالمدير (صاحب القناة) لكي تكون التاجات خاصة بكل فريق عمل
    admin = models.ForeignKey(
        CustomUser, 
        on_delete=models.CASCADE, 
        related_name='my_tags'
    )
    
    # (اختياري) لون التاج للتميز في الواجهة
    color = models.CharField(max_length=7, default="#6366f1") # Hex Color
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # منع تكرار نفس اسم التاج لنفس المدير
        unique_together = ('name', 'admin')

    def __str__(self):
        return self.name





class Contact(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    phone = models.CharField(max_length=30)
    name = models.CharField(max_length=255, blank=True, null=True)
    channel = models.ForeignKey(WhatsAppChannel, on_delete=models.CASCADE)
    tags = models.ManyToManyField(Tags, blank=True, related_name='contacts')
    class PipelineStage(models.TextChoices):
        NEW = 'new', '🆕 New Chat'
        INTERESTED = 'interested', '🔥 Interested'
        FOLLOW_UP = 'follow_up', '📅 Follow Up'
        CLOSED = 'closed', '✅ Closed / Won'
        REJECTED = 'rejected', '❌ Not Interested'

  
    pipeline_stage = models.CharField(
        max_length=20,
        choices=PipelineStage.choices,
        default=PipelineStage.NEW,
        verbose_name="مرحلة العميل"
    )
    flow_started = models.BooleanField(default=False)
    last_interaction = models.DateTimeField(auto_now=True)
    last_seen = models.DateField(max_length=255, blank=True, null=True)
        # تصحيح last_seen
    last_seen = models.DateTimeField(blank=True, null=True)
    assigned_agent = models.ForeignKey(
        CustomUser, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='assigned_chats',
        verbose_name='الموظف المسؤول'
    )

    # صورة العميل
    profile_picture = models.ImageField(
        upload_to='contacts/', 
        blank=True,
        null=True
    )

    def __str__(self):
        return self.phone
    created_at = models.DateTimeField(auto_now_add=True , null=True , blank=True)


class BlockedCustomer(models.Model):
    """Phone numbers blocked from inbound WhatsApp processing on a specific channel."""
    channel = models.ForeignKey(
        WhatsAppChannel,
        on_delete=models.CASCADE,
        related_name="blocked_customers",
    )
    phone = models.CharField(max_length=30, db_index=True)
    blocked_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="blocked_customers",
    )
    reason = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Blocked customer"
        verbose_name_plural = "Blocked customers"
        unique_together = [("channel", "phone")]
        indexes = [
            models.Index(fields=["channel", "phone"], name="blocked_cust_ch_phone_idx"),
        ]

    def __str__(self):
        return f"{self.phone} @ {self.channel_id}"























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








# quik replay 
# models.py
class CannedResponse(models.Model):
    # المالك (مهم جداً في نظام SaaS)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='canned_responses')
    channel = models.ForeignKey(WhatsAppChannel, on_delete=models.CASCADE, related_name='canned_responses')
    shortcut = models.CharField(max_length=50, help_text="الكلمة التي ستظهر في القائمة بعد /")
    message = models.TextField(blank=True, null=True)
    type = models.CharField(max_length=20, blank = True, null=True) 
    
    # ملف مرفق (فيديو/صورة) جاهز مسبقاً
    attachment = models.FileField(upload_to='canned_files/', blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    usage = models.PositiveIntegerField(default=0)

    def __str__(self):
        return self.shortcut


class AIUsageLog(models.Model):
    """Track API usage (ElevenLabs, Whisper) for analytics and overage prevention."""
    channel = models.ForeignKey(
        WhatsAppChannel,
        on_delete=models.CASCADE,
        related_name="ai_usage_logs",
    )
    date = models.DateField(db_index=True)
    provider = models.CharField(max_length=32)  # e.g. elevenlabs, whisper
    characters_used = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-created_at"]
        indexes = [models.Index(fields=["channel", "date"])]
        verbose_name = "AI usage log"
        verbose_name_plural = "AI usage logs"

    def __str__(self):
        return f"{self.channel_id} {self.date} {self.provider}: {self.characters_used}"


class StorePaymentMethod(models.Model):
    """Encrypted store-level payment accounts used by the AI for digital product checkout."""

    PROVIDER_CHOICES = [
        ('cih_bank',      'CIH Bank'),
        ('attijariwafa',  'Attijariwafa Bank'),
        ('boa',           'Bank of Africa'),
        ('paypal',        'PayPal'),
        ('wise',          'Wise'),
    ]

    # Providers that require an account holder name and a RIB identifier.
    # All other providers (PayPal, Wise) use an email address instead.
    BANK_PROVIDERS = {'cih_bank', 'attijariwafa', 'boa'}

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='payment_methods',
    )
    provider_name = models.CharField(max_length=50, choices=PROVIDER_CHOICES)
    display_name = models.CharField(
        max_length=100,
        blank=True,
        help_text='Custom label shown to customers. Leave blank to use the provider name.',
    )
    # For bank transfers: the account owner's full name printed on the RIB.
    account_holder_name = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text='Full name of the account holder (bank transfers only).',
    )
    # Holds either the RIB (bank) or the email address (PayPal / Wise).
    # Always stored Fernet-encrypted at rest.
    account_details_encrypted = models.TextField(
        help_text='RIB (24 digits) or email — stored Fernet-encrypted at rest.',
    )
    instructions = models.TextField(
        blank=True,
        help_text='e.g., "Include order number in transfer note."',
    )
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['provider_name', 'id']
        verbose_name = 'Store Payment Method'
        verbose_name_plural = 'Store Payment Methods'

    def __str__(self):
        return f"{self.label} ({self.owner_id})"

    # ------------------------------------------------------------------ #
    #  Helpers                                                             #
    # ------------------------------------------------------------------ #

    @property
    def is_bank(self) -> bool:
        return self.provider_name in self.BANK_PROVIDERS

    def set_account_details(self, raw_value: str) -> None:
        from discount.crypto import encrypt_token
        self.account_details_encrypted = encrypt_token(raw_value)

    def get_account_details(self) -> str:
        from discount.crypto import decrypt_token
        if not self.account_details_encrypted:
            return ''
        try:
            return decrypt_token(self.account_details_encrypted)
        except Exception:
            return ''

    def get_masked_details(self) -> str:
        """
        Show only the last 4 characters.
        For emails the domain part is preserved: user@domain.com → ****@domain.com.
        """
        details = self.get_account_details()
        if not details:
            return '****'
        if '@' in details:
            local, domain = details.rsplit('@', 1)
            masked_local = '*' * max(len(local), 1)
            return f"{masked_local}@{domain}"
        if len(details) <= 4:
            return details
        return ('*' * (len(details) - 4)) + details[-4:]

    def format_for_ai(self) -> str:
        """Return a single human-readable line for injection into the AI system prompt."""
        identifier = self.get_account_details()
        if self.is_bank:
            name_part = f"{self.account_holder_name} — " if self.account_holder_name else ""
            return f"{self.label}: {name_part}RIB {identifier}"
        return f"{self.label} Email: {identifier}"

    @property
    def label(self) -> str:
        return self.display_name.strip() or self.get_provider_name_display()


# ══════════════════════════════════════════════════════════════════════════
# Dynamic Digital Stock
# ══════════════════════════════════════════════════════════════════════════
#
# One row = one ready-to-deliver digital asset (license key, key code, or
# `email:password` combo) for a `Products` instance. Sellers bulk-paste
# their inventory in the product form; on each digital order approval the
# fulfillment endpoint locks **one** unsold row with `select_for_update`,
# marks it `is_sold=True`, links it to the order, decrypts the content
# server-side, and ships it via the spoiler pipeline.
#
# Race-safety contract:
#   - `asset_content` is Fernet-encrypted at rest (helpers below mirror
#     `StorePaymentMethod.account_details_encrypted` / `Message.encrypted_asset`).
#   - The unique compound index `(product, is_sold, id)` keeps the FIFO
#     consume-query (`order_by('id').first()` on unsold) index-only.
#   - The fulfillment view MUST wrap the lookup + `save()` in
#     `transaction.atomic()` so the `SELECT … FOR UPDATE` row lock is
#     released only after commit — two parallel approvals can never grab
#     the same row.
class DigitalAssetStock(models.Model):
    """One pre-loaded digital asset row consumed FIFO on each sale."""

    product = models.ForeignKey(
        'Products',
        on_delete=models.CASCADE,
        related_name='digital_stock',
        help_text='The digital product this asset will be delivered for.',
    )
    asset_content = models.TextField(
        # NOTE: `CharField(500)` would truncate Fernet ciphertext for any
        # real-world payload. We use TextField (no length cap) like the
        # rest of the encrypted-fields family in this codebase.
        blank=True,
        null=True,
        help_text='Fernet-encrypted credential payload (single key OR '
                  '"email:password" depending on product.stock_format).',
    )
    is_sold = models.BooleanField(
        default=False,
        db_index=True,
        help_text='True once this row has been consumed and shipped to a customer.',
    )
    order = models.ForeignKey(
        'SimpleOrder',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='digital_stock_rows',
        help_text='The order that consumed this row (null while is_sold=False).',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    sold_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Timestamp when this row was marked is_sold=True. '
                  'Useful for analytics and race-condition forensics.',
    )

    class Meta:
        ordering = ['id']
        indexes = [
            # FIFO consume query — keeps `select_for_update().filter(
            # product=p, is_sold=False).order_by('id').first()` index-only.
            models.Index(
                fields=['product', 'is_sold', 'id'],
                name='digstock_consume_idx',
            ),
        ]

    def __str__(self):
        state = 'sold' if self.is_sold else 'available'
        return f'DigitalAssetStock<{self.product_id} #{self.pk} {state}>'

    # ── Encrypted-asset helpers (same Fernet pattern as the rest of the app)
    def set_asset_content(self, raw_value):
        """Encrypt `raw_value` at rest. Empty input clears the field."""
        if not raw_value:
            self.asset_content = None
            return
        from discount.crypto import encrypt_token
        self.asset_content = encrypt_token(str(raw_value))

    def get_asset_content(self) -> str:
        """
        Return the plaintext credential (or '' on missing / corrupted
        ciphertext). MUST only be called inside the owner-gated
        fulfillment flow — never in a list endpoint.
        """
        if not self.asset_content:
            return ''
        try:
            from discount.crypto import decrypt_token
            return decrypt_token(self.asset_content)
        except Exception:
            return ''