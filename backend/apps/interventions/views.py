from datetime import timedelta

from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsStaffRole
from apps.events.services import session_key_from_request
from apps.interventions.models import Intervention

ACTIVE_FOR_DAYS = 7  # an older message is stale and is not shown


class InterventionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Intervention
        fields = [
            "id", "user_id", "session_key", "trigger_event_type", "cart_value", "action", "rule", "signals",
            "message", "message_source", "status", "clicked_at", "outcome", "outcome_at", "created_at",
        ]


class ActiveInterventionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Intervention
        fields = ["id", "action", "message", "signals"]


def my_interventions(request):
    """Interventions that belong to the caller: their account and/or their browser
    session. Nobody else's are reachable, so ids from other customers are 404s."""
    condition = Q(pk__in=[])
    if request.user.is_authenticated:
        condition |= Q(user_id=request.user.id)
    session_key = session_key_from_request(request)
    if session_key:
        condition |= Q(session_key=session_key)
    return Intervention.objects.filter(condition)


class CustomerInterventionView(APIView):
    permission_classes = [AllowAny]  # guests are identified by X-Session-Id


class ActiveInterventionView(CustomerInterventionView):
    """Polled by the storefront: is there a rescue message waiting for this customer?"""

    def get(self, request):
        fresh = timezone.now() - timedelta(days=ACTIVE_FOR_DAYS)
        intervention = (
            my_interventions(request)
            .filter(status=Intervention.Status.SENT, outcome="", created_at__gte=fresh)
            .order_by("-created_at")
            .first()
        )
        # JSON null when nothing is waiting (an empty body would break the frontend's res.json()).
        return JsonResponse(ActiveInterventionSerializer(intervention).data if intervention else None, safe=False)


class DismissView(CustomerInterventionView):
    def post(self, request, pk):
        intervention = get_object_or_404(my_interventions(request), pk=pk)
        intervention.status = Intervention.Status.DISMISSED
        intervention.save(update_fields=["status"])
        return Response(ActiveInterventionSerializer(intervention).data)


class ClickView(CustomerInterventionView):
    """The customer followed the message's button (interaction tracking)."""

    def post(self, request, pk):
        intervention = get_object_or_404(my_interventions(request), pk=pk)
        if intervention.clicked_at is None:
            intervention.clicked_at = timezone.now()
            intervention.save(update_fields=["clicked_at"])
        return Response(ActiveInterventionSerializer(intervention).data)


class InterventionListView(generics.ListAPIView):
    """Operations console: every decision, with the rule and signals behind it."""

    permission_classes = [IsStaffRole]
    serializer_class = InterventionSerializer
    queryset = Intervention.objects.all()
