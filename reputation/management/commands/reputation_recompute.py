"""
Alias for fix_reputation. Recalculate all profiles from Order table.
Usage: python manage.py reputation_recompute
"""
from django.core.management.base import BaseCommand
from reputation.services import recalculate_all_reputations


class Command(BaseCommand):
    help = "Recompute all reputation profiles from Order table (source of truth)."

    def handle(self, *args, **options):
        self.stdout.write("Recomputing all reputation profiles...")
        count = recalculate_all_reputations()
        self.stdout.write(self.style.SUCCESS(f"Done: {count} profiles processed."))
