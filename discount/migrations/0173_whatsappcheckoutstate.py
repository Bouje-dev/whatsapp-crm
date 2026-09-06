from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("discount", "0172_products_aliases_embedding"),
    ]

    operations = [
        migrations.CreateModel(
            name="WhatsAppCheckoutState",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("customer_phone", models.CharField(db_index=True, max_length=32)),
                ("customer_name", models.CharField(blank=True, default="", max_length=200)),
                ("city", models.CharField(blank=True, default="", max_length=200)),
                ("address", models.CharField(blank=True, default="", max_length=500)),
                ("email_address", models.CharField(blank=True, default="", max_length=254)),
                (
                    "is_ready_for_checkout",
                    models.BooleanField(
                        db_index=True,
                        default=False,
                        help_text="True when all product-required fields are present (product + slots).",
                    ),
                ),
                (
                    "raw_extractions",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text="Last LLM extraction payload for debugging / audit.",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "channel",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="checkout_states",
                        to="discount.whatsappchannel",
                    ),
                ),
                (
                    "product",
                    models.ForeignKey(
                        blank=True,
                        help_text="Resolved catalog product for this checkout (fuzzy / session sync).",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="checkout_states",
                        to="discount.products",
                    ),
                ),
            ],
            options={
                "verbose_name": "WhatsApp checkout state",
                "verbose_name_plural": "WhatsApp checkout states",
            },
        ),
        migrations.AddIndex(
            model_name="whatsappcheckoutstate",
            index=models.Index(fields=["channel", "customer_phone"], name="discount_wh_channel_0e8c1a_idx"),
        ),
        migrations.AddIndex(
            model_name="whatsappcheckoutstate",
            index=models.Index(fields=["channel", "is_ready_for_checkout"], name="discount_wh_channel_9f2b4d_idx"),
        ),
        migrations.AddConstraint(
            model_name="whatsappcheckoutstate",
            constraint=models.UniqueConstraint(
                fields=("channel", "customer_phone"),
                name="unique_channel_customer_checkout_state",
            ),
        ),
    ]
