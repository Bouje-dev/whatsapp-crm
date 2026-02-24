# Node: response_mode, node_voice_id, node_language, node_gender; NodeMedia model for AI Agent media gallery

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("discount", "0096_node_ai_agent_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="node",
            name="response_mode",
            field=models.CharField(
                blank=True,
                choices=[
                    ("TEXT_ONLY", "Text only"),
                    ("AUDIO_ONLY", "Audio only"),
                    ("AUTO_SMART", "Auto (text for short, audio for pitch/closing)"),
                ],
                default="TEXT_ONLY",
                help_text="TEXT_ONLY, AUDIO_ONLY, or AUTO_SMART",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="node",
            name="node_voice_id",
            field=models.CharField(blank=True, help_text="Voice ID for this node (e.g. ElevenLabs)", max_length=100, null=True),
        ),
        migrations.AddField(
            model_name="node",
            name="node_language",
            field=models.CharField(blank=True, help_text="e.g. AR_MA, FR_FR, EN_US", max_length=20, null=True),
        ),
        migrations.AddField(
            model_name="node",
            name="node_gender",
            field=models.CharField(blank=True, help_text="FEMALE or MALE", max_length=10, null=True),
        ),
        migrations.CreateModel(
            name="NodeMedia",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("file", models.FileField(blank=True, max_length=500, null=True, upload_to="flow_node_media/%Y/%m/")),
                ("file_type", models.CharField(choices=[("Image", "Image"), ("Video", "Video")], default="Image", max_length=10)),
                ("description", models.CharField(blank=True, help_text="Label for GPT, e.g. Product Close-up", max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("node", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="media_assets", to="discount.node")),
            ],
            options={
                "ordering": ["created_at"],
                "verbose_name": "Node media",
                "verbose_name_plural": "Node media",
            },
        ),
    ]
