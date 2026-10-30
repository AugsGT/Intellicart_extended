from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.accounts.permissions import IsStaffRole
from apps.customer_intelligence import services


class MyPurchaseHistoryView(APIView):
    """A customer's own purchase history; the user always comes from the token."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(services.purchase_history(request.user))


class CustomerPurchaseHistoryView(APIView):
    """Staff view of one customer's purchase history."""

    permission_classes = [IsStaffRole]

    def get(self, request, user_id):
        user = get_object_or_404(User, pk=user_id)
        return Response(services.purchase_history(user))


class HighIntentCustomersView(APIView):
    """Operations console: customers most recently scored HIGH or MEDIUM, each with
    the exact signals and weights behind the score."""

    permission_classes = [IsStaffRole]

    def get(self, request):
        from apps.customer_intelligence.intent import latest_scores

        return Response(
            [
                {
                    "user_id": s.user_id,
                    "session_id": s.session_key,
                    "score": s.score,
                    "tier": s.tier,
                    "basis": s.basis,
                    "computed_at": s.computed_at,
                }
                for s in latest_scores(["HIGH", "MEDIUM"], limit=100)
            ]
        )
