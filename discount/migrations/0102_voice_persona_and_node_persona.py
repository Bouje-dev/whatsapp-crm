# VoicePersona model + Node persona/voice fields + Plan.can_use_persona_gallery

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('discount', '0101_rename_discount_ai_channel_6b8c2a_idx_discount_ai_channel_91b405_idx_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='plan',
            name='can_use_persona_gallery',
            field=models.BooleanField(default=False, help_text='High-quality & cloned personas in Flow Builder'),
        ),
        migrations.CreateModel(
            name='VoicePersona',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(help_text='e.g. Laila, Sami, Hiba - Luxury Consultant', max_length=120)),
                ('description', models.CharField(blank=True, help_text='e.g. Soft, calm, perfect for cosmetics', max_length=255)),
                ('voice_id', models.CharField(help_text='ElevenLabs Voice ID', max_length=120)),
                ('is_system', models.BooleanField(default=True, help_text='System-wide persona vs user-cloned')),
                ('behavioral_instructions', models.TextField(blank=True, help_text='e.g. Use high-end vocabulary, be extremely polite, use specific emojis.')),
                ('language_code', models.CharField(default='AR_MA', help_text='AR_MA, FR_FR, EN_US, etc.', max_length=20)),
                ('tier', models.CharField(choices=[('standard', 'Standard'), ('premium', 'Premium')], default='standard', help_text='For system personas: standard=free, premium=paid only', max_length=20)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('owner', models.ForeignKey(blank=True, help_text='Set for user-cloned voices; null for system personas', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='cloned_voice_personas', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Voice Persona',
                'verbose_name_plural': 'Voice Personas',
                'ordering': ['-is_system', 'name'],
            },
        ),
        migrations.AddField(
            model_name='node',
            name='persona',
            field=models.ForeignKey(blank=True, help_text='Sales agent persona (voice + behavior); overrides node_voice_id when set', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='nodes', to='discount.voicepersona'),
        ),
        migrations.AddField(
            model_name='node',
            name='voice_speed',
            field=models.FloatField(blank=True, help_text='0.5–1.5 for ElevenLabs', null=True),
        ),
        migrations.AddField(
            model_name='node',
            name='voice_similarity',
            field=models.FloatField(blank=True, help_text='0.0–1.0 for ElevenLabs', null=True),
        ),
        migrations.AddField(
            model_name='node',
            name='voice_stability',
            field=models.FloatField(blank=True, help_text='0.0–1.0 for ElevenLabs', null=True),
        ),
    ]
