"""
Conversation State Manager - نظام تتبع حالة المحادثة
يحل مشكلة: النموذج ينسى السياق (المنتج، السعر، إلخ)
"""
import json
import logging
from typing import Dict, Any, Optional
from django.core.cache import cache
from django.utils import timezone
from datetime import timedelta

logger = logging.getLogger(__name__)


class ConversationState:
    """
    حالة المحادثة - يخزن كل المعلومات المهمة
    """
    
    def __init__(self, channel_id: int, customer_phone: str):
        self.channel_id = channel_id
        self.customer_phone = customer_phone
        self.cache_key = f"conv_state:{channel_id}:{customer_phone}"
        
        # تحميل الحالة من الذاكرة
        self._state = self._load_state()
    
    def _load_state(self) -> Dict[str, Any]:
        """تحميل الحالة من Redis/Cache"""
        cached = cache.get(self.cache_key)
        if cached:
            return json.loads(cached)
        
        # حالة جديدة
        return {
            'product': None,           # المنتج المختار
            'product_name': None,      # اسم المنتج
            'product_price': None,     # السعر
            'product_sku': None,       # SKU
            'quantity': 1,             # الكمية
            'customer_name': None,     # اسم العميل
            'customer_city': None,     # المدينة
            'customer_address': None,  # العنوان
            'phone_confirmed': False,  # رقم الهاتف مؤكد
            'stage': 'initial',        # مرحلة المحادثة
            'intent': None,            # النية الحالية
            'last_updated': None,
            'conversation_started': timezone.now().isoformat(),
            'notes': [],               # ملاحظات مهمة
        }
    
    def _save_state(self):
        """حفظ الحالة في Redis/Cache"""
        self._state['last_updated'] = timezone.now().isoformat()
        cache.set(
            self.cache_key,
            json.dumps(self._state, ensure_ascii=False),
            timeout=86400 * 3  # 3 أيام
        )
    
    # ==========================================
    #  Product Management
    # ==========================================
    
    def set_product(self, product_id: int, product_name: str, 
                    price: float = None, sku: str = None):
        """
        ✅ حفظ المنتج المختار (لن ينساه النموذج أبداً!)
        """
        self._state['product'] = product_id
        self._state['product_name'] = product_name
        self._state['product_price'] = price
        self._state['product_sku'] = sku
        self._state['stage'] = 'product_selected'
        
        # أضف ملاحظة
        self._state['notes'].append(
            f"المنتج المختار: {product_name} (#{product_id})"
        )
        
        self._save_state()
        logger.info(f"✅ Product saved to state: {product_name} (#{product_id})")
    
    def get_product(self) -> Optional[Dict[str, Any]]:
        """استرجاع المنتج المحفوظ"""
        if not self._state.get('product'):
            return None
        
        return {
            'id': self._state['product'],
            'name': self._state['product_name'],
            'price': self._state['product_price'],
            'sku': self._state['product_sku'],
        }
    
    def clear_product(self):
        """مسح المنتج (إذا العميل بدل رأيه)"""
        self._state['product'] = None
        self._state['product_name'] = None
        self._state['product_price'] = None
        self._state['product_sku'] = None
        self._save_state()
    
    # ==========================================
    #  Customer Data Management
    # ==========================================
    
    def set_customer_name(self, name: str):
        """حفظ اسم العميل"""
        self._state['customer_name'] = name
        self._state['notes'].append(f"الاسم: {name}")
        self._save_state()
    
    def set_customer_city(self, city: str):
        """حفظ مدينة العميل"""
        self._state['customer_city'] = city
        self._state['notes'].append(f"المدينة: {city}")
        self._save_state()
    
    def set_customer_address(self, address: str):
        """حفظ عنوان العميل"""
        self._state['customer_address'] = address
        self._save_state()
    
    def confirm_phone(self):
        """تأكيد رقم الهاتف"""
        self._state['phone_confirmed'] = True
        self._save_state()
    
    # ==========================================
    #  Conversation Stage Management
    # ==========================================
    
    def set_stage(self, stage: str):
        """
        تحديث مرحلة المحادثة:
        - initial: بداية
        - browsing: يتصفح المنتجات
        - product_selected: اختار منتج
        - collecting_info: يجمع بيانات العميل
        - confirming: تأكيد الطلب
        - completed: اكتمل
        """
        self._state['stage'] = stage
        self._save_state()
    
    def get_stage(self) -> str:
        """الحصول على المرحلة الحالية"""
        return self._state.get('stage', 'initial')
    
    def set_intent(self, intent: str):
        """حفظ النية الحالية (price_inquiry, order_placement, etc.)"""
        self._state['intent'] = intent
        self._save_state()
    
    # ==========================================
    #  Context Building for AI
    # ==========================================
    
    def build_context_prompt(self) -> str:
        """
        ✅ بناء prompt للـ AI يحتوي على كل السياق المهم
        هذا يمنع النموذج من نسيان المعلومات!
        """
        product = self.get_product()
        
        context_parts = ["=== معلومات المحادثة الحالية ===\n"]
        
        # المنتج
        if product:
            context_parts.append(
                f"📦 المنتج المختار: {product['name']} (ID: {product['id']})\n"
            )
            if product['price']:
                context_parts.append(f"💰 السعر: {product['price']} درهم\n")
            context_parts.append(
                "⚠️ لا تسأل العميل عن المنتج مرة أخرى - هو اختاره بالفعل!\n"
            )
        else:
            context_parts.append("📦 المنتج: لم يختر بعد\n")
        
        # بيانات العميل
        if self._state.get('customer_name'):
            context_parts.append(f"👤 الاسم: {self._state['customer_name']}\n")
        
        if self._state.get('customer_city'):
            context_parts.append(f"🏙️ المدينة: {self._state['customer_city']}\n")
        
        if self._state.get('customer_address'):
            context_parts.append(f"📍 العنوان: {self._state['customer_address']}\n")
        
        # المرحلة الحالية
        stage_names = {
            'initial': 'بداية المحادثة',
            'browsing': 'يتصفح المنتجات',
            'product_selected': 'اختار منتج',
            'collecting_info': 'جمع بيانات العميل',
            'confirming': 'تأكيد الطلب',
            'completed': 'اكتمل الطلب'
        }
        stage = self.get_stage()
        context_parts.append(f"📊 المرحلة: {stage_names.get(stage, stage)}\n")
        
        # ما الذي يجب فعله الآن؟
        if product and not self._state.get('customer_name'):
            context_parts.append("\n✅ الخطوة التالية: اسأل عن اسم العميل\n")
        elif product and self._state.get('customer_name') and not self._state.get('customer_city'):
            context_parts.append("\n✅ الخطوة التالية: اسأل عن المدينة\n")
        elif product and self._state.get('customer_city') and not self._state.get('customer_address'):
            context_parts.append("\n✅ الخطوة التالية: اسأل عن العنوان الكامل\n")
        
        # ملاحظات إضافية
        if self._state.get('notes'):
            context_parts.append("\n📝 ملاحظات المحادثة:\n")
            for note in self._state['notes'][-5:]:  # آخر 5 ملاحظات
                context_parts.append(f"  • {note}\n")
        
        context_parts.append("\n" + "=" * 50 + "\n")
        
        return "".join(context_parts)
    
    def get_missing_fields(self) -> list[str]:
        """
        ✅ قائمة الحقول الناقصة لإكمال الطلب
        """
        missing = []
        
        if not self._state.get('product'):
            missing.append('المنتج')
        if not self._state.get('customer_name'):
            missing.append('الاسم')
        if not self._state.get('customer_city'):
            missing.append('المدينة')
        if not self._state.get('customer_address'):
            missing.append('العنوان')
        
        return missing
    
    def is_ready_to_order(self) -> bool:
        """
        ✅ هل كل المعلومات جاهزة لتسجيل الطلب؟
        """
        return len(self.get_missing_fields()) == 0
    
    def to_order_dict(self) -> Dict[str, Any]:
        """
        ✅ تحويل الحالة إلى بيانات طلب جاهزة
        """
        return {
            'product_id': self._state.get('product'),
            'product_name': self._state.get('product_name'),
            'price': self._state.get('product_price'),
            'quantity': self._state.get('quantity', 1),
            'customer_name': self._state.get('customer_name'),
            'customer_city': self._state.get('customer_city'),
            'customer_address': self._state.get('customer_address'),
            'customer_phone': self.customer_phone,
        }
    
    def add_note(self, note: str):
        """إضافة ملاحظة للمحادثة"""
        if 'notes' not in self._state:
            self._state['notes'] = []
        self._state['notes'].append(f"{timezone.now().strftime('%H:%M')}: {note}")
        self._save_state()
    
    def reset(self):
        """إعادة تعيين الحالة (محادثة جديدة)"""
        cache.delete(self.cache_key)
        self._state = self._load_state()
    
    def __str__(self):
        """عرض ملخص الحالة"""
        product = self.get_product()
        return (
            f"ConversationState(product={product['name'] if product else 'None'}, "
            f"stage={self.get_stage()}, "
            f"ready={self.is_ready_to_order()})"
        )


