# Voice Gallery & Multilingual v2 (elevenlabs_model_id, selected_voice_id, voice_preview_url)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("discount", "0093_voice_studio_plan_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="whatsappchannel",
            name="elevenlabs_model_id",
            field=models.CharField(
                default="eleven_multilingual_v2",
                help_text="ElevenLabs model; use eleven_multilingual_v2 for natural Arabic.",
                max_length=64,
            ),
        ),
        migrations.AddField(
            model_name="whatsappchannel",
            name="selected_voice_id",
            field=models.CharField(
                blank=True,
                help_text="ElevenLabs voice ID from the gallery (e.g. Layla, Rachel).",
                max_length=255,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="whatsappchannel",
            name="voice_preview_url",
            field=models.URLField(
                blank=True,
                help_text="Sample audio URL for the selected voice in the UI.",
                max_length=500,
                null=True,
            ),
        ),
    ]
