from django.db import models
from django.conf import settings


class AIUsageLog(models.Model):
    """Tracks AI assist usage per agent for monitoring and rate-limiting."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ai_usage_logs",
    )
    channel_id = models.IntegerField(null=True, blank=True)
    contact_phone = models.CharField(max_length=30)
    prompt_tokens = models.IntegerField(default=0)
    completion_tokens = models.IntegerField(default=0)
    model_used = models.CharField(max_length=50, default="gpt-4o-mini")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.user} | {self.contact_phone} | {self.created_at:%Y-%m-%d %H:%M}"
