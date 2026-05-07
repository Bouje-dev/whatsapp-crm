from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("discount", "0132_voice_gallery_language_code"),
    ]

    operations = [
        migrations.CreateModel(
            name="VoiceCloneRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("audio_file", models.FileField(upload_to="voice_clone_requests/%Y/%m/")),
                ("consent_agreed", models.BooleanField(default=False)),
                (
                    "status",
                    models.CharField(
                        choices=[("pending", "Pending"), ("approved", "Approved"), ("rejected", "Rejected")],
                        db_index=True,
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "merchant",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="voice_clone_requests",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Voice clone request",
                "verbose_name_plural": "Voice clone requests",
                "ordering": ["-created_at"],
            },
        ),
    ]

