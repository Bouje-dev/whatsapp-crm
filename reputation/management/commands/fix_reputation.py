"""
Recalculate ALL reputation profiles from Order table.
Usage: python manage.py fix_reputation
"""
from django.core.management.base import BaseCommand
from reputation.services import recalculate_all_reputations


class Command(BaseCommand):
    help = "Recalculate all GlobalCustomerProfile records from Order table"

    def handle(self, *args, **options):
        self.stdout.write("Recalculating all reputation profiles...")
        count = recalculate_all_reputations()
        self.stdout.write(self.style.SUCCESS(f"Done: {count} profiles processed."))
