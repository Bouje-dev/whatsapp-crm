"""
Generate sample traffic (CampaignVisit) and orders (Store, Order, Attribution) for testing.
Usage: python manage.py generate_test_orders [--users 1] [--visits 30] [--orders 25]
"""
import random
from decimal import Decimal
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.auth import get_user_model

User = get_user_model()

# Sample data
CAMPAIGNS = [
    ("Winter Sale 2025", "facebook", "ad_winter_1", "AdSet A"),
    ("Winter Sale 2025", "facebook", "ad_winter_2", "AdSet B"),
    ("Brand Awareness", "facebook", "ad_brand_1", "AdSet Brand"),
    ("Google Search CPC", "google", "ad_google_1", "Search AdSet"),
    ("TikTok Reach", "tiktok", "ad_tiktok_1", "TikTok AdSet"),
]
CITIES = ["Riyadh", "Jeddah", "Dammam", "Makkah", "Medina", "Khobar", "Tabuk"]
PRODUCTS = [
    ("Wireless Earbuds Pro", "49.99"),
    ("Phone Stand", "12.50"),
    ("USB-C Cable Pack", "8.99"),
    ("Desk Lamp LED", "24.00"),
    ("Notebook Set", "15.00"),
]
FIRST_NAMES = ["Ahmed", "Sara", "Mohammed", "Fatima", "Omar", "Nora", "Khalid", "Layla", "Ali", "Huda"]
PHONE_PREFIXES = ["+9665", "+9665", "+9665", "+9665", "+9665"]  # Saudi-style


def normalize_phone(phone):
    return "".join(c for c in phone if c.isdigit())[-9:] or phone[:9]


