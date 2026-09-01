"""
مثال عملي: كيفية دمج نظام الذاكرة في process_messages.py

هذا الملف يشرح التعديلات المطلوبة على AI Agent
"""

# ==========================================
#  في process_messages.py
# ==========================================

# 1️⃣ الإضافات في الـ imports
from discount.services.context_integration import (
    enhance_ai_prompt_with_context,
    update_state_from_customer_message,
    process_ai_response_and_update_state,
    link_product_to_conversation,
    get_order_data_from_state,
    build_context_aware_conversation,
)

# ==========================================
#  2️⃣ في دالة run_ai_agent_node()
# ==========================================

def run_ai_agent_node_ENHANCED(channel, sender, name, body, session, node):
    """
    ✅ نسخة محسّنة من run_ai_agent_node مع Context Awareness
    """
    
    # الكود الأصلي...
    
    # ✅ خطوة 1: تحديث الحالة من رسالة العميل
    state = update_state_from_customer_message(
        message=body,
        channel_id=channel.id,
        customer_phone=sender
    )
    
    logger.info(f"📊 Conversation state: {state}")
    
    # ✅ خطوة 2: تحميل الرسائل السابقة
    recent_messages = Message.objects.filter(
        channel=channel,
        sender=sender
    ).order_by('-id')[:15]
    recent_messages = list(recent_messages)
    recent_messages.reverse()
    
    # ✅ خطوة 3: بناء محادثة مع السياق
    conversation = build_context_aware_conversation(
        channel_id=channel.id,
        customer_phone=sender,
        recent_messages=recent_messages
    )
    
    # ✅ خطوة 4: تحسين الـ system prompt
    base_system_prompt = node.ai_model_config.get('system_prompt', DEFAULT_SYSTEM_PROMPT)
    
    enhanced_prompt = enhance_ai_prompt_with_context(
        channel_id=channel.id,
        customer_phone=sender,
        base_prompt=base_system_prompt
    )
    
    # ✅ خطوة 5: استدعاء AI مع الـ prompt المحسّن
    try:
        from ai_assistant.services import generate_reply_with_tools
        
        result = generate_reply_with_tools(
            conversation=conversation,
            custom_instruction=enhanced_prompt,
            channel=channel,
            sender=sender,
            session=session
        )
        
        reply_text = result.get('reply_text', '')
        tool_calls = result.get('tool_calls', [])
        
        # ✅ خطوة 6: معالجة الرد وتحديث الحالة
        reply_text = process_ai_response_and_update_state(
            response_text=reply_text,
            channel_id=channel.id,
            customer_phone=sender,
            customer_message=body
        )
        
        # ✅ خطوة 7: معالجة tool calls (إذا موجودة)
        if tool_calls:
            # معالجة الـ tools...
            pass
        
        # إرسال الرد
        if reply_text:
            send_whatsapp_message(channel, sender, reply_text)
            
            # حفظ في قاعدة البيانات
            Message.objects.create(
                channel=channel,
                sender=sender,
                body=reply_text,
                is_from_me=True,
                timestamp=timezone.now()
            )
        
    except Exception as e:
        logger.exception(f"AI Agent error: {e}")
        # Fallback...


# ==========================================
#  3️⃣ في Flow Builder: ربط المنتج
# ==========================================

def handle_product_selection(channel_id, customer_phone, product_id):
    """
    ✅ عندما العميل يختار منتج من Flow Builder
    """
    from discount.services.context_integration import link_product_to_conversation
    
    success = link_product_to_conversation(
        product_id=product_id,
        channel_id=channel_id,
        customer_phone=customer_phone
    )
    
    if success:
        # أرسل رسالة تأكيد
        send_whatsapp_message(
            channel_id=channel_id,
            phone=customer_phone,
            message="✅ تم اختيار المنتج! الآن فقط نحتاج بعض التفاصيل للتوصيل."
        )


# ==========================================
#  4️⃣ تحسين submit_customer_order tool
# ==========================================

# في ai_assistant/services.py - tools definition

TOOLS_WITH_CONTEXT = [
    {
        "type": "function",
        "function": {
            "name": "submit_customer_order",
            "description": """
            ✅ UPDATED: تسجيل طلب العميل في النظام.
            
            ⚠️ قبل استدعاء هذا الـ tool:
            1. تحقق من المعلومات الموجودة في السياق (CONTEXT أعلاه)
            2. لا تطلب معلومات موجودة بالفعل
            3. اطلب فقط ما هو ناقص
            
            المطلوب:
            - customer_name (الاسم الكامل)
            - customer_city (المدينة)
            - customer_address (العنوان الكامل)
            - product_name (اسم المنتج - عادة موجود في السياق!)
            - price (السعر - عادة موجود في السياق!)
            - quantity (الكمية - افتراضياً 1)
            """,
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_name": {
                        "type": "string",
                        "description": "الاسم الكامل للعميل (إذا ناقص فقط)"
                    },
                    "customer_city": {
                        "type": "string",
                        "description": "مدينة التوصيل"
                    },
                    "customer_address": {
                        "type": "string",
                        "description": "العنوان الكامل (حي، شارع، رقم)"
                    },
                    "product_name": {
                        "type": "string",
                        "description": "اسم المنتج (عادة موجود في السياق)"
                    },
                    "price": {
                        "type": "number",
                        "description": "سعر الطلب (عادة موجود في السياق)"
                    },
                    "quantity": {
                        "type": "integer",
                        "description": "الكمية (افتراضياً 1)"
                    }
                },
                "required": ["customer_name", "customer_city", "customer_address"]
            }
        }
    }
]


