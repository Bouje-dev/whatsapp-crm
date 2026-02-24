# Notify owner when AI creates an order (Email or WhatsApp)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("discount", "0094_voice_gallery_multilingual_v2"),
    ]

    operations = [
        migrations.AddField(
            model_name="whatsappchannel",
            name="order_notify_method",
            field=models.CharField(
                blank=True,
                choices=[("", "Off"), ("EMAIL", "Email"), ("WHATSAPP", "WhatsApp")],
                default="",
                help_text="Send owner a notification when AI creates an order.",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="whatsappchannel",
            name="order_notify_email",
            field=models.EmailField(
                blank=True,
                help_text="Email address for order notifications (when method is Email).",
                max_length=254,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="whatsappchannel",
            name="order_notify_whatsapp_phone",
            field=models.CharField(
                blank=True,
                help_text="Phone (with country code) for WhatsApp order notifications.",
                max_length=20,
                null=True,
            ),
        ),
    ]
