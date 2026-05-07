from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("discount", "0140_remove_whatsappchannel_bot_language"),
    ]

    operations = [
        migrations.AddField(
            model_name="chatsession",
            name="active_product",
            field=models.ForeignKey(
                blank=True,
                help_text="Persistent product memory for AI context (survives prompt truncation).",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="active_product_sessions",
                to="discount.products",
            ),
        ),
    ]
