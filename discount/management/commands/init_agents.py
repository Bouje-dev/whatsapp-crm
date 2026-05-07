"""
Populate VoicePersona with initial sales agent personas.
Run: python manage.py init_agents
Uses get_or_create to avoid duplicates (key: name + system persona).
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from discount.models import VoicePersona


AGENTS_DATA = [
    # ElevenLabs agents
    {
        "name": "ليلى - مستشارة مبيعات",
        "voice_id": "EXAVITQu4vr4xnSDxMaL",
        "provider": VoicePersona.PROVIDER_ELEVENLABS,
        "language_code": "AR_MA",
        "description": "بائعة محترفة، هادئة، لغة بيضاء.",
        "behavioral_instructions": "بائعة محترفة، هادئة، لغة بيضاء.",
    },
    {
        "name": "ياسين - بائع حماسي",
        "voice_id": "VR6AewrST9dh6vM97NBe",
        "provider": VoicePersona.PROVIDER_ELEVENLABS,
        "language_code": "AR_MA",
        "description": "بائع تقني، سريع، يركز على العروض المحدودة.",
        "behavioral_instructions": "بائع تقني، سريع، يركز على العروض المحدودة.",
    },
    {
        "name": "نور - خدمة عملاء",
        "voice_id": "shimmer",
        "provider": VoicePersona.PROVIDER_ELEVENLABS,
        "language_code": "AR_SA",
        "description": "ودودة، صبورة، تستخدم الإيموجي.",
        "behavioral_instructions": "ودودة، صبورة، تستخدم الإيموجي.",
    },
    {
        "name": "سامي - الخبير الفخم",
        "voice_id": "ErXwS2Rj9s637OAdmCBy",
        "provider": VoicePersona.PROVIDER_ELEVENLABS,
        "language_code": "AR_MA",
        "description": "رسمي، رصين، يعطي شعوراً بالأمان والجودة.",
        "behavioral_instructions": "رسمي، رصين، يعطي شعوراً بالأمان والجودة.",
    },
    # Economic Agents (OpenAI TTS – cheaper, fast)
    {
        "name": "نور (اقتصادي)",
        "voice_id": "shimmer",
        "provider": VoicePersona.PROVIDER_OPENAI,
        "language_code": "AR_SA",
        "description": "صوت أنثوي ناعم واقتصادي، ممتاز لخدمة العملاء.",
        "behavioral_instructions": "صوت أنثوي ناعم واقتصادي، ممتاز لخدمة العملاء.",
    },
    {
        "name": "عمر (اقتصادي)",
        "voice_id": "alloy",
        "provider": VoicePersona.PROVIDER_OPENAI,
        "language_code": "AR_MA",
        "description": "صوت رجالي متزن، مثالي للردود السريعة وتأكيد الطلبات.",
        "behavioral_instructions": "صوت رجالي متزن، مثالي للردود السريعة وتأكيد الطلبات.",
    },
    {
        "name": "ريم (اقتصادي)",
        "voice_id": "nova",
        "provider": VoicePersona.PROVIDER_OPENAI,
        "language_code": "AR_MA",
        "description": "نبرة أنثوية حيوية، رائعة للعروض الترويجية.",
        "behavioral_instructions": "نبرة أنثوية حيوية، رائعة للعروض الترويجية.",
    },
    {
        "name": "خالد (اقتصادي)",
        "voice_id": "onyx",
        "provider": VoicePersona.PROVIDER_OPENAI,
        "language_code": "AR_MA",
        "description": "صوت رجالي فخم وعميق للمنتجات الموثوقة.",
        "behavioral_instructions": "صوت رجالي فخم وعميق للمنتجات الموثوقة.",
    },
]


class Command(BaseCommand):
    help = "Create initial VoicePersona (sales agent) entries; skips duplicates via get_or_create."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Update existing personas with the same name (overwrite voice_id, instructions, etc.).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        force = options.get("force", False)
        created_count = 0
        updated_count = 0

        for data in AGENTS_DATA:
            lookup = {
                "name": data["name"],
                "is_system": True,
                "owner": None,
            }
            defaults = {
                "voice_id": data["voice_id"],
                "provider": data.get("provider", VoicePersona.PROVIDER_ELEVENLABS),
                "language_code": data["language_code"],
                "description": data.get("description", ""),
                "behavioral_instructions": data.get("behavioral_instructions", ""),
                "tier": VoicePersona.TIER_STANDARD,
            }
            persona, created = VoicePersona.objects.get_or_create(
                **lookup,
                defaults=defaults,
            )
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f"Created: {persona.name}"))
            else:
                if force:
                    for key, value in defaults.items():
                        setattr(persona, key, value)
                    persona.save()
                    updated_count += 1
                    self.stdout.write(self.style.WARNING(f"Updated: {persona.name}"))
                else:
                    self.stdout.write(f"Already exists (skip): {persona.name}")

        self.stdout.write(
            self.style.SUCCESS(
                f"init_agents done. Created {created_count}, updated {updated_count}."
            )
        )
