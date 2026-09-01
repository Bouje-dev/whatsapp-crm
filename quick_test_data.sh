#!/bin/bash
# Quick Test Data Generator
# Usage: ./quick_test_data.sh [phone_number]

PHONE="${1:-+212612638500}"
VENV_PATH="venv11"

echo "🔧 Adding test data for: $PHONE"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

source $VENV_PATH/bin/activate

python manage.py shell << EOF
from discount.services.conversation_state import ConversationState
from django.utils import timezone

PHONE = "$PHONE"
CHANNEL_ID = 1

print("🔧 Creating test data...")

state = ConversationState(channel_id=CHANNEL_ID, customer_phone=PHONE)
state.reset()

state.set_product(
    product_id=101,
    product_name="iPhone 15 Pro Max - 256GB",
    price=15999.00,
    sku="IPH15PM-256-BLU"
)

state.set_customer_name("Bojamaa")
state.set_customer_city("Casablanca")
state.set_customer_address("123 Rue Mohammed V, Quartier Maarif")
state.confirm_phone()
state.set_stage("collecting_info")

state.add_note("Customer interested in blue color")
state.add_note("Asked about delivery time")
state.add_note("Prefers cash on delivery")
state.add_note("Available for delivery on weekends")

print("")
print("=" * 60)
print("✅ TEST DATA CREATED SUCCESSFULLY!")
print("=" * 60)
print(f"📱 Phone: {PHONE}")
print(f"📺 Channel ID: {CHANNEL_ID}")
print(f"👤 Customer: Bojamaa")
print(f"📦 Product: iPhone 15 Pro Max - 256GB")
print(f"💰 Price: 15,999.00 DH")
print(f"📊 Stage: collecting_info")
print(f"✅ Ready: {state.is_ready_to_order()}")
print("=" * 60)
print("")
print("🔗 Open the chat for this customer to see the Context Panel!")
print("")
EOF

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Done!"
