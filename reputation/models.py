from django.db import models


class GlobalCustomerProfile(models.Model):
    """
    Global Customer Reputation Profile.
    All fields are recalculated from Order table on every save (stateless aggregation).
    """
    phone_number = models.CharField(max_length=32, unique=True, db_index=True)
    fingerprint_hash = models.CharField(max_length=64, blank=True)

    # Aggregated counters (overwritten from Order table, never incremented)
    total_orders = models.PositiveIntegerField(
        default=0,
        help_text="Total finalized orders (DELIVERED + RETURNED + CANCELED + NO_ANSWER)",
    )
    delivered_count = models.PositiveIntegerField(default=0)
    returned_count = models.PositiveIntegerField(default=0)
    canceled_count = models.PositiveIntegerField(default=0)
    no_answer_count = models.PositiveIntegerField(default=0)

    # Stored score and level (written by recalculate_reputation, not computed properties)
    trust_score = models.FloatField(
        default=50.0,
        help_text="Trust score 0-100. Base 50 + Delivered*10 - Returned*10 - NoAnswer*5 - Canceled*2",
    )
    risk_level = models.CharField(
        max_length=16,
        choices=[
            ("ELITE", "Elite"),
            ("GOOD", "Good"),
            ("NEUTRAL", "Neutral"),
            ("RISKY", "Risky"),
            ("BLACKLIST", "Blacklist"),
        ],
        default="NEUTRAL",
    )

    last_order_date = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-last_order_date", "-updated_at"]
        verbose_name = "Global Customer Profile"
        verbose_name_plural = "Global Customer Profiles"
        indexes = [
            models.Index(fields=["-last_order_date"], name="rep_last_order_idx"),
            models.Index(fields=["risk_level"], name="rep_risk_level_idx"),
        ]

    def __str__(self):
        return f"{self.phone_number} (score={self.trust_score:.0f}, {self.risk_level})"

    def risk_level_color(self):
        """Return CSS class suffix for rep-badge--{color}."""
        return {
            "ELITE": "green",
            "GOOD": "blue",
            "NEUTRAL": "gray",
            "RISKY": "yellow",
            "BLACKLIST": "red",
        }.get(self.risk_level, "gray")

    @property
    def delivery_rate_pct(self):
        if self.total_orders == 0:
            return 0.0
        return (self.delivered_count / self.total_orders) * 100.0
