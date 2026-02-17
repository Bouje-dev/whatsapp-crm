"""
Order Management Models (CRM / Order Tracker).
"""
from django.db import models
from django.conf import settings
from django.utils import timezone

from .managers import OrderManager


class Store(models.Model):
    name = models.CharField(max_length=255)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="owned_stores",
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Attribution(models.Model):
    utm_campaign = models.CharField(max_length=200, blank=True)
    utm_source = models.CharField(max_length=200, blank=True)
    ad_id = models.CharField(max_length=200, blank=True)
    campaign_visit = models.OneToOneField(
        "discount.CampaignVisit",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_attribution",
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        parts = [self.utm_source, self.utm_campaign]
        return " / ".join(p for p in parts if p) or f"Attribution {self.pk}"


class Order(models.Model):
    STATUS_NEW = "NEW"
    STATUS_CHOICES = [
        ("NEW", "New"),
        ("PENDING_CONFIRMATION", "Pending confirmation"),
        ("CONFIRMED", "Confirmed"),
        ("SHIPPED", "Shipped"),
        ("DELIVERED", "Delivered"),
        ("CANCELED", "Canceled"),
        ("RETURNED", "Returned"),
        ("NO_ANSWER", "No answer"),
    ]

    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="orders")
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=32, db_index=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=120, blank=True)
    product_name = models.CharField(max_length=255)
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    quantity = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="NEW")
    assigned_agent = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_orders",
    )
    attribution_data = models.OneToOneField(
        Attribution,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order",
    )
    client_data = models.JSONField(default=dict, blank=True, help_text="Full visit/capture payload")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    objects = OrderManager()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Order #{self.pk} - {self.name} ({self.status})"

    def get_reputation_badge(self):
        """
        Query GlobalCustomerProfile for this phone and return badge dict.
        Used by order_row.html template.
        """
        if not self.phone:
            return {
                "level": "NEW", "score": 50, "color": "gray",
                "explanation": "No phone", "tooltip_title": "No data",
                "tooltip_html": "<div>No phone number</div>",
            }

        try:
            from reputation.models import GlobalCustomerProfile
            from reputation.utils import normalize_phone_for_reputation

            phone_key = normalize_phone_for_reputation(self.phone)
            if not phone_key:
                return {
                    "level": "NEW", "score": 50, "color": "gray",
                    "explanation": "Invalid phone", "tooltip_title": "No data",
                    "tooltip_html": "<div>Invalid phone</div>",
                }

            try:
                profile = GlobalCustomerProfile.objects.get(phone_number=phone_key)
            except GlobalCustomerProfile.DoesNotExist:
                return {
                    "level": "NEW", "score": 50, "total_finalized": 0,
                    "color": "gray", "explanation": "No order history",
                    "tooltip_title": "New customer",
                    "tooltip_html": "<div>No previous orders</div>",
                }

            # Build popover HTML
            lines = []
            if profile.delivered_count:
                lines.append(
                    f"<span class='rep-tt-row'><span class='rep-tt-label'>Delivered</span> "
                    f"<span class='rep-tt-val rep-tt-good'>{profile.delivered_count} &times; (+10)</span></span>"
                )
            if profile.returned_count:
                lines.append(
                    f"<span class='rep-tt-row'><span class='rep-tt-label'>Returned</span> "
                    f"<span class='rep-tt-val rep-tt-bad'>{profile.returned_count} &times; (&minus;10)</span></span>"
                )
            if profile.canceled_count:
                lines.append(
                    f"<span class='rep-tt-row'><span class='rep-tt-label'>Canceled</span> "
                    f"<span class='rep-tt-val rep-tt-mid'>{profile.canceled_count} &times; (&minus;2)</span></span>"
                )
            if profile.no_answer_count:
                lines.append(
                    f"<span class='rep-tt-row'><span class='rep-tt-label'>No answer</span> "
                    f"<span class='rep-tt-val rep-tt-bad'>{profile.no_answer_count} &times; (&minus;5)</span></span>"
                )

            body = "".join(lines)
            score_int = int(round(profile.trust_score))
            body += (
                f"<div class='rep-tt-score-line'><strong>Score</strong> = <strong>{score_int}</strong></div>"
                f"<div class='rep-tt-level-line'><strong>Level</strong> {profile.risk_level}</div>"
                "<p class='rep-tt-muted'>ELITE &ge;80 &middot; GOOD 60&ndash;79 &middot; NEUTRAL 40&ndash;59 &middot; RISKY 20&ndash;39 &middot; BLACKLIST &lt;20</p>"
            )
            tooltip_html = f"<div class='rep-popover-body'>{body}</div>"

            # Plain-text explanation (title fallback)
            parts = []
            if profile.delivered_count:
                parts.append(f"{profile.delivered_count} delivered (+{profile.delivered_count * 10})")
            if profile.returned_count:
                parts.append(f"{profile.returned_count} returned ({profile.returned_count * -10})")
            if profile.canceled_count:
                parts.append(f"{profile.canceled_count} canceled ({profile.canceled_count * -2})")
            if profile.no_answer_count:
                parts.append(f"{profile.no_answer_count} no answer ({profile.no_answer_count * -5})")
            summary = "; ".join(parts) if parts else "No finalized orders"
            explanation = f"{summary}. Score {score_int} = {profile.risk_level}."

            return {
                "level": profile.risk_level,
                "score": score_int,
                "total_finalized": profile.total_orders,
                "color": profile.risk_level_color(),
                "explanation": explanation,
                "tooltip_title": "Risk breakdown",
                "tooltip_html": tooltip_html,
            }

        except Exception:
            import logging
            logging.exception("get_reputation_badge failed pk=%s", self.pk)
            return {
                "level": "ERROR", "score": 0, "color": "gray",
                "explanation": "Error", "tooltip_title": "Error",
                "tooltip_html": "<div>Error loading reputation</div>",
            }
