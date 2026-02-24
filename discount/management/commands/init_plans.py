"""
Initialize default Basic and Premium subscription plans.
Run: python manage.py init_plans
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from discount.models import Plan


class Command(BaseCommand):
    help = "Create default Basic and Premium plans with their feature flags."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Update existing plans with default values (otherwise skip if plan exists).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        force = options.get("force", False)
        defaults = [
            {
                "name": "Free",
                "can_use_ai_voice": False,
                "can_use_voice_cloning": False,
                "can_use_auto_reply": False,
                "can_use_advanced_tones": False,
                "can_use_cloning": False,
                "price": 0,
            },
            {
                "name": "Basic",
                "can_use_ai_voice": False,
                "can_use_voice_cloning": False,
                "can_use_auto_reply": False,
                "can_use_advanced_tones": False,
                "can_use_cloning": False,
                "price": 0,
            },
            {
                "name": "Premium",
                "can_use_ai_voice": True,
                "can_use_voice_cloning": True,
                "can_use_auto_reply": True,
                "can_use_advanced_tones": True,
                "can_use_cloning": True,
                "price": None,  # set your price or leave null
            },
        ]
        for d in defaults:
            plan, created = Plan.objects.update_or_create(
                name=d["name"],
                defaults={
                    "can_use_ai_voice": d["can_use_ai_voice"],
                    "can_use_voice_cloning": d["can_use_voice_cloning"],
                    "can_use_auto_reply": d["can_use_auto_reply"],
                    "can_use_advanced_tones": d.get("can_use_advanced_tones", False),
                    "can_use_cloning": d.get("can_use_cloning", False),
                    "price": d.get("price"),
                },
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f"Created plan: {plan.name}"))
            else:
                if force:
                    for k, v in d.items():
                        setattr(plan, k, v)
                    plan.save()
                    self.stdout.write(self.style.WARNING(f"Updated plan: {plan.name}"))
                else:
                    self.stdout.write(f"Plan already exists (skip): {plan.name}")

        self.stdout.write(self.style.SUCCESS("init_plans done. Assign users to a plan via CustomUser.plan_id."))
