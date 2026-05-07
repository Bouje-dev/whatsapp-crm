# Orders app – lightweight CRM / Order Manager

## Setup

1. **Migrations** (run in your venv):
   ```bash
   python manage.py migrate orders
   ```
   If you get a dependency error, change `orders/migrations/0001_initial.py` to depend on your latest `discount` migration.

2. **Create a Store** for the current user (Django shell or admin):
   ```python
   from orders.models import Store
   from django.contrib.auth import get_user_model
   User = get_user_model()
   user = User.objects.first()
   store = Store.objects.create(name="My Store", owner=user)
   ```
   Then create orders with `store=store`. Or register `Store` in admin and create from there.

## URLs

- **List:** `/orders/`
- **HTMX table partial:** `/orders/partial/table/?status=...&phone=...&date_after=...&date_before=...`
- **Update status (POST):** `/orders/update-status/<id>/`
- **Update agent (POST):** `/orders/update-agent/<id>/`
- **Bulk assign (POST):** `/orders/bulk-assign/`

## Role-based access

- **Staff / superuser:** see all orders.
- **Store owner** (`user.owned_stores.exists()`): see all orders of their stores.
- **Agent:** see only orders where `assigned_agent=user`.

## Attribution & DELIVERED

- `Order.attribution_data` is an optional OneToOne to `orders.Attribution`; `Attribution` can link to `discount.CampaignVisit`.
- When an order is saved with `status=DELIVERED`, a placeholder is in `Order.save()`: `# TODO: Update Campaign ROI here`.

## WhatsApp button

The “WhatsApp” button in the actions column is a placeholder; wire it to your WhatsApp module when ready.
