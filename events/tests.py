import json

from asgiref.sync import sync_to_async
from channels.testing import WebsocketCommunicator
from django.test import SimpleTestCase, TestCase, TransactionTestCase

from apps.analytics.models import WorkflowEvent
from apps.conversations.models import Conversation
from config.asgi import application

from .bus import emit_event, group_name


class GroupNameTests(SimpleTestCase):
    def test_formats_conversation_group_name(self):
        self.assertEqual(group_name(42), "conversation_42")


class EmitEventTests(TestCase):
    def test_persists_workflow_event(self):
        conversation = Conversation.objects.create()

        event = emit_event(conversation, "workflow.started", {"workflow": "PRODUCT_PURCHASE"})

        self.assertEqual(WorkflowEvent.objects.count(), 1)
        self.assertEqual(event.conversation_id, conversation.id)
        self.assertEqual(event.event_type, "workflow.started")
        self.assertEqual(event.payload, {"workflow": "PRODUCT_PURCHASE"})

    def test_defaults_payload_to_empty_dict(self):
        conversation = Conversation.objects.create()

        event = emit_event(conversation, "workflow.completed")

        self.assertEqual(event.payload, {})

    def test_publish_to_channel_layer_does_not_raise_without_listeners(self):
        # Uses the in-memory channel layer (default test settings, no
        # REDIS_URL) — group_send to a group with no active consumer must
        # be a safe no-op, not an error.
        conversation = Conversation.objects.create()

        emit_event(conversation, "routing.completed", {"decision": "CONTINUE", "confidence": 0.7})

        self.assertEqual(WorkflowEvent.objects.count(), 1)


class ConversationEventsConsumerTests(TransactionTestCase):
    async def test_connected_client_receives_emitted_event(self):
        conversation = await sync_to_async(Conversation.objects.create)()

        communicator = WebsocketCommunicator(application, f"/ws/conversations/{conversation.id}/")
        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        await sync_to_async(emit_event)(
            conversation, "workflow.started", {"workflow": "PRODUCT_PURCHASE"}
        )

        raw_message = await communicator.receive_from()
        message = json.loads(raw_message)

        self.assertEqual(message["event_type"], "workflow.started")
        self.assertEqual(message["payload"], {"workflow": "PRODUCT_PURCHASE"})

        await communicator.disconnect()
