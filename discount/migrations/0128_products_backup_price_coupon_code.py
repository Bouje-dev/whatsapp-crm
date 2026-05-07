from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("discount", "0127_customuser_low_balance_alert_enabled_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="products",
            name="backup_price",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Optional fallback/negotiation price used by AI when offering a discount.",
                max_digits=12,
                null=True,
                verbose_name="سعر احتياطي للتفاوض",
            ),
        ),
        migrations.AddField(
            model_name="products",
            name="coupon_code",
            field=models.CharField(
                blank=True,
                help_text="Optional coupon code the AI can use during negotiation.",
                max_length=64,
                null=True,
                verbose_name="كود كوبون",
            ),
        ),
    ]
