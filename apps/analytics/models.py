from django.db import models

from apps.conversations.models import Conversation


class WorkflowEvent(models.Model):
    """A single domain event (ARCHITECTURE.md §20/§21).

    This is the one place events are recorded — it doubles as the durable
    feed for the future Trace view (M10) and as what gets published live
    over WebSockets (events/bus.py), so there's no separate observability
    system to keep in sync.
    """

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="events")
    event_type = models.CharField(max_length=100)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.event_type} (conversation #{self.conversation_id})"
