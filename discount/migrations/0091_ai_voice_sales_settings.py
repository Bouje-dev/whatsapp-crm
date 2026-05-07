# Generated manually for AI Voice & Sales Intelligence

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('discount', '0090_expand_activity_types'),
    ]

    operations = [
        migrations.AddField(
            model_name='whatsappchannel',
            name='ai_auto_reply',
            field=models.BooleanField(default=False, help_text='Full autopilot: AI replies when no flow matches'),
        ),
        migrations.AddField(
            model_name='whatsappchannel',
            name='ai_voice_enabled',
            field=models.BooleanField(default=False, help_text='Send AI replies as voice messages'),
        ),
        migrations.AddField(
            model_name='whatsappchannel',
            name='voice_provider',
            field=models.CharField(choices=[('OPENAI', 'OpenAI TTS'), ('ELEVENLABS', 'ElevenLabs')], default='OPENAI', max_length=20),
        ),
        migrations.AddField(
            model_name='whatsappchannel',
            name='voice_gender',
            field=models.CharField(choices=[('MALE', 'Male'), ('FEMALE', 'Female')], default='FEMALE', max_length=10),
        ),
        migrations.AddField(
            model_name='whatsappchannel',
            name='voice_delay_seconds',
            field=models.PositiveSmallIntegerField(default=20, help_text='Delay before sending voice (10-30 sec)'),
        ),
        migrations.AddField(
            model_name='whatsappchannel',
            name='ai_order_capture',
            field=models.BooleanField(default=True, help_text='Automatically extract and save orders from conversations'),
        ),
        migrations.AddField(
            model_name='whatsappchannel',
            name='elevenlabs_api_key',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='whatsappchannel',
            name='voice_cloning_enabled',
            field=models.BooleanField(default=False, help_text='Clone your voice (Premium only)'),
        ),
    ]
