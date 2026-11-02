from rest_framework import generics, serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.ai_assistant import orchestrator, requirements
from apps.ai_assistant.models import Conversation, Message


class MessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = ["id", "role", "content", "payload", "created_at"]


def understood(conversation: Conversation) -> dict:
    """What the advisor currently understands, in a shape the UI can show."""
    state = conversation.requirements or {}
    return {
        "summary": requirements.describe(state) if state.get("category_id") else "",
        "priorities": requirements.priority_labels(state),
        "budget": {"min": state.get("min_budget"), "max": state.get("max_budget")},
        "usage": state.get("usage", []),
    }


class ConversationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Conversation
        fields = ["id", "title", "created_at", "updated_at"]


class ConversationDetailSerializer(ConversationSerializer):
    messages = MessageSerializer(many=True, read_only=True)
    pending_action = serializers.JSONField(read_only=True)
    understood = serializers.SerializerMethodField()

    class Meta(ConversationSerializer.Meta):
        fields = ConversationSerializer.Meta.fields + ["messages", "pending_action", "understood"]

    def get_understood(self, conversation):
        return understood(conversation)


class MyConversations:
    """Every query is limited to the logged-in customer's own conversations, so
    another customer's conversation id is simply a 404."""

    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Conversation.objects.filter(user=self.request.user, kind=Conversation.Kind.SHOPPING)


class ConversationListCreateView(MyConversations, generics.ListCreateAPIView):
    serializer_class = ConversationSerializer

    def perform_create(self, serializer):
        serializer.save(user=self.request.user, kind=Conversation.Kind.SHOPPING)


class ConversationDetailView(MyConversations, generics.RetrieveDestroyAPIView):
    serializer_class = ConversationDetailSerializer


class SendMessageSerializer(serializers.Serializer):
    text = serializers.CharField(max_length=1000)


class SendMessageView(MyConversations, APIView):
    """One conversational turn. Rate-limited because it may cost a model call."""

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "assistant"

    def post(self, request, pk):
        conversation = generics.get_object_or_404(self.get_queryset(), pk=pk)
        serializer = SendMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        text = serializer.validated_data["text"].strip()
        if not text:
            return Response({"text": ["This field may not be blank."]}, status=status.HTTP_400_BAD_REQUEST)
        try:
            message = orchestrator.handle_message(conversation, text)
        except ValueError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {"message": MessageSerializer(message).data, "pending_action": conversation.pending_action, "understood": understood(conversation)}
        )


class ConfirmSerializer(serializers.Serializer):
    approve = serializers.BooleanField()


class ConfirmActionView(MyConversations, APIView):
    """The customer's Confirm / Cancel for a pending action (for example adding to the cart)."""

    def post(self, request, pk):
        conversation = generics.get_object_or_404(self.get_queryset(), pk=pk)
        serializer = ConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        message = orchestrator.respond_to_pending(conversation, serializer.validated_data["approve"])
        return Response({"message": MessageSerializer(message).data, "pending_action": conversation.pending_action})
