import tempfile
from pathlib import Path

from django.test import TestCase

from apps.catalog.models import Category, Product
from rag.indexer import build_index

from .product_tools import ProductConstraints, search_products


class SearchProductsTests(TestCase):
    def setUp(self):
        category = Category.objects.create(name="Notebooks", slug="notebooks")
        self.gaming_laptop = Product.objects.create(
            category=category,
            name="ASUS TUF Gaming A15",
            slug="asus-tuf-gaming-a15",
            description="Notebook gamer para programar y jugar con RTX 4060.",
            use_cases=["gaming", "programming"],
            semantic_tags=["gamer"],
            price="1400000.00",
            stock=5,
        )
        self.office_laptop = Product.objects.create(
            category=category,
            name="Dell Inspiron 15",
            slug="dell-inspiron-15",
            description="Notebook liviana para oficina, sin GPU dedicada.",
            use_cases=["office"],
            price="900000.00",
            stock=10,
        )

        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)
        self.index_path = Path(tmp_dir.name) / "faiss_index.bin"
        override = self.settings(FAISS_INDEX_PATH=str(self.index_path))
        override.enable()
        self.addCleanup(override.disable)

    def test_falls_back_to_keyword_overlap_when_no_index_exists(self):
        constraints = ProductConstraints(needs=["gaming"])

        candidates = search_products("notebook gamer", constraints)

        ids = [candidate.id for candidate in candidates]
        self.assertIn(self.gaming_laptop.id, ids)
        self.assertNotIn(self.office_laptop.id, ids)

    def test_uses_semantic_index_when_available(self):
        build_index()

        constraints = ProductConstraints()
        candidates = search_products("notebook para programar y jugar", constraints)

        ids = [candidate.id for candidate in candidates]
        self.assertIn(self.gaming_laptop.id, ids)

    def test_still_enforces_budget_from_postgres(self):
        build_index()

        constraints = ProductConstraints(budget_max=100000)
        candidates = search_products("notebook gamer", constraints)

        self.assertEqual(candidates, [])
