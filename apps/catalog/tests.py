from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Category, Product


class CatalogAPITests(APITestCase):
    def setUp(self):
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
