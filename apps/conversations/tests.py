import tempfile
from pathlib import Path

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.analytics.models import WorkflowEvent
from apps.catalog.models import Category, Product

from .models import Conversation, Message


class ConversationAPITests(APITestCase):
    def test_create_conversation(self):
        url = reverse("conversation-list")
        response = self.client.post(url, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Conversation.objects.count(), 1)
        self.assertEqual(response.data["messages"], [])

    def test_post_message_runs_workflow_and_replies(self):
        conversation = Conversation.objects.create()
        url = reverse("conversation-messages", args=[conversation.pk])

        response = self.client.post(url, {"content": "Busco una notebook gamer."}, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(conversation.messages.count(), 2)

        roles = [item["role"] for item in response.data["messages"]]
        self.assertEqual(roles, [Message.Role.USER, Message.Role.ASSISTANT])
        # No budget yet -> DISCOVERY asks for it instead of searching.
        self.assertIn("presupuesto", response.data["messages"][1]["content"].lower())

    def test_post_message_updates_sales_state(self):
        conversation = Conversation.objects.create()
        url = reverse("conversation-messages", args=[conversation.pk])

        response = self.client.post(
            url, {"content": "Busco una notebook para programar y jugar."}, format="json"
        )

        state = response.data["sales_state"]
        self.assertEqual(state["primary_goal"], "BUY_PRODUCT")
        self.assertIn("gaming", state["customer_needs"])
        self.assertIn("programming", state["customer_needs"])
        self.assertEqual(state["funnel_stage"], "CONSIDERATION")
        self.assertEqual(state["routing_decision"], "CONTINUE")
        self.assertEqual(state["routing_confidence"], 0.7)

    def test_state_endpoint_returns_current_snapshot(self):
        conversation = Conversation.objects.create()
        messages_url = reverse("conversation-messages", args=[conversation.pk])
        self.client.post(messages_url, {"content": "Tengo hasta $1.500.000."}, format="json")

        state_url = reverse("conversation-state", args=[conversation.pk])
        response = self.client.get(state_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["constraints"]["budget_max"], 1500000)

    def test_post_message_requires_content(self):
        conversation = Conversation.objects.create()
        url = reverse("conversation-messages", args=[conversation.pk])

        response = self.client.post(url, {"content": ""}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_retrieve_conversation_includes_messages_in_order(self):
        conversation = Conversation.objects.create()
        Message.objects.create(conversation=conversation, role=Message.Role.USER, content="Hola")
        Message.objects.create(conversation=conversation, role=Message.Role.ASSISTANT, content="Hola, ¿en qué te ayudo?")

        url = reverse("conversation-detail", args=[conversation.pk])
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["messages"]), 2)
        self.assertEqual(response.data["messages"][0]["content"], "Hola")


class ConversationScenarioTests(APITestCase):
    """The golden-path scenario from PLAN.MD §25/ARCHITECTURE.md §8:

    a shipping SIDE_QUERY must not destroy the PRODUCT_PURCHASE workflow.
    """

    def setUp(self):
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

    def _post_message(self, conversation, content):
        url = reverse("conversation-messages", args=[conversation.pk])
        return self.client.post(url, {"content": content}, format="json")

    def test_shipping_side_query_does_not_destroy_product_purchase(self):
        conversation = Conversation.objects.create()

        self._post_message(conversation, "Busco una notebook gamer.")
        budget_response = self._post_message(conversation, "Tengo hasta $1.500.000.")

        state_after_budget = budget_response.data["sales_state"]
        self.assertIn(self.gaming_laptop.id, state_after_budget["candidate_products"])
        self.assertEqual(state_after_budget["active_workflow"], "PRODUCT_PURCHASE")

        shipping_response = self._post_message(conversation, "¿Hacen envíos a Santa Fe?")

        shipping_reply = shipping_response.data["messages"][1]["content"]
        self.assertIn("Santa Fe", shipping_reply)

        state_after_shipping = shipping_response.data["sales_state"]
        # PRODUCT_PURCHASE context survived the interruption untouched.
        self.assertEqual(state_after_shipping["active_workflow"], "PRODUCT_PURCHASE")
        self.assertEqual(
            state_after_shipping["candidate_products"], state_after_budget["candidate_products"]
        )
        self.assertEqual(state_after_shipping["constraints"]["budget_max"], 1500000)
        self.assertEqual(state_after_shipping["routing_decision"], "RESUME")
        self.assertIsNone(state_after_shipping["interruption"])

        event_types = list(
            conversation.events.order_by("created_at").values_list("event_type", flat=True)
        )
        self.assertIn("workflow.started", event_types)
        self.assertIn("workflow.suspended", event_types)
        self.assertIn("workflow.resumed", event_types)
        self.assertEqual(event_types.count("jev.decision"), 3)
        self.assertEqual(event_types.count("routing.completed"), 3)

    def test_replace_abandons_previous_goal_and_starts_a_new_one(self):
        Category.objects.create(name="Monitores", slug="monitores")
        conversation = Conversation.objects.create()

        self._post_message(conversation, "Busco una notebook gamer.")
        budget_response = self._post_message(conversation, "Tengo hasta $1.500.000.")
        self.assertIn(self.gaming_laptop.id, budget_response.data["sales_state"]["candidate_products"])

        replace_response = self._post_message(
            conversation, "Olvidate de la notebook. Quiero buscar un monitor."
        )

        state_after_replace = replace_response.data["sales_state"]
        self.assertEqual(state_after_replace["routing_decision"], "REPLACE")
        self.assertEqual(state_after_replace["candidate_products"], [])
        self.assertEqual(state_after_replace["constraints"], {})
        self.assertEqual(state_after_replace["active_workflow"], "PRODUCT_PURCHASE")

        self.assertTrue(
            WorkflowEvent.objects.filter(conversation=conversation, event_type="workflow.replaced").exists()
        )
