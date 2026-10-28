from rest_framework import generics
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsStaffRole
from apps.events import services
from apps.events.models import DeadLetterEvent, Event
from apps.events.serializers import DeadLetterSerializer, EventSerializer


class EventListView(generics.ListAPIView):
    """Operations console: the processed event log, newest first (?event_type=)."""

    permission_classes = [IsStaffRole]
    serializer_class = EventSerializer

    def get_queryset(self):
        events = Event.objects.all()
        event_type = self.request.query_params.get("event_type")
        return events.filter(event_type=event_type) if event_type else events


class DeadLetterListView(generics.ListAPIView):
    permission_classes = [IsStaffRole]
    serializer_class = DeadLetterSerializer
    queryset = DeadLetterEvent.objects.all()


class CheckoutStartedView(APIView):
    """The checkout page tells us the shopper reached it (used for abandonment analysis)."""

    permission_classes = [AllowAny]

    def post(self, request):
        user = request.user if request.user.is_authenticated else None
        services.emit("CHECKOUT_STARTED", user=user, session_key=services.session_key_from_request(request))
        return Response({"detail": "tracked"}, status=202)
