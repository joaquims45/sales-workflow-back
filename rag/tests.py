import tempfile
from io import StringIO
from pathlib import Path

import faiss
from django.core.management import call_command
from django.test import TestCase

from apps.catalog.models import Category, Product

from .indexer import build_index, build_product_text


class RagIndexerTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Notebooks", slug="notebooks")
        self.product = Product.objects.create(
            category=self.category,
            name="ASUS TUF Gaming A15",
            slug="asus-tuf-gaming-a15",
            description="Notebook gamer para programar y jugar.",
            features={"gpu": "RTX 4060"},
            use_cases=["gaming", "programming"],
            semantic_tags=["gamer"],
            price="1400000.00",
            stock=5,
        )
        Product.objects.create(
            category=self.category,
            name="Modelo descontinuado",
            slug="modelo-descontinuado",
            description="No debe indexarse.",
            price="1.00",
            stock=0,
            is_active=False,
        )

        self._tmp_dir = tempfile.TemporaryDirectory()
        self.index_path = Path(self._tmp_dir.name) / "faiss_index.bin"
        self.addCleanup(self._tmp_dir.cleanup)
        self._override = self.settings(FAISS_INDEX_PATH=str(self.index_path))
        self._override.enable()
        self.addCleanup(self._override.disable)

    def test_build_product_text_includes_all_indexed_fields(self):
        text = build_product_text(self.product)

        self.assertIn("ASUS TUF Gaming A15", text)
        self.assertIn("Notebooks", text)
        self.assertIn("RTX 4060", text)
        self.assertIn("gaming", text)
        self.assertIn("gamer", text)

    def test_build_index_only_includes_active_products(self):
        count = build_index()

        self.assertEqual(count, 1)
        self.assertTrue(self.index_path.exists())

        index = faiss.read_index(str(self.index_path))
        self.assertEqual(index.ntotal, 1)

    def test_reindex_products_command_reports_count(self):
        out = StringIO()
        call_command("reindex_products", stdout=out)

        self.assertIn("Indexed 1 product(s).", out.getvalue())
