from django.urls import re_path

from .consumers import ConversationEventsConsumer

websocket_urlpatterns = [
    re_path(r"^ws/conversations/(?P<conversation_id>\d+)/$", ConversationEventsConsumer.as_asgi()),
]
