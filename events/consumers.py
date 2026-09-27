import json

from channels.generic.websocket import AsyncWebsocketConsumer

from .bus import group_name


class ConversationEventsConsumer(AsyncWebsocketConsumer):
    """Streams a conversation's WorkflowEvents to whoever is watching it
    (Workflow Brain / Workflow Inspector / Trace, once the frontend exists).
    """

    async def connect(self):
        self.conversation_id = self.scope["url_route"]["kwargs"]["conversation_id"]
        self.group_name = group_name(self.conversation_id)

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def workflow_event(self, event):
        await self.send(text_data=json.dumps(event["event"]))