# ==========================================
#  5️⃣ معالجة tool call مع السياق
# ==========================================

def execute_submit_order_with_context(channel, sender, tool_args):
    """
    ✅ تنفيذ submit_order مع استكمال من السياق
    """
    from discount.services.context_integration import (
        get_conversation_state,
        get_order_data_from_state
    )
    
    state = get_conversation_state(channel.id, sender)
    
    # ✅ استكمال البيانات الناقصة من السياق
    # إذا المنتج موجود في السياق، استخدمه
    product = state.get_product()
    if product and not tool_args.get('product_name'):
        tool_args['product_name'] = product['name']
        tool_args['price'] = product['price']
        logger.info(f"✅ Auto-filled product from context: {product['name']}")
    
    # إذا الاسم موجود في السياق، استخدمه
    if state._state.get('customer_name') and not tool_args.get('customer_name'):
        tool_args['customer_name'] = state._state['customer_name']
        logger.info(f"✅ Auto-filled name from context")
    
    # إذا المدينة موجودة في السياق، استخدمها
    if state._state.get('customer_city') and not tool_args.get('customer_city'):
        tool_args['customer_city'] = state._state['customer_city']
        logger.info(f"✅ Auto-filled city from context")
    
    # الآن نفذ الطلب
    from discount.orders_ai import handle_submit_order_tool
    
    result = handle_submit_order_tool(
        channel_id=channel.id,
        customer_phone=sender,
        **tool_args
    )
    
    return result


# ==========================================
#  6️⃣ API Endpoint للـ debugging
# ==========================================

# في discount/views.py أو core_admin/views.py

from django.http import JsonResponse
from django.contrib.admin.views.decorators import staff_member_required
from discount.services.context_integration import get_conversation_state_debug

@staff_member_required
def debug_conversation_state(request, channel_id, customer_phone):
    """
    ✅ API للمطورين: عرض حالة المحادثة
    
    استخدام:
    GET /debug/conversation-state/{channel_id}/{customer_phone}/
    """
    try:
        state_data = get_conversation_state_debug(channel_id, customer_phone)
        return JsonResponse({
            'success': True,
            'state': state_data
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# ==========================================
#  7️⃣ إضافة في templates (عرض السياق للوكلاء)
# ==========================================

"""
في templates/whatssap/chat.html:

<div class="conversation-context-panel">
    <h3>📊 Context</h3>
    <div id="context-display">
        <!-- يتم تحديثه بـ HTMX -->
    </div>
</div>

<script>
// تحديث السياق كل 5 ثوان
setInterval(() => {
    fetch(`/api/conversation-context/${channelId}/${customerPhone}/`)
        .then(r => r.json())
        .then(data => {
            const display = document.getElementById('context-display');
            
            if (data.product) {
                display.innerHTML = `
                    <div class="context-item">
                        📦 المنتج: <strong>${data.product.name}</strong>
                        ${data.product.price ? `(${data.product.price} درهم)` : ''}
                    </div>
                `;
            }
            
            if (data.customer_data.name) {
                display.innerHTML += `
                    <div class="context-item">
                        👤 الاسم: <strong>${data.customer_data.name}</strong>
                    </div>
                `;
            }
            
            if (data.missing_fields.length > 0) {
                display.innerHTML += `
                    <div class="context-item warning">
                        ⚠️ ناقص: ${data.missing_fields.join(', ')}
                    </div>
                `;
            }
            
            if (data.ready_to_order) {
                display.innerHTML += `
                    <div class="context-item success">
                        ✅ جاهز للطلب!
                    </div>
                `;
            }
        });
}, 5000);
</script>
"""


# ==========================================
#  8️⃣ Management Command للـ testing
# ==========================================

"""
في discount/management/commands/test_context.py:

from django.core.management.base import BaseCommand
from discount.services.context_integration import (
    get_conversation_state,
    link_product_to_conversation,
    get_conversation_state_debug
)

class Command(BaseCommand):
    help = 'Test conversation context system'
    
    def add_arguments(self, parser):
        parser.add_argument('channel_id', type=int)
        parser.add_argument('phone', type=str)
    
    def handle(self, *args, **options):
        channel_id = options['channel_id']
        phone = options['phone']
        
        # اختبار
        self.stdout.write("Testing context system...")
        
        state = get_conversation_state(channel_id, phone)
        
        # ربط منتج تجريبي
        state.set_product(1, "منتج تجريبي", 299.0, "TEST-SKU")
        state.set_customer_name("أحمد")
        state.set_customer_city("الدار البيضاء")
        
        # عرض الحالة
        debug_data = get_conversation_state_debug(channel_id, phone)
        
        self.stdout.write(self.style.SUCCESS(
            f"✅ Context test passed!\n{debug_data}"
        ))

استخدام:
python manage.py test_context 1 212600000000
"""
