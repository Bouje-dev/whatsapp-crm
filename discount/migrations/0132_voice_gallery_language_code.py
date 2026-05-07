from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("discount", "0131_voice_gallery_preview_file"),
    ]

    operations = [
        migrations.AddField(
            model_name="voicegalleryentry",
            name="language_code",
            field=models.CharField(
                blank=True,
                db_index=True,
                default="",
                help_text="Primary locale for filtering, e.g. AR_MA, FR_FR, EN_US (use underscore). "
                "Leave empty for multilingual / any language.",
                max_length=32,
            ),
        ),
    ]
