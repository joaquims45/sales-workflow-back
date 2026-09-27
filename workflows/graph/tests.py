import tempfile
from decimal import Decimal
from pathlib import Path

from django.test import SimpleTestCase, TestCase

from apps.catalog.models import Category, Product
from apps.conversations.models import Conversation
from apps.orders.models import Order
from apps.payments.models import Payment

from .extraction import extract_budget, extract_needs
from .orchestrator import run_replace, run_side_query
from .product_purchase import run_product_purchase
from .shipping_query import run_shipping_query
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
        # No FAISS index at this path -> search_products falls back to the
        # naive keyword-overlap filter, keeping these assertions independent
        # of whatever index happens to exist on the developer's machine.
        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)
        override = self.settings(FAISS_INDEX_PATH=str(Path(tmp_dir.name) / "unused.bin"))
        override.enable()
        self.addCleanup(override.disable)

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

    def test_purchases_the_only_candidate_when_intent_expressed(self):
        conversation = Conversation.objects.create()
        state = build_initial_state(conversation_id=conversation.id)
        state["candidate_products"] = [self.gaming_laptop.id]

        new_state, reply = run_product_purchase(state, "Quiero comprarla.")

        self.assertEqual(new_state["selected_product_id"], self.gaming_laptop.id)
        self.assertTrue(new_state["checkout_ready"])
        self.assertIn("Listo", reply)

        order = Order.objects.get()
        self.assertEqual(order.total, Decimal("1400000.00"))
        self.assertEqual(order.conversation_id, conversation.id)
        self.assertEqual(Payment.objects.get().status, Payment.Status.PENDING)

    def test_matches_candidate_by_name_among_several(self):
        conversation = Conversation.objects.create()
        office_laptop = Product.objects.create(
            category=self.gaming_laptop.category,
            name="Dell Inspiron 15",
            slug="dell-inspiron-15",
            description="Notebook de oficina.",
            use_cases=["office"],
            price="800000.00",
            stock=10,
        )
        state = build_initial_state(conversation_id=conversation.id)
        state["candidate_products"] = [self.gaming_laptop.id, office_laptop.id]

        new_state, reply = run_product_purchase(state, "Quiero comprar la ASUS.")

        self.assertEqual(new_state["selected_product_id"], self.gaming_laptop.id)
        self.assertTrue(new_state["checkout_ready"])
        self.assertIn("Listo", reply)

    def test_asks_which_product_when_ambiguous(self):
        conversation = Conversation.objects.create()
        office_laptop = Product.objects.create(
            category=self.gaming_laptop.category,
            name="Dell Inspiron 15",
            slug="dell-inspiron-15",
            description="Notebook de oficina.",
            use_cases=["office"],
            price="800000.00",
            stock=10,
        )
        state = build_initial_state(conversation_id=conversation.id)
        state["candidate_products"] = [self.gaming_laptop.id, office_laptop.id]

        new_state, reply = run_product_purchase(state, "Quiero comprarla.")

        self.assertIsNone(new_state["selected_product_id"])
        self.assertFalse(new_state["checkout_ready"])
        self.assertIn(self.gaming_laptop.name, reply)
        self.assertIn(office_laptop.name, reply)
        self.assertEqual(Order.objects.count(), 0)

    def test_reports_out_of_stock_product(self):
        conversation = Conversation.objects.create()
        self.gaming_laptop.stock = 0
        self.gaming_laptop.save()
        state = build_initial_state(conversation_id=conversation.id)
        state["candidate_products"] = [self.gaming_laptop.id]

        new_state, reply = run_product_purchase(state, "Quiero comprarla.")

        self.assertFalse(new_state["checkout_ready"])
        self.assertIn("stock", reply.lower())
        self.assertEqual(Order.objects.count(), 0)


class ShippingQueryGraphTests(SimpleTestCase):
    def test_quotes_a_serviceable_destination(self):
        reply = run_shipping_query("¿Hacen envíos a Santa Fe?")

        self.assertIn("Santa Fe", reply)
        self.assertIn("$12000", reply)

    def test_reports_unserviceable_destination(self):
        reply = run_shipping_query("¿Hacen envíos a la Antártida?")

        self.assertIn("¿A qué localidad", reply)

    def test_asks_for_destination_when_none_mentioned(self):
        reply = run_shipping_query("¿Hacen envíos?")

        self.assertIn("¿A qué localidad", reply)


class RunSideQueryTests(SimpleTestCase):
    def test_suspends_and_resumes_active_workflow(self):
        state = build_initial_state(conversation_id=1)
        state["active_workflow"] = "PRODUCT_PURCHASE"
        state["active_node"] = "PRODUCT_COMPARISON"

        new_state, reply = run_side_query(state, "¿Hacen envíos a Santa Fe?")

        self.assertIn("Santa Fe", reply)
        # Fully resumed: no trace of the interruption left in the final state.
        self.assertEqual(new_state["active_workflow"], "PRODUCT_PURCHASE")
        self.assertEqual(new_state["active_node"], "PRODUCT_COMPARISON")
        self.assertIsNone(new_state["suspended_workflow"])
        self.assertIsNone(new_state["suspended_node"])
        self.assertIsNone(new_state["interruption"])
        self.assertEqual(new_state["workflow_stack"], [])
        self.assertEqual(new_state["routing_decision"], "RESUME")

    def test_side_query_without_an_active_workflow_leaves_nothing_active(self):
        state = build_initial_state(conversation_id=1)

        new_state, _reply = run_side_query(state, "¿Hacen envíos a Santa Fe?")

        self.assertIsNone(new_state["active_workflow"])
        self.assertIsNone(new_state["active_node"])
        self.assertEqual(new_state["workflow_stack"], [])


class RunReplaceTests(TestCase):
    def setUp(self):
        # Same reasoning as ProductPurchaseGraphTests: isolate from whatever
        # FAISS index exists on the developer's machine.
        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)
        override = self.settings(FAISS_INDEX_PATH=str(Path(tmp_dir.name) / "unused.bin"))
        override.enable()
        self.addCleanup(override.disable)

        Category.objects.create(name="Monitores", slug="monitores")

    def test_replace_clears_previous_goal_and_starts_fresh(self):
        state = build_initial_state(conversation_id=1)
        state["primary_goal"] = "BUY_PRODUCT"
        state["active_workflow"] = "PRODUCT_PURCHASE"
        state["active_node"] = "PRODUCT_COMPARISON"
        state["customer_needs"] = ["gaming", "programming"]
        state["constraints"] = {"budget_max": 1500000}
        state["candidate_products"] = [1, 2, 3]
        state["routing_confidence"] = 0.7

        new_state, reply = run_replace(state, "Olvidate de la notebook. Quiero buscar un monitor.")

        self.assertEqual(new_state["routing_decision"], "REPLACE")
        self.assertEqual(new_state["routing_confidence"], 0.7)
        self.assertEqual(new_state["candidate_products"], [])
        self.assertEqual(new_state["constraints"], {})
        # The new message re-enters DISCOVERY like any fresh conversation.
        self.assertEqual(new_state["primary_goal"], "BUY_PRODUCT")
        self.assertEqual(new_state["active_workflow"], "PRODUCT_PURCHASE")
        self.assertTrue(reply)
