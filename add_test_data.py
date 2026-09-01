"""
Simple script to add test data directly to Redis
Usage: python add_test_data.py
"""
import json
import redis
from datetime import datetime

# Redis connection (adjust if your Redis config is different)
r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

# Test data
PHONE = "+212612638500"
CHANNEL_ID = 1  # Change to your actual channel ID
CACHE_KEY = f"conv_state:{CHANNEL_ID}:{PHONE}"

# Build test state
test_state = {
    'product': 101,
    'product_name': 'iPhone 15 Pro Max - 256GB',
    'product_price': 15999.00,
    'product_sku': 'IPH15PM-256-BLU',
    'quantity': 1,
    'customer_name': 'Bojamaa',
    'customer_city': 'Casablanca',
    'customer_address': '123 Rue Mohammed V, Quartier Maarif',
    'phone_confirmed': True,
    'stage': 'collecting_info',
    'intent': 'order_placement',
    'last_updated': datetime.now().isoformat(),
    'conversation_started': datetime.now().isoformat(),
    'notes': [
        "23:45: المنتج المختار: iPhone 15 Pro Max - 256GB (#101)",
        "23:46: الاسم: Bojamaa",
        "23:46: المدينة: Casablanca",
        "23:47: Customer interested in blue color",
        "23:48: Asked about delivery time",
        "23:49: Prefers cash on delivery",
        "23:50: Available for delivery on weekends"
    ]
}

# Save to Redis
r.set(CACHE_KEY, json.dumps(test_state, ensure_ascii=False))
r.expire(CACHE_KEY, 86400 * 3)  # 3 days

print("=" * 60)
print("🎉 TEST DATA ADDED TO REDIS!")
print("=" * 60)
print(f"📱 Phone: {PHONE}")
print(f"📺 Channel ID: {CHANNEL_ID}")
print(f"👤 Username: bojamaa")
print(f"🔑 Cache Key: {CACHE_KEY}")
print("\n📦 Product: iPhone 15 Pro Max - 256GB")
print("💰 Price: 15,999.00 DH")
print("👤 Name: Bojamaa")
print("🏙️ City: Casablanca")
print("📍 Address: 123 Rue Mohammed V, Quartier Maarif")
print("📊 Stage: collecting_info")
print("📝 Notes: 7 conversation notes")
print("\n🔗 Now open the chat for +212612638500 to see the data!")
print("=" * 60)