# ==========================================
#  Helper Functions
# ==========================================

def get_conversation_state(channel_id: int, customer_phone: str) -> ConversationState:
    """
    ✅ الحصول على حالة المحادثة (Helper function)
    """
    return ConversationState(channel_id, customer_phone)


def extract_and_save_entities(message: str, state: ConversationState):
    """
    ✅ استخراج الكيانات (المنتج، الاسم، المدينة) من الرسالة تلقائياً
    """
    import re
    
    message_lower = message.lower()
    
    # استخراج اسم محتمل (بعد "اسمي" أو "أنا")
    name_patterns = [
        r'اسمي\s+(\w+)',
        r'أنا\s+(\w+)',
        r'نبغي\s+(\w+)',  # أحياناً الاسم بعد "نبغي"
    ]
    for pattern in name_patterns:
        match = re.search(pattern, message_lower)
        if match and not state._state.get('customer_name'):
            potential_name = match.group(1)
            # تحقق: ليس كلمة عامة
            if potential_name not in ['واحد', 'هاد', 'المنتج']:
                state.set_customer_name(potential_name.title())
                logger.info(f"✅ Extracted name: {potential_name}")
    
    # استخراج مدينة محتملة
    moroccan_cities = [
        'الدار البيضاء', 'كازا', 'casablanca', 'الرباط', 'rabat',
        'فاس', 'fes', 'مراكش', 'marrakech', 'طنجة', 'tanger',
        'أغادير', 'agadir', 'مكناس', 'meknes', 'وجدة', 'oujda',
        'القنيطرة', 'kenitra', 'تطوان', 'tetouan', 'الجديدة'
    ]
    for city in moroccan_cities:
        if city in message_lower and not state._state.get('customer_city'):
            state.set_customer_city(city.title())
            logger.info(f"✅ Extracted city: {city}")
            break
