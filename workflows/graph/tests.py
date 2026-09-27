import tempfile
from decimal import Decimal
from pathlib import Path
from unittest import mock

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

    def test_explicit_budget_unknown_searches_instead_of_asking_again(self):
        # Regression: without this, a customer who says "no sé" gets the
        # exact same "¿qué presupuesto tenés?" forever.
        state = build_initial_state(conversation_id=1)
        state["customer_needs"] = ["gaming", "programming"]

        fake_provider = mock.Mock()
        fake_provider.extract.return_value = {
            "needs": ["gaming"],
            "budget_max": None,
            "budget_unknown": True,
            "wants_to_buy": False,
        }

        with mock.patch(
            "workflows.graph.product_purchase.get_discovery_extraction_provider",
            return_value=fake_provider,
        ):
            new_state, reply = run_product_purchase(state, "No sé, busco alguna placa de video.")

        self.assertIsNone(new_state["constraints"].get("budget_max"))
        self.assertNotIn("presupuesto", reply.lower())
        self.assertIn(self.gaming_laptop.id, new_state["candidate_products"])

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

    def test_purchase_intent_without_keywords_uses_extraction_provider(self):
        # Regression: "Me interesa la lenovo" / "Si, la lenovo" don't match
        # PURCHASE_INTENT_KEYWORDS (comprar/la compro/...), so without the
        # extraction provider's wants_to_buy this fell through to
        # product_search, re-running the search and drifting the candidate
        # list turn after turn instead of ever reaching checkout.
        conversation = Conversation.objects.create()
        state = build_initial_state(conversation_id=conversation.id)
        state["candidate_products"] = [self.gaming_laptop.id]

        fake_provider = mock.Mock()
        fake_provider.extract.return_value = {
            "needs": [],
            "budget_max": None,
            "budget_unknown": False,
            "wants_to_buy": True,
        }

        with mock.patch(
            "workflows.graph.product_purchase.get_discovery_extraction_provider",
            return_value=fake_provider,
        ):
            new_state, reply = run_product_purchase(state, "Me interesa la ASUS.")

        self.assertEqual(new_state["selected_product_id"], self.gaming_laptop.id)
        self.assertTrue(new_state["checkout_ready"])
        self.assertIn("Listo", reply)

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

    def test_emits_node_started_and_completed_for_each_node_visited(self):
        conversation = Conversation.objects.create()
        state = build_initial_state(conversation_id=conversation.id)

        run_product_purchase(state, "Busco una notebook para programar y jugar.")

        events = list(conversation.events.order_by("created_at").values_list("event_type", "payload"))
        started_nodes = [payload["node"] for event_type, payload in events if event_type == "node.started"]
        completed = [
            (payload["node"], payload["duration_ms"]) for event_type, payload in events if event_type == "node.completed"
        ]

        # Only DISCOVERY runs this turn (no budget yet -> ends at ASK_FOR_BUDGET).
        self.assertEqual(started_nodes, ["DISCOVERY", "ASK_FOR_BUDGET"])
        self.assertEqual([node for node, _duration in completed], ["DISCOVERY", "ASK_FOR_BUDGET"])
        for _node, duration_ms in completed:
            self.assertIsInstance(duration_ms, float)
            self.assertGreaterEqual(duration_ms, 0)

    def test_does_not_emit_events_for_an_unknown_conversation(self):
        # conversation_id=1 with no matching row — instrumentation should
        # skip silently rather than raise.
        state = build_initial_state(conversation_id=999999)

        new_state, reply = run_product_purchase(state, "hola")

        self.assertTrue(reply)
        self.assertEqual(new_state["active_workflow"], "PRODUCT_PURCHASE")


class ShippingQueryGraphTests(SimpleTestCase):
    def test_quotes_a_serviceable_destination(self):
        reply, resolved = run_shipping_query("¿Hacen envíos a Santa Fe?")

        self.assertIn("Santa Fe", reply)
        self.assertIn("$12000", reply)
        self.assertTrue(resolved)

    def test_unrecognized_destination_asks_again_and_is_not_resolved(self):
        reply, resolved = run_shipping_query("¿Hacen envíos a la Antártida?")

        self.assertIn("¿A qué localidad", reply)
        self.assertFalse(resolved)

    def test_asks_for_destination_when_none_mentioned(self):
        reply, resolved = run_shipping_query("¿Hacen envíos?")

        self.assertIn("¿A qué localidad", reply)
        self.assertFalse(resolved)


class RunSideQueryTests(TestCase):
    # TestCase, not SimpleTestCase: run_side_query now looks up the
    # Conversation to emit node.started/completed (workflows/graph/
    # orchestrator.py), which needs real DB access.
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

    def test_missing_destination_stays_suspended_for_a_follow_up(self):
        # Regression: "¿Hacen envíos?" (no destination) used to resume
        # immediately, so the next message (the actual destination) was
        # routed from scratch instead of answering the pending question.
        state = build_initial_state(conversation_id=1)
        state["active_workflow"] = "PRODUCT_PURCHASE"
        state["active_node"] = "RECOMMENDATION"

        state, reply = run_side_query(state, "¿Hacen envíos?")

        self.assertIn("¿A qué localidad", reply)
        self.assertEqual(state["interruption"], "SHIPPING_QUERY")
        self.assertEqual(state["active_workflow"], "SHIPPING_QUERY")
        self.assertEqual(state["suspended_workflow"], "PRODUCT_PURCHASE")
        self.assertEqual(state["suspended_node"], "RECOMMENDATION")
        self.assertEqual(len(state["workflow_stack"]), 1)

        # The follow-up answers the pending question — same call, doesn't
        # push a second frame, and now actually resumes.
        new_state, second_reply = run_side_query(state, "Santa Fe")

        self.assertIn("Santa Fe", second_reply)
        self.assertIsNone(new_state["interruption"])
        self.assertEqual(new_state["active_workflow"], "PRODUCT_PURCHASE")
        self.assertEqual(new_state["active_node"], "RECOMMENDATION")
        self.assertEqual(new_state["workflow_stack"], [])

    def test_emits_one_started_and_completed_pair_when_resolved_in_one_turn(self):
        conversation = Conversation.objects.create()
        state = build_initial_state(conversation_id=conversation.id)
        state["active_workflow"] = "PRODUCT_PURCHASE"
        state["active_node"] = "RECOMMENDATION"

        run_side_query(state, "¿Hacen envíos a Santa Fe?")

        event_types = list(conversation.events.order_by("created_at").values_list("event_type", flat=True))
        self.assertEqual(event_types.count("node.started"), 1)
        self.assertEqual(event_types.count("node.completed"), 1)

    def test_does_not_emit_completed_while_still_waiting_for_destination(self):
        conversation = Conversation.objects.create()
        state = build_initial_state(conversation_id=conversation.id)
        state["active_workflow"] = "PRODUCT_PURCHASE"
        state["active_node"] = "RECOMMENDATION"

        state, _reply = run_side_query(state, "¿Hacen envíos?")

        event_types = list(conversation.events.order_by("created_at").values_list("event_type", flat=True))
        self.assertEqual(event_types.count("node.started"), 1)
        self.assertEqual(event_types.count("node.completed"), 0)

        # Follow-up resolves it — completes, and does NOT re-emit started.
        run_side_query(state, "Santa Fe")

        event_types = list(conversation.events.order_by("created_at").values_list("event_type", flat=True))
        self.assertEqual(event_types.count("node.started"), 1)
        self.assertEqual(event_types.count("node.completed"), 1)


class RunReplaceTests(TestCase):
    def setUp(self):
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
