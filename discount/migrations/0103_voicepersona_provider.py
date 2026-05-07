# Add provider (ELEVENLABS / OPENAI) to VoicePersona

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('discount', '0102_voice_persona_and_node_persona'),
    ]

    operations = [
        migrations.AddField(
            model_name='voicepersona',
            name='provider',
            field=models.CharField(
                choices=[('ELEVENLABS', 'ElevenLabs'), ('OPENAI', 'OpenAI')],
                default='ELEVENLABS',
                help_text='TTS provider for this voice',
                max_length=20,
            ),
        ),
    ]
