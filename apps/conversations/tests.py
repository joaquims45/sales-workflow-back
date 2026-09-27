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

    def test_post_message_echoes_back(self):
        conversation = Conversation.objects.create()
        url = reverse("conversation-messages", args=[conversation.pk])

        response = self.client.post(url, {"content": "Busco una notebook gamer."}, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(conversation.messages.count(), 2)

        roles = [item["role"] for item in response.data]
        self.assertEqual(roles, [Message.Role.USER, Message.Role.ASSISTANT])
        self.assertIn("Busco una notebook gamer.", response.data[1]["content"])

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
