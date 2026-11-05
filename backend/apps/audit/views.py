from rest_framework import generics, serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsAdminRole
from apps.audit.models import AuditLog
from apps.audit.services import ACTIONS


class AuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = ["id", "created_at", "actor_label", "actor_role", "action", "entity_type", "entity_id", "summary", "details", "ip_address"]


class AuditLogListView(generics.ListAPIView):
    """Administrators only. Read-only: there is no endpoint that edits or deletes entries.

    Filters: ?action=  ?actor=<email contains>  ?entity_type=  ?entity_id=  ?since=<ISO date>  ?until=<ISO date>
    """

    permission_classes = [IsAdminRole]
    serializer_class = AuditLogSerializer

    def get_queryset(self):
        params = self.request.query_params
        entries = AuditLog.objects.all()
        if params.get("action"):
            entries = entries.filter(action=params["action"])
        if params.get("actor"):
            entries = entries.filter(actor_label__icontains=params["actor"])
        if params.get("entity_type"):
            entries = entries.filter(entity_type=params["entity_type"])
        if params.get("entity_id"):
            entries = entries.filter(entity_id=params["entity_id"])
        if params.get("since"):
            entries = entries.filter(created_at__date__gte=params["since"])
        if params.get("until"):
            entries = entries.filter(created_at__date__lte=params["until"])
        return entries


class AuditActionsView(APIView):
    """The list of recorded actions with plain-language descriptions (for the filter dropdown)."""

    permission_classes = [IsAdminRole]

    def get(self, request):
        return Response([{"action": key, "description": text} for key, text in ACTIONS.items()])