class Command(BaseCommand):
    help = "Generate test CampaignVisits (traffic) and Orders with optional Attribution."

    def add_arguments(self, parser):
        parser.add_argument("--users", type=int, default=1, help="Number of owner users to use (from first N users)")
        parser.add_argument("--visits", type=int, default=40, help="Number of campaign visits (traffic) to create")
        parser.add_argument("--orders", type=int, default=25, help="Number of orders to create")
        parser.add_argument("--external", type=int, default=15, help="Number of ExternalOrders (marketing dashboard) to create and link to visits")
        parser.add_argument("--clear-orders", action="store_true", help="Delete existing orders/stores/attributions (not visits) before creating")

    def handle(self, *args, **options):
        n_users = max(1, options["users"])
        n_visits = max(1, options["visits"])
        n_orders = max(1, options["orders"])
        clear_first = options["clear_orders"]

        users = list(User.objects.filter(is_active=True)[: n_users + 5])  # extra for agents
        if not users:
            self.stdout.write(self.style.ERROR("No active users. Create a user first."))
            return

        owner = users[0]
        agents = users[1:4] if len(users) > 1 else []

        # ----- Traffic (CampaignVisit) -----
        from discount.models import CampaignVisit

        self.stdout.write("Creating campaign visits (traffic)...")
        created_visits = []
        for i in range(n_visits):
            campaign_name, utm_source, ad_id, adset_name = random.choice(CAMPAIGNS)
            phone_suffix = "".join([str(random.randint(0, 9)) for _ in range(8)])
            raw = random.choice(PHONE_PREFIXES) + phone_suffix
            phone_norm = normalize_phone(raw)
            visit = CampaignVisit.objects.create(
                user=owner,
                flow=None,
                visit_id=f"v_{i}_{random.randint(1000, 9999)}",
                raw_phone=raw,
                phone_normalized=phone_norm,
                utm_campaign=campaign_name,
                utm_source=utm_source,
                utm_medium=random.choice(["feed", "story", "cpc", "display"]),
                ad_id=ad_id,
                site_source_name=utm_source,
                ad_adset_name=adset_name,
                created_at=timezone.now() - timedelta(days=random.randint(0, 14)),
            )
            created_visits.append(visit)

        self.stdout.write(self.style.SUCCESS(f"  Created {len(created_visits)} campaign visits."))

        # ----- Orders app: Store, Attribution, Order -----
        from orders.models import Store, Attribution, Order

        if clear_first:
            Order.objects.all().delete()
            Attribution.objects.all().delete()
            Store.objects.filter(owner=owner).delete()
            self.stdout.write("  Cleared existing orders, attributions, and your stores.")

        store, _ = Store.objects.get_or_create(owner=owner, defaults={"name": "Main Store"})
        if not store:
            store = Store.objects.filter(owner=owner).first()
        if not store:
            store = Store.objects.create(name="Main Store", owner=owner)
        self.stdout.write(f"  Using store: {store.name}")

        # Attributions from a subset of visits (so some orders can link to them)
        self.stdout.write("Creating attributions...")
        attributions = []
        for visit in created_visits[: min(20, len(created_visits))]:
            att, _ = Attribution.objects.get_or_create(
                campaign_visit=visit,
                defaults={
                    "utm_campaign": visit.utm_campaign or "",
                    "utm_source": visit.utm_source or "",
                    "ad_id": visit.ad_id or "",
                },
            )
            attributions.append(att)
        self.stdout.write(self.style.SUCCESS(f"  Created/using {len(attributions)} attributions."))

        # Orders: mix of statuses, some with attribution, some with agent
        self.stdout.write("Creating orders...")
        statuses = [
            Order.STATUS_NEW,
            Order.STATUS_NEW,
            Order.STATUS_PENDING_CONFIRMATION,
            Order.STATUS_CONFIRMED,
            Order.STATUS_CONFIRMED,
            Order.STATUS_SHIPPED,
            Order.STATUS_DELIVERED,
            Order.STATUS_DELIVERED,
            Order.STATUS_CANCELED,
            Order.STATUS_NO_ANSWER,
        ]
        # Attributions not yet linked to an order (OneToOne: one attribution per order)
        att_ids_available = list(Attribution.objects.filter(order__isnull=True).values_list("id", flat=True))
        orders_created = 0
        for i in range(n_orders):
            name = f"{random.choice(FIRST_NAMES)} {random.choice(FIRST_NAMES)}"
            phone_suffix = "".join([str(random.randint(0, 9)) for _ in range(8)])
            phone = random.choice(PHONE_PREFIXES) + phone_suffix
            product, price_str = random.choice(PRODUCTS)
            status = random.choice(statuses)
            agent = random.choice(agents) if agents and random.random() < 0.4 else None
            created = timezone.now() - timedelta(days=random.randint(0, 14))

            order = Order(
                store=store,
                name=name,
                phone=phone,
                address=f"Street {random.randint(1, 99)}, Block {random.randint(1, 20)}",
                city=random.choice(CITIES),
                product_name=product,
                price=Decimal(price_str),
                quantity=random.randint(1, 3),
                status=status,
                assigned_agent=agent,
                created_at=created,
            )
            order.save()
            if att_ids_available and random.random() < 0.5:
                att_id = att_ids_available.pop(random.randint(0, len(att_ids_available) - 1))
                order.attribution_data_id = att_id
                order.save(update_fields=["attribution_data_id"])
            orders_created += 1

        self.stdout.write(self.style.SUCCESS(f"  Created {orders_created} orders."))

        # Optional: ExternalOrder (for marketing analytics dashboard)
        n_external = max(0, options.get("external", 0))
        if n_external and created_visits:
            from discount.models import ExternalOrder
            ext_statuses = ["created", "confirmed", "confirmed", "delivered", "shipped", "cancelled"]
            for i in range(n_external):
                visit = random.choice(created_visits)
                ExternalOrder.objects.create(
                    external_order_id=f"EXT-{random.randint(10000, 99999)}",
                    phone_normalized=visit.phone_normalized or "",
                    raw_phone=visit.raw_phone or "",
                    customer_name=f"{random.choice(FIRST_NAMES)} {random.choice(FIRST_NAMES)}",
                    status=random.choice(ext_statuses),
                    created_at=visit.created_at,
                    matched_visit=visit,
                    platform=visit.utm_source or "cod",
                )
            self.stdout.write(self.style.SUCCESS(f"  Created {n_external} ExternalOrders (linked to visits) for analytics dashboard."))

        self.stdout.write(self.style.SUCCESS("Done. Visit /orders/ and your analytics dashboard to see the data."))
