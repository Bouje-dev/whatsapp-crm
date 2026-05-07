# AI Agent node fields (product_context, context_source, voice_enabled, ai_model_config)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("discount", "0095_order_notify_email_whatsapp"),
    ]

    operations = [
        migrations.AddField(
            model_name="node",
            name="product_context",
            field=models.TextField(blank=True, help_text="Product details: Name, Price, Specs, Shipping", null=True),
        ),
        migrations.AddField(
            model_name="node",
            name="context_source",
            field=models.CharField(blank=True, choices=[("MANUAL", "Manual"), ("URL_SCRAPER", "URL Scraper")], default="MANUAL", max_length=20),
        ),
        migrations.AddField(
            model_name="node",
            name="voice_enabled",
            field=models.BooleanField(default=False, help_text="Use voice_engine for response"),
        ),
        migrations.AddField(
            model_name="node",
            name="ai_model_config",
            field=models.JSONField(blank=True, default=dict, help_text="temperature, model_id, etc."),
        ),
    ]
