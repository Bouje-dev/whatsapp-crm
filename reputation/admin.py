from django.contrib import admin
from django.utils.html import format_html

from .models import GlobalCustomerProfile


@admin.register(GlobalCustomerProfile)
class GlobalCustomerProfileAdmin(admin.ModelAdmin):
    list_display = [
        "phone_number",
        "total_orders",
        "delivered_count",
        "returned_count",
        "canceled_count",
        "no_answer_count",
        "trust_score_display",
        "risk_level_display",
        "last_order_date",
    ]
    list_filter = ["risk_level"]
    search_fields = ["phone_number"]
    readonly_fields = [
        "phone_number", "total_orders",
        "delivered_count", "returned_count", "canceled_count", "no_answer_count",
        "trust_score", "risk_level",
        "created_at", "updated_at",
    ]
    ordering = ["-last_order_date"]
    actions = ["recompute_selected", "recompute_all"]

    def trust_score_display(self, obj):
        return f"{obj.trust_score:.0f}"
    trust_score_display.short_description = "Score"

    def risk_level_display(self, obj):
        color = obj.risk_level_color()
        return format_html('<span style="color:{}; font-weight:bold;">{}</span>', color, obj.risk_level)
    risk_level_display.short_description = "Level"

    @admin.action(description="Recalculate selected profiles")
    def recompute_selected(self, request, queryset):
        from .services import recalculate_reputation
        from orders.models import Order
        count = 0
        for profile in queryset:
            order = Order.objects.filter(phone__endswith=profile.phone_number[-9:]).first()
            if order:
                recalculate_reputation(order.phone)
                count += 1
        self.message_user(request, f"Recalculated {count} profile(s).")

    @admin.action(description="Recalculate ALL profiles")
    def recompute_all(self, request, queryset):
        from .services import recalculate_all_reputations
        count = recalculate_all_reputations()
        self.message_user(request, f"Recalculated {count} profile(s).")
