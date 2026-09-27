from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.analytics.models import WorkflowEvent

from .models import Conversation, Message
from .serializers import ConversationSerializer, MessageSerializer, PostMessageSerializer, WorkflowEventSerializer
from .services import advance_conversation, get_or_create_state


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

        # Routes the message (CONTINUE/SIDE_QUERY/REPLACE) and runs whichever
        # workflow that decision calls for (see apps/conversations/services.py).
        state, reply = advance_conversation(conversation, content)

        assistant_message = Message.objects.create(
            conversation=conversation,
            role=Message.Role.ASSISTANT,
            content=reply,
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

    @action(detail=True, methods=["get"], url_path="trace")
    def trace(self, request, pk=None):
        conversation = self.get_object()
        events = WorkflowEvent.objects.filter(conversation=conversation).order_by("created_at")
        return Response(WorkflowEventSerializer(events, many=True).data)
