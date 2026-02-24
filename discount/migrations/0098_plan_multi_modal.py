# Plan: can_use_multi_modal for AI node media gallery

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("discount", "0097_node_ai_voice_media_response_mode"),
    ]

    operations = [
        migrations.AddField(
            model_name="plan",
            name="can_use_multi_modal",
            field=models.BooleanField(
                default=False,
                help_text="AI node media gallery & [SEND_MEDIA] in flows",
            ),
        ),
    ]
