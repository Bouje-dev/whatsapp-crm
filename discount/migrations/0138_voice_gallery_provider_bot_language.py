# Generated manually: VoiceGalleryEntry.provider, WhatsAppChannel.bot_language, seed OpenAI TTS voices.

from django.db import migrations, models


def seed_openai_gallery_voices(apps, schema_editor):
    VoiceGalleryEntry = apps.get_model("discount", "VoiceGalleryEntry")
    rows = [
        {
            "elevenlabs_voice_id": "alloy",
            "name": "Alloy",
            "label": "OpenAI — Alloy",
            "gender": "MALE",
            "tags": ["Multilingual", "OpenAI"],
            "language_code": "MULTILINGUAL",
            "dialect": "OTHER",
            "native_arabic": False,
            "sort_order": 200,
        },
        {
            "elevenlabs_voice_id": "echo",
            "name": "Echo",
            "label": "OpenAI — Echo",
            "gender": "MALE",
            "tags": ["Multilingual", "OpenAI"],
            "language_code": "MULTILINGUAL",
            "dialect": "OTHER",
            "native_arabic": False,
            "sort_order": 201,
        },
        {
            "elevenlabs_voice_id": "fable",
            "name": "Fable",
            "label": "OpenAI — Fable",
            "gender": "MALE",
            "tags": ["Multilingual", "OpenAI"],
            "language_code": "MULTILINGUAL",
            "dialect": "OTHER",
            "native_arabic": False,
            "sort_order": 202,
        },
        {
            "elevenlabs_voice_id": "onyx",
            "name": "Onyx",
            "label": "OpenAI — Onyx",
            "gender": "MALE",
            "tags": ["Multilingual", "OpenAI"],
            "language_code": "MULTILINGUAL",
            "dialect": "OTHER",
            "native_arabic": False,
            "sort_order": 203,
        },
        {
            "elevenlabs_voice_id": "nova",
            "name": "Nova",
            "label": "OpenAI — Nova",
            "gender": "FEMALE",
            "tags": ["Multilingual", "OpenAI"],
            "language_code": "MULTILINGUAL",
            "dialect": "OTHER",
            "native_arabic": False,
            "sort_order": 204,
        },
        {
            "elevenlabs_voice_id": "shimmer",
            "name": "Shimmer",
            "label": "OpenAI — Shimmer",
            "gender": "FEMALE",
            "tags": ["Multilingual", "OpenAI"],
            "language_code": "MULTILINGUAL",
            "dialect": "OTHER",
            "native_arabic": False,
            "sort_order": 205,
        },
    ]
    for row in rows:
        vid = row.pop("elevenlabs_voice_id")
        VoiceGalleryEntry.objects.update_or_create(
            elevenlabs_voice_id=vid,
            defaults={
                "provider": "OPENAI",
                "is_active": True,
                **row,
            },
        )


def unseed_openai_gallery_voices(apps, schema_editor):
    VoiceGalleryEntry = apps.get_model("discount", "VoiceGalleryEntry")
    VoiceGalleryEntry.objects.filter(provider="OPENAI", elevenlabs_voice_id__in=[
        "alloy", "echo", "fable", "onyx", "nova", "shimmer",
    ]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("discount", "0137_template_header_document"),
    ]

    operations = [
        migrations.AddField(
            model_name="whatsappchannel",
            name="bot_language",
            field=models.CharField(
                choices=[
                    ("auto", "Auto (derive from Voice language)"),
                    ("ar", "Arabic — align with TTS / dialect"),
                    ("fr", "French — formal corporate (overrides Arabic voice dialect for LLM)"),
                    ("en", "English"),
                ],
                default="auto",
                help_text="Primary language for AI agent replies. French forces formal French and ignores Arabic dialect prompts from the voice gallery.",
                max_length=8,
            ),
        ),
        migrations.AddField(
            model_name="voicegalleryentry",
            name="provider",
            field=models.CharField(
                choices=[("ELEVENLABS", "ElevenLabs"), ("OPENAI", "OpenAI")],
                default="ELEVENLABS",
                help_text="TTS backend: ElevenLabs API or OpenAI audio.speech (tts-1).",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="voicegalleryentry",
            name="elevenlabs_voice_id",
            field=models.CharField(
                help_text="ElevenLabs voice_id, or OpenAI voice name (alloy, echo, fable, onyx, nova, shimmer) when provider is OpenAI.",
                max_length=64,
                unique=True,
            ),
        ),
        migrations.RunPython(seed_openai_gallery_voices, unseed_openai_gallery_voices),
    ]
