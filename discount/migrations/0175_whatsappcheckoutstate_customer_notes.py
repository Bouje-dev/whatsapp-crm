from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("discount", "0174_products_checkout_method"),
    ]

    operations = [
        migrations.AddField(
            model_name="whatsappcheckoutstate",
            name="customer_notes",
            field=models.TextField(
                blank=True,
                default="",
                help_text=(
                    "Accumulated customer profile context for sales personalization "
                    "(pain points, objections, skin/health concerns, location nuances, "
                    "prior bad experiences). Updated by the entity extractor; not checkout slots."
                ),
            ),
        ),
    ]
