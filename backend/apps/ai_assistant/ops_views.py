from rest_framework import generics, serializers, status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts.permissions import IsStaffRole
from apps.ai_assistant import ops_orchestrator
from apps.audit import services as audit
from apps.ai_assistant.models import Conversation
from apps.ai_assistant.views import ConversationSerializer, MessageSerializer


class OpsConversationDetailSerializer(ConversationSerializer):
    messages = MessageSerializer(many=True, read_only=True)

    class Meta(ConversationSerializer.Meta):
        fields = ConversationSerializer.Meta.fields + ["messages"]


class MyOpsConversations:
    """Staff only (checked on every request against the database role, so a demoted
    user loses access immediately), and only the staff member's own conversations."""

    permission_classes = [IsStaffRole]

    def get_queryset(self):
        return Conversation.objects.filter(user=self.request.user, kind=Conversation.Kind.OPERATIONS)


class OpsConversationListCreateView(MyOpsConversations, generics.ListCreateAPIView):
    serializer_class = ConversationSerializer

    def perform_create(self, serializer):
        serializer.save(user=self.request.user, kind=Conversation.Kind.OPERATIONS)


class OpsConversationDetailView(MyOpsConversations, generics.RetrieveDestroyAPIView):
    serializer_class = OpsConversationDetailSerializer


class AskSerializer(serializers.Serializer):
    text = serializers.CharField(max_length=1000)


class OpsAskView(MyOpsConversations, APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "assistant"

    def post(self, request, pk):
        conversation = generics.get_object_or_404(self.get_queryset(), pk=pk)
        serializer = AskSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        text = serializer.validated_data["text"].strip()
        if not text:
            return Response({"text": ["This field may not be blank."]}, status=status.HTTP_400_BAD_REQUEST)
        try:
            message = ops_orchestrator.handle_question(conversation, text)
        except ValueError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        # Staff can see sensitive business data through the assistant, so every question is recorded.
        audit.record(request, "OPS_ASSISTANT_QUERY", f"Asked the operations assistant: {text[:120]}", entity_type="conversation", entity_id=conversation.id,
                     details={"question": text[:300], "tools": [t["name"] for t in message.payload.get("tools", [])]})
        return Response({"message": MessageSerializer(message).data})
