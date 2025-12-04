import requests

# ضع البيانات هنا
ACCESS_TOKEN ="EAALZBubBgmq0BQHmIewxaHrZBwF67lMsRRj012KOo8hNl8ab6agSmVSHqkzZCNbhHZChionX5hJwiXHMYu7pLI7ZANqxFKoBZAgrBv6X0jarDAwIyMBEYoEvQNXzWKrQocyG7cR7m8Hftt9fTtvPAZCimPA9qMKfXo20qz0MQlzjzUnLbyVzx5PSzbaYA7oyfNK6AZDZD"

WABA_ID = "838444915721462"

url = f"https://graph.facebook.com/v18.0/{WABA_ID}/subscribed_apps"

headers = {
    "Authorization": f"Bearer {ACCESS_TOKEN}",
    "Content-Type": "application/json"
}

response = requests.post(url, headers=headers)

print(f"Status Code: {response.status_code}")
print(f"Response: {response.text}")

if response.status_code == 200:
    print("✅ تم تفعيل الويب هوك للرقم الجديد بنجاح! جرب الآن.")
else:
    print("❌ حدث خطأ، تأكد من WABA ID والتوكن.")