# import requests

# # ضع البيانات هنا
# ACCESS_TOKEN ="EAALZBubBgmq0BQHmIewxaHrZBwF67lMsRRj012KOo8hNl8ab6agSmVSHqkzZCNbhHZChionX5hJwiXHMYu7pLI7ZANqxFKoBZAgrBv6X0jarDAwIyMBEYoEvQNXzWKrQocyG7cR7m8Hftt9fTtvPAZCimPA9qMKfXo20qz0MQlzjzUnLbyVzx5PSzbaYA7oyfNK6AZDZD"

# WABA_ID = "838444915721462"

# url = f"https://graph.facebook.com/v18.0/{WABA_ID}/subscribed_apps"

# headers = {
#     "Authorization": f"Bearer {ACCESS_TOKEN}",
#     "Content-Type": "application/json"
# }

# response = requests.post(url, headers=headers)

# print(f"Status Code: {response.status_code}")
# print(f"Response: {response.text}")

# if response.status_code == 200:
#     print("✅ تم تفعيل الويب هوك للرقم الجديد بنجاح! جرب الآن.")
# else:
#     print("❌ حدث خطأ، تأكد من WABA ID والتوكن.")





import hashlib

# def crack_imile_salt():
#     # البيانات الحقيقية التي حصلت عليها أنت من المتصفح
#     waybill = "6120825213610"
#     target_hash = "e20bfad98c95bbbb062feeda7ef3ce6d"

#     # قائمة الكلمات المحتملة (Salts) التي يستخدمها المبرمجون عادة
#     # يمكنك إضافة المزيد من الكلمات هنا إذا أردت
#     common_salts = [
#         "imileTrackQuery2024", "imile", "IMILE", "Imile",
#         "iMile2022", "iMile2023", "iMile2024", "iMile2025",
#         "track", "tracking", "query", "param",
#         "secret", "key", "salt", "123456", "12345678",
#         "imile_track", "customer", "client",
#         "Sign", "signature", "md5", "check",
#         "H5", "h5", "mobile", "app",
#         "ae", "sa", "AE", "SA", # رموز الدول
#         "express", "delivery",
#         "", # أحياناً لا يوجد سر، فقط تشفير الرقم
#     ]

#     print(f"🔍 Searching for the secret salt for waybill: {waybill}...")

#     for salt in common_salts:
#         # المبرمجون يدمجون الرقم والسر بطريقتين عادة:
        
#         # الطريقة 1: الرقم + السر
#         s1 = f"{waybill}{salt}"
#         h1 = hashlib.md5(s1.encode()).hexdigest()
        
#         # الطريقة 2: السر + الرقم
#         s2 = f"{salt}{waybill}"
#         h2 = hashlib.md5(s2.encode()).hexdigest()

#         # الطريقة 3: (معادلة خاصة) ربما: param=رقم&salt=سر
#         s3 = f"waybillNo={waybill}&salt={salt}"
#         h3 = hashlib.md5(s3.encode()).hexdigest()
        
#         # مقارنة النتيجة
#         if h1 == target_hash:
#             return f"🎉 FOUND IT! The salt is: '{salt}' (Format: Waybill + Salt)"
#         if h2 == target_hash:
#             return f"🎉 FOUND IT! The salt is: '{salt}' (Format: Salt + Waybill)"
#         if h3 == target_hash:
#             return f"🎉 FOUND IT! The salt is: '{salt}' (Format: Complex)"

#     return "❌ Not found in common list. We need to look deeper in JS files."

# # تشغيل الكاسر
# result = crack_imile_salt()
# print(result)




import hashlib
import requests
import json

 

from django.conf import settings

 # بدلاً من استخدام توكن العميل فقط، جرب إرسال التوكن كمعامل (Param)
# واستخدم App Access Token في الـ Headers (أحياناً يحل هذا مشكلة الـ Permission)
target_waba_id = 1504186850696314
app_access_token = f"{settings.META_APP_ID}|{settings.META_APP_SECRET}"
subscribe_url = f"https://graph.facebook.com/v24.0/{target_waba_id}/subscribed_apps"

params = {
    'access_token': 'EAALZBubBgmq0BQUpecOrUvRcKddYIbLJUIinT7GcBHUh2azmAJRv9oU5yiG9F7JHcTdnrdJYAPxZBTuutNKmrEBdRsh2mSslvRzhW1qZCaZBmlPY7l4LcyQv6hVpMfK2iLQmHAaI7kHYca0nhtTNNlVJ2noFPiQ7SJHlD1tvXBc6Hw3g2ZAgFwkAtMALuAIX0n3xgmCK4MaSmOefNcwfB9j9N46Tgm1dJzvcqr7ze7utd0Dy1ZAWj6LzC5row48WYxAtyNgXWZCDamkQqC9q0OUAxJ2qCI24Iwxs8JN' # توكن العميل
}


headers = {
    "Authorization": f"Bearer {app_access_token}" 
}

resp = requests.post(subscribe_url, params=params, headers=headers)
print(resp.text)