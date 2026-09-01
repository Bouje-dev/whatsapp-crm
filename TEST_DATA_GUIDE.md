# 🧪 Test Data Guide - دليل البيانات التجريبية

## ✅ Test Data Created Successfully

البيانات التجريبية تم إضافتها بنجاح إلى Redis!

### 📋 Test Customer Information

- **Phone Number:** `+212612638500`
- **Username:** `bojamaa`
- **Channel ID:** `1`

### 📦 Test Conversation Data

**Product Information:**
- Product: iPhone 15 Pro Max - 256GB
- Product ID: 101
- Price: 15,999.00 DH
- SKU: IPH15PM-256-BLU
- Quantity: 1

**Customer Information:**
- Name: Bojamaa
- City: Casablanca
- Address: 123 Rue Mohammed V, Quartier Maarif
- Phone Confirmed: ✅ Yes

**Conversation Stage:**
- Current Stage: `collecting_info` (جمع بيانات العميل)
- Intent: `order_placement`

**Conversation Notes:**
1. Customer interested in blue color
2. Asked about delivery time
3. Prefers cash on delivery
4. Available for delivery on weekends

**Status:**
- ✅ Ready to Order: Yes
- ✅ Missing Fields: None
- ✅ All required information collected

---

## 🎯 How to Test the Context Panel

### Step 1: Open the Chat
1. في لوحة التحكم، ابحث عن المحادثة مع الرقم: `+212612638500`
2. أو المستخدم: `bojamaa`
3. افتح المحادثة

### Step 2: View Context Panel
1. اضغط على زر **"AI Context"** في الأعلى
2. يجب أن ترى:
   - البطاقة الجانبية تختفي (quick-body)
   - Context Panel يظهر مكانها
   - كل المعلومات المحفوظة تظهر بوضوح

### Expected Display:

```
🏷️ CONVERSATION STAGE
✅ Stage: Collecting Info
   Conversation Started: [timestamp]

📦 SELECTED PRODUCT
✅ Product: iPhone 15 Pro Max - 256GB
💰 Price: 15,999.00 DH
🔖 SKU: IPH15PM-256-BLU
📊 Quantity: 1

👤 CUSTOMER INFORMATION
✅ Name: Bojamaa
🏙️ City: Casablanca
📍 Address: 123 Rue Mohammed V, Quartier Maarif
📱 Phone: +212612638500 (Confirmed)

📝 CONVERSATION NOTES
• Customer interested in blue color
• Asked about delivery time
• Prefers cash on delivery
• Available for delivery on weekends

✅ ORDER STATUS
Ready to Submit: All information collected
```

---

## 🔄 Add More Test Data

لإضافة بيانات تجريبية لعميل آخر:

```bash
source venv11/bin/activate
python manage.py shell << 'EOF'
from discount.services.conversation_state import ConversationState

PHONE = "+212600000000"  # رقم جديد
CHANNEL_ID = 1

state = ConversationState(channel_id=CHANNEL_ID, customer_phone=PHONE)
state.reset()

state.set_product(
    product_id=102,
    product_name="Samsung Galaxy S24 Ultra",
    price=12999.00,
    sku="SAM-S24U-512"
)

state.set_customer_name("Ahmed")
state.set_customer_city("Rabat")
state.set_customer_address("456 Avenue Hassan II")
state.confirm_phone()
state.set_stage("product_selected")

print(f"✅ Test data created for {PHONE}")
EOF
```

---

## 🗑️ Clear Test Data

لمسح البيانات التجريبية:

```bash
source venv11/bin/activate
python manage.py shell << 'EOF'
from discount.services.conversation_state import ConversationState

PHONE = "+212612638500"
CHANNEL_ID = 1

state = ConversationState(channel_id=CHANNEL_ID, customer_phone=PHONE)
state.reset()

print("✅ Test data cleared")
EOF
```

---

## 🎨 Visual Test Checklist

عند فتح Context Panel، تأكد من:

- ✅ الألوان Dark Theme متطابقة مع المشروع
- ✅ quick-body يختفي عند فتح Context Panel
- ✅ quick-body يظهر عند إغلاق Context Panel
- ✅ الزر يغير اللون (بنفسجي → أخضر)
- ✅ البيانات تظهر بشكل واضح ومنظم
- ✅ الأيقونات ملونة ومناسبة
- ✅ Badges بألوان مختلفة حسب الحالة
- ✅ Timeline يظهر الملاحظات بترتيب زمني
- ✅ Auto-refresh يعمل كل 5 ثواني
- ✅ Hover effects تعمل على العناصر
- ✅ Scrollbar بألوان بنفسجية شفافة

---

## 🐛 Troubleshooting

### Context Panel لا يظهر؟
1. تحقق من Console في المتصفح (F12)
2. تأكد من أن JavaScript يعمل
3. تأكد من أن API endpoint يعمل: `/api/conversation-context/1/+212612638500/`

### لا توجد بيانات تظهر؟
1. تحقق من Redis: `redis-cli KEYS "conv_state:*"`
2. أعد تشغيل script إضافة البيانات
3. تحقق من Channel ID الصحيح

### الألوان لا تتطابق؟
1. حدث الصفحة (Ctrl/Cmd + Shift + R)
2. تحقق من CSS في ملف whatssap.html

---

## 📝 Notes

- البيانات التجريبية تبقى في Redis لمدة **3 أيام**
- يمكن إضافة بيانات لعدة عملاء للاختبار
- استخدم `state.add_note()` لإضافة ملاحظات جديدة
- استخدم `state.set_stage()` لتغيير المرحلة

---

**Created:** August 24, 2026
**Test Phone:** +212612638500
**Test Username:** bojamaa
