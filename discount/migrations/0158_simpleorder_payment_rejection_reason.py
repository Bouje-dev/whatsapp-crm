from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("discount", "0157_simpleorder_post_sale_support"),
    ]

    operations = [
        migrations.AddField(
            model_name="simpleorder",
            name="payment_rejection_reason",
            field=models.CharField(
                blank=True,
                help_text=(
                    "Merchant-provided reason when a payment receipt was rejected; "
                    "cleared on approval. Order returns to pending_payment for resubmission."
                ),
                max_length=255,
                null=True,
            ),
        ),
    ]
