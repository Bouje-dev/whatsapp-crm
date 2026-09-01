"""
Script to populate test data for Context Panel
Run: python manage.py shell < test_context_data.py
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'disound.settings')
django.setup()

from discount.services.conversation_state import ConversationState
from django.utils import timezone

# Test data
PHONE = "+212612638500"
CHANNEL_ID = 1  # Change this to your actual channel ID

print("=" * 60)
print("🔧 CREATING TEST CONTEXT DATA")
print("=" * 60)

# Create conversation state
state = ConversationState(channel_id=CHANNEL_ID, customer_phone=PHONE)

# Clear any existing state
state.reset()
print("✅ Reset existing state")

# Set product info
state.set_product(
    product_id=101,
    product_name="iPhone 15 Pro Max - 256GB",
    price=15999.00,
    sku="IPH15PM-256-BLU"
)
print("✅ Added product: iPhone 15 Pro Max")

# Set customer info
state.set_customer_name("Bojamaa")
print("✅ Added customer name: Bojamaa")

state.set_customer_city("Casablanca")
print("✅ Added city: Casablanca")

state.set_customer_address("123 Rue Mohammed V, Quartier Maarif")
print("✅ Added address")

state.confirm_phone()
print("✅ Confirmed phone number")

# Set stage
state.set_stage("collecting_info")
print("✅ Set stage: collecting_info")

# Add some notes
state.add_note("Customer interested in blue color")
state.add_note("Asked about delivery time")
state.add_note("Prefers cash on delivery")
state.add_note("Available for delivery on weekends")
print("✅ Added conversation notes")

# Verify data
print("\n" + "=" * 60)
print("📊 TEST DATA SUMMARY")
print("=" * 60)
print(state.build_context_prompt())
print("=" * 60)
print(f"✅ Cache Key: {state.cache_key}")
print(f"✅ Ready to Order: {state.is_ready_to_order()}")
print(f"✅ Missing Fields: {state.get_missing_fields()}")
print("=" * 60)
print("\n🎉 TEST DATA CREATED SUCCESSFULLY!")
print(f"📱 Phone: {PHONE}")
print(f"📺 Channel ID: {CHANNEL_ID}")
print(f"👤 Username: bojamaa")
print("\n🔗 Now open the chat for this customer to see the Context Panel!")
print("=" * 60)
