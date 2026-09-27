from rest_framework import serializers

from apps.analytics.models import WorkflowEvent
from apps.orders.models import Order

from .models import Conversation, Message


class WorkflowEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkflowEvent
        fields = ["id", "event_type", "payload", "created_at"]


class OrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = ["id", "status", "total", "created_at"]


class CheckoutStatusSerializer(serializers.Serializer):
    """The order + its most recent checkout/payment, normalized for the UI.

    Never exposes provider-specific fields (ARCHITECTURE.md §45/§46) — just
    the same PENDING/APPROVED/REJECTED/CANCELLED vocabulary Payment uses.
    """

    order = OrderSerializer(allow_null=True)
    payment_status = serializers.CharField(allow_null=True)
    checkout_url = serializers.CharField(allow_null=True)
    provider = serializers.CharField(allow_null=True)


class MessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = ["id", "role", "content", "created_at"]
        read_only_fields = ["id", "role", "created_at"]


class ConversationSerializer(serializers.ModelSerializer):
    messages = MessageSerializer(many=True, read_only=True)

    class Meta:
        model = Conversation
        fields = ["id", "customer", "is_active", "created_at", "messages"]
        read_only_fields = ["id", "is_active", "created_at", "messages"]
        extra_kwargs = {"customer": {"required": False, "allow_null": True}}


class PostMessageSerializer(serializers.Serializer):
    content = serializers.CharField(allow_blank=False)
