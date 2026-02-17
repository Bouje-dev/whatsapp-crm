from django.contrib import admin
from .models import Store, Attribution, Order


@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    list_display = ["name", "owner", "created_at"]
    list_filter = ["owner"]


@admin.register(Attribution)
class AttributionAdmin(admin.ModelAdmin):
    list_display = ["utm_campaign", "utm_source", "ad_id", "created_at"]


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "phone", "product_name", "status", "assigned_agent", "store", "created_at"]
    list_filter = ["status", "store", "assigned_agent"]
    search_fields = ["name", "phone", "product_name"]
