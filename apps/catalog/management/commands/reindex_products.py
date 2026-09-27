from django.core.management.base import BaseCommand

from rag.indexer import build_index


class Command(BaseCommand):
    help = "Rebuild the FAISS semantic index from active products."

    def handle(self, *args, **options):
        count = build_index()
        self.stdout.write(self.style.SUCCESS(f"Indexed {count} product(s)."))
