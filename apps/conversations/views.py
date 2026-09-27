from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Conversation, Message
from .serializers import ConversationSerializer, MessageSerializer, PostMessageSerializer
from .services import get_or_create_state, update_state_from_message


class ConversationViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    queryset = Conversation.objects.all()
    serializer_class = ConversationSerializer

    @action(detail=True, methods=["post"])
    def messages(self, request, pk=None):
        conversation = self.get_object()

        input_serializer = PostMessageSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        content = input_serializer.validated_data["content"]

        user_message = Message.objects.create(
            conversation=conversation, role=Message.Role.USER, content=content
        )

        # Hardcoded transition until the real router (Jev) + PRODUCT_PURCHASE
        # graph exist (M4+) — see workflows/graph/transitions.py.
        state = update_state_from_message(conversation, content)

        # Placeholder response until the sales workflow/routing is wired in (M6+).
        assistant_message = Message.objects.create(
            conversation=conversation,
            role=Message.Role.ASSISTANT,
            content=f"Recibido: {content}",
        )

        return Response(
            {
                "messages": MessageSerializer([user_message, assistant_message], many=True).data,
                "sales_state": state,
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["get"], url_path="state")
    def state(self, request, pk=None):
        conversation = self.get_object()
        return Response(get_or_create_state(conversation))
