from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsStaffRole
from apps.analytics import services


class OverviewView(APIView):
    permission_classes = [IsStaffRole]

    def get(self, request):
        return Response(services.overview())


class SystemHealthView(APIView):
    permission_classes = [IsStaffRole]

    def get(self, request):
        from apps.events.health import system_health

        return Response(system_health())


class ProductBehaviourView(APIView):
    permission_classes = [IsStaffRole]

    def get(self, request):
        return Response(services.product_behaviour())


class SalesOverviewView(APIView):
    permission_classes = [IsStaffRole]

    def get(self, request):
        return Response(services.sales_overview())
