# Remove WhatsAppChannel.bot_language (language comes from voice_language only).

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("discount", "0139_rename_dc_ecss_owner_active_discount_ex_billing_c34026_idx"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="whatsappchannel",
            name="bot_language",
        ),
    ]
