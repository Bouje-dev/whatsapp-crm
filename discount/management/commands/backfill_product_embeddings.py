"""
Backfill OpenAI embeddings for catalog products that have none yet.

Usage: python manage.py backfill_product_embeddings
"""
from django.core.management.base import BaseCommand

from discount.models import Products
from ai_assistant.embeddings import refresh_product_embedding


class Command(BaseCommand):
    help = "Generate text-embedding-3-small vectors for products missing an embedding."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Max products to process (0 = all).",
        )

    def handle(self, *args, **options):
        qs = Products.objects.filter(embedding__isnull=True).order_by("id")
        limit = int(options.get("limit") or 0)
        if limit > 0:
            qs = qs[:limit]
        total = qs.count()
        ok = 0
        failed = 0
        self.stdout.write(f"Embedding {total} product(s)…")
        for product in qs.iterator():
            if refresh_product_embedding(product.id):
                ok += 1
            else:
                failed += 1
                self.stderr.write(f"Failed product_id={product.id} ({product.name})")
        self.stdout.write(self.style.SUCCESS(f"Done. ok={ok} failed={failed}"))
