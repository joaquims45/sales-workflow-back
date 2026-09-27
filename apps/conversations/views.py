from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Conversation, Message
from .serializers import ConversationSerializer, MessageSerializer, PostMessageSerializer


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
        # Placeholder response until the sales workflow/routing is wired in (M6+).
        assistant_message = Message.objects.create(
            conversation=conversation,
            role=Message.Role.ASSISTANT,
            content=f"Recibido: {content}",
        )

        return Response(
            MessageSerializer([user_message, assistant_message], many=True).data,
            status=status.HTTP_201_CREATED,
        )
