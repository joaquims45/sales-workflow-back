import tempfile
from pathlib import Path

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Category, Product


class CatalogAPITests(APITestCase):
    def setUp(self):
        # create()/update() trigger a FAISS reindex — isolate from whatever
        # index exists on the developer's machine.
        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)
        override = self.settings(FAISS_INDEX_PATH=str(Path(tmp_dir.name) / "unused.bin"))
        override.enable()
        self.addCleanup(override.disable)

        self.category = Category.objects.create(name="Notebooks", slug="notebooks")
        self.active_product = Product.objects.create(
            category=self.category,
            name="ASUS TUF Gaming A15",
            slug="asus-tuf-gaming-a15",
            description="Notebook gamer.",
            features={"gpu": "RTX 4060", "ram_gb": 16},
            use_cases=["gaming", "programming"],
            semantic_tags=["gamer"],
            price="1400000.00",
            stock=5,
            is_active=True,
        )
        self.inactive_product = Product.objects.create(
            category=self.category,
            name="Modelo descontinuado",
            slug="modelo-descontinuado",
            description="No debe aparecer en la API pública.",
            price="1.00",
            stock=0,
            is_active=False,
        )

    def test_list_categories(self):
        url = reverse("category-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["slug"], "notebooks")

    def test_list_products_excludes_inactive(self):
        url = reverse("product-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        slugs = [item["slug"] for item in response.data]
        self.assertIn("asus-tuf-gaming-a15", slugs)
        self.assertNotIn("modelo-descontinuado", slugs)

    def test_retrieve_product_includes_nested_category(self):
        url = reverse("product-detail", args=[self.active_product.pk])
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["category"]["slug"], "notebooks")
        self.assertEqual(response.data["features"]["gpu"], "RTX 4060")

    def test_create_category_auto_generates_slug(self):
        url = reverse("category-list")
        response = self.client.post(url, {"name": "Monitores"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["slug"], "monitores")

    def test_create_product_with_category_id_and_auto_slug(self):
        url = reverse("product-list")
        payload = {
            "name": "Monitor LG UltraGear",
            "description": "Monitor gamer 27 pulgadas.",
            "category": self.category.id,
            "price": "380000.00",
            "stock": 12,
            "use_cases": ["gaming"],
        }

        response = self.client.post(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["slug"], "monitor-lg-ultragear")
        # Response shape matches list/retrieve (nested category), not the
        # plain id ProductWriteSerializer accepts as input.
        self.assertEqual(response.data["category"]["slug"], "notebooks")

        product = Product.objects.get(pk=response.data["id"])
        self.assertEqual(product.category, self.category)
        self.assertTrue(product.is_active)

    def test_create_product_with_duplicate_name_gets_disambiguated_slug(self):
        url = reverse("product-list")
        payload = {
            "name": "ASUS TUF Gaming A15",
            "description": "Otra unidad distinta con el mismo nombre.",
            "category": self.category.id,
            "price": "1400000.00",
            "stock": 2,
        }

        response = self.client.post(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertNotEqual(response.data["slug"], self.active_product.slug)
        self.assertEqual(response.data["slug"], "asus-tuf-gaming-a15-2")

    def test_create_product_requires_a_valid_category(self):
        url = reverse("product-list")
        payload = {"name": "Producto huérfano", "description": "x", "category": 9999, "price": "1.00"}

        response = self.client.post(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("category", response.data)

    def test_update_product(self):
        url = reverse("product-detail", args=[self.active_product.pk])

        response = self.client.patch(url, {"stock": 3}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["category"]["slug"], "notebooks")
        self.active_product.refresh_from_db()
        self.assertEqual(self.active_product.stock, 3)
