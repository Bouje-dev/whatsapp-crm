from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("discount", "0160_simpleorder_payment_rejection_notice_text"),
    ]

    operations = [
        migrations.AddField(
            model_name="products",
            name="return_policy",
            field=models.TextField(
                blank=True,
                help_text=(
                    "Specific return/warranty policy for this product. If left blank, AI will apply "
                    "standard strict delivery rules."
                ),
                null=True,
                verbose_name="Return / warranty policy",
            ),
        ),
    ]
