from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("discount", "0135_userpermissionsetting_templates_channels"),
    ]

    operations = [
        migrations.CreateModel(
            name="ExtraChannelSlotSubscription",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("stripe_subscription_id", models.CharField(max_length=255, unique=True)),
                ("stripe_customer_id", models.CharField(blank=True, max_length=255, null=True)),
                ("active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "billing_owner",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="extra_channel_slot_subscriptions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={},
        ),
        migrations.AddIndex(
            model_name="extrachannelslotsubscription",
            index=models.Index(fields=["billing_owner", "active"], name="dc_ecss_owner_active"),
        ),
    ]
