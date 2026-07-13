# Generated manually for Founder HQ risk module

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("discount", "0161_products_return_policy"),
    ]

    operations = [
        migrations.CreateModel(
            name="MerchantRiskEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("customer_phone", models.CharField(blank=True, default="", max_length=30)),
                (
                    "event_type",
                    models.CharField(
                        choices=[
                            ("support_complaint", "Support complaint"),
                            ("flag_for_review", "Flagged for review"),
                            ("payment_rejected", "Payment receipt rejected"),
                            ("negative_sentiment", "Negative sentiment / rejection"),
                        ],
                        db_index=True,
                        max_length=32,
                    ),
                ),
                ("summary", models.TextField(blank=True, default="")),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "channel",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="risk_events",
                        to="discount.whatsappchannel",
                    ),
                ),
                (
                    "merchant",
                    models.ForeignKey(
                        limit_choices_to={"is_bot": False},
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="risk_events",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "order",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="risk_events",
                        to="discount.simpleorder",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="FounderRiskAlert",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("alert_date", models.DateField(db_index=True)),
                ("complaints_count", models.PositiveIntegerField(default=0)),
                ("notified_at", models.DateTimeField(auto_now_add=True)),
                (
                    "merchant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="founder_risk_alerts",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.AddIndex(
            model_name="merchantriskevent",
            index=models.Index(fields=["merchant", "-created_at"], name="discount_me_merchan_8a1f2c_idx"),
        ),
        migrations.AddIndex(
            model_name="merchantriskevent",
            index=models.Index(fields=["merchant", "event_type", "-created_at"], name="discount_me_merchan_4b3e9d_idx"),
        ),
        migrations.AlterUniqueTogether(
            name="founderriskalert",
            unique_together={("merchant", "alert_date")},
        ),
    ]
