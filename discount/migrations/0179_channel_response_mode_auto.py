from django.db import migrations, models


def forwards_seed_channel_response_mode(apps, schema_editor):
    WhatsAppChannel = apps.get_model("discount", "WhatsAppChannel")
    WhatsAppChannel.objects.filter(ai_voice_enabled=True).update(response_mode="voice_enabled")
    WhatsAppChannel.objects.filter(ai_voice_enabled=False).update(response_mode="text_only")


def backwards_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("discount", "0178_knowledge_gap_waiting_magic"),
    ]

    operations = [
        migrations.AddField(
            model_name="whatsappchannel",
            name="response_mode",
            field=models.CharField(
                blank=True,
                choices=[
                    ("text_only", "Text only"),
                    ("voice_enabled", "Voice enabled"),
                    ("auto", "Auto (AI chooses text or voice)"),
                ],
                default="text_only",
                help_text="Store reply delivery: text_only, voice_enabled, or auto (LLM chooses per turn).",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="node",
            name="response_mode",
            field=models.CharField(
                blank=True,
                choices=[
                    ("TEXT_ONLY", "Text only"),
                    ("AUDIO_ONLY", "Audio only"),
                    ("AUTO_SMART", "Auto (AI chooses text or voice)"),
                    ("AUTO", "Auto (AI chooses text or voice)"),
                ],
                default="TEXT_ONLY",
                help_text="TEXT_ONLY, AUDIO_ONLY, AUTO, or AUTO_SMART",
                max_length=20,
            ),
        ),
        migrations.RunPython(forwards_seed_channel_response_mode, backwards_noop),
    ]
