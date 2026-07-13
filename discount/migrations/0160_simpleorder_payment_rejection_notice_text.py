from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("discount", "0159_alter_digitalassetstock_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="simpleorder",
            name="payment_rejection_notice_text",
            field=models.TextField(
                blank=True,
                help_text=(
                    "Full localized WhatsApp notice sent to the customer after rejection "
                    "(saved when the outbound message is delivered)."
                ),
                null=True,
            ),
        ),
    ]
