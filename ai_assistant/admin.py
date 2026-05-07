from django.contrib import admin
from .models import AIUsageLog


@admin.register(AIUsageLog)
class AIUsageLogAdmin(admin.ModelAdmin):
    list_display = ("user", "contact_phone", "model_used", "prompt_tokens", "completion_tokens", "created_at")
    list_filter = ("model_used", "created_at")
    search_fields = ("user__username", "contact_phone")
    readonly_fields = ("user", "channel_id", "contact_phone", "prompt_tokens", "completion_tokens", "model_used", "created_at")
    ordering = ("-created_at",)
