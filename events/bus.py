"""EventBus: the one place a domain event gets recorded (ARCHITECTURE.md §20/§21).

`emit_event` persists a `WorkflowEvent` (the durable feed the future Trace
view and analytics read from) and publishes the same payload to that
conversation's WebSocket group. One call feeds both — no separate
observability system to keep in sync.

Publishing is best-effort: if no channel layer is configured (e.g. in a
management command run outside ASGI, or a misconfigured environment), the
event is still persisted and the publish step is skipped rather than
raising.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from apps.analytics.models import WorkflowEvent

if TYPE_CHECKING:
    from apps.conversations.models import Conversation


def group_name(conversation_id: int) -> str:
    return f"conversation_{conversation_id}"


def emit_event(conversation: "Conversation", event_type: str, payload: dict[str, Any] | None = None) -> WorkflowEvent:
    event = WorkflowEvent.objects.create(
        conversation=conversation,
        event_type=event_type,
        payload=payload or {},
    )

    channel_layer = get_channel_layer()
    if channel_layer is not None:
        async_to_sync(channel_layer.group_send)(
            group_name(conversation.id),
            {
                "type": "workflow.event",
                "event": {
                    "event_type": event.event_type,
                    "payload": event.payload,
                    "created_at": event.created_at.isoformat(),
                },
            },
        )

    return event
