from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

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
        self.assertEqual(state["routing_confidence"], 1.0)

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
