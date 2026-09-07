from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("discount", "0179_channel_response_mode_auto"),
    ]

    operations = [
        migrations.AddField(
            model_name="whatsappcheckoutstate",
            name="force_voice_mode",
            field=models.BooleanField(
                db_index=True,
                default=False,
                help_text=(
                    "Accessibility: customer sent a voice note or asked for audio. "
                    "When Auto reply format is on, every subsequent AI reply is TTS."
                ),
            ),
        ),
    ]
