from rest_framework import serializers

from .models import Conversation, Message


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
