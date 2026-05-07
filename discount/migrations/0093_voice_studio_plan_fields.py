# Advanced AI Voice Studio & Plan fields

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("discount", "0092_plan_and_customuser_plan"),
    ]

    operations = [
        migrations.AddField(
            model_name="plan",
            name="can_use_cloning",
            field=models.BooleanField(default=False, help_text="Alias for voice cloning capability"),
        ),
        migrations.AddField(
            model_name="plan",
            name="can_use_advanced_tones",
            field=models.BooleanField(default=False, help_text="Stability & similarity sliders (PRO)"),
        ),
        migrations.AddField(
            model_name="plan",
            name="max_monthly_orders",
            field=models.PositiveIntegerField(blank=True, help_text="Cap on auto-created orders per month; null = unlimited", null=True),
        ),
        migrations.AddField(
            model_name="whatsappchannel",
            name="voice_language",
            field=models.CharField(choices=[("AUTO", "Auto-Detect"), ("AR_MA", "Arabic (Morocco)"), ("AR_SA", "Arabic (Saudi)"), ("FR_FR", "French (France)"), ("EN_US", "English (US)")], default="AUTO", max_length=10),
        ),
        migrations.AddField(
            model_name="whatsappchannel",
            name="voice_stability",
            field=models.FloatField(default=0.5, help_text="0.0-1.0 Emotion/Stability"),
        ),
        migrations.AddField(
            model_name="whatsappchannel",
            name="voice_similarity",
            field=models.FloatField(default=0.75, help_text="0.0-1.0 Similarity/Clarity"),
        ),
        migrations.AddField(
            model_name="whatsappchannel",
            name="cloned_voice_id",
            field=models.CharField(blank=True, help_text="ElevenLabs cloned voice ID", max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="whatsappchannel",
            name="ai_voice_provider",
            field=models.CharField(choices=[("OPENAI", "OpenAI TTS"), ("ELEVENLABS", "ElevenLabs")], default="OPENAI", max_length=20),
        ),
    ]
