from django.test import SimpleTestCase, TestCase

from apps.catalog.models import Category, Product

from .extraction import extract_budget, extract_needs
from .product_purchase import run_product_purchase
from .state import FunnelStage, build_initial_state


class SalesStateTests(SimpleTestCase):
    def test_initial_state_shape(self):
        state = build_initial_state(conversation_id=1)

        self.assertEqual(state["conversation_id"], 1)
        self.assertEqual(state["funnel_stage"], FunnelStage.DISCOVERY)
        self.assertIsNone(state["primary_goal"])
        self.assertEqual(state["customer_needs"], [])
        self.assertEqual(state["workflow_stack"], [])


class ExtractionTests(SimpleTestCase):
    def test_extract_needs_detects_gaming_and_programming(self):
        needs = extract_needs("Busco una notebook para programar y jugar.")

        self.assertIn("gaming", needs)
        self.assertIn("programming", needs)

    def test_extract_budget_parses_formatted_number(self):
        self.assertEqual(extract_budget("Tengo hasta $1.500.000."), 1500000)

    def test_extract_budget_returns_none_when_absent(self):
        self.assertIsNone(extract_budget("¿Cuál tiene mejor GPU?"))


class ProductPurchaseGraphTests(TestCase):
    def setUp(self):
        category = Category.objects.create(name="Notebooks", slug="notebooks")
        self.gaming_laptop = Product.objects.create(
            category=category,
            name="ASUS TUF Gaming A15",
            slug="asus-tuf-gaming-a15",
            description="Notebook gamer.",
            use_cases=["gaming", "programming"],
            price="1400000.00",
            stock=5,
        )
        Product.objects.create(
            category=category,
            name="Notebook de oficina",
            slug="notebook-oficina",
            description="Sin GPU dedicada.",
            use_cases=["office"],
            price="800000.00",
            stock=10,
        )

    def test_asks_for_budget_when_missing(self):
        state = build_initial_state(conversation_id=1)

        new_state, reply = run_product_purchase(state, "Busco una notebook para programar y jugar.")

        self.assertEqual(new_state["primary_goal"], "BUY_PRODUCT")
        self.assertIn("gaming", new_state["customer_needs"])
        self.assertEqual(new_state["candidate_products"], [])
        self.assertIn("presupuesto", reply.lower())

    def test_recommends_matching_products_once_budget_known(self):
        state = build_initial_state(conversation_id=1)
        state["customer_needs"] = ["gaming", "programming"]

        new_state, reply = run_product_purchase(state, "Tengo hasta $1.500.000.")

        self.assertEqual(new_state["constraints"]["budget_max"], 1500000)
        self.assertIn(self.gaming_laptop.id, new_state["candidate_products"])
        self.assertIn(self.gaming_laptop.name, reply)

    def test_no_candidates_returns_helpful_reply(self):
        state = build_initial_state(conversation_id=1)
        state["customer_needs"] = ["gaming", "programming"]

        new_state, reply = run_product_purchase(state, "Tengo hasta $100.000.")

        self.assertEqual(new_state["candidate_products"], [])
        self.assertIn("No encontré", reply)
