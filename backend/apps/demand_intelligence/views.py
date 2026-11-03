from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsStaffRole
from apps.demand_intelligence import services
from apps.products.models import Product

GRANULARITIES = {"day": 90, "week": 180, "month": 365}


class StaffView(APIView):
    permission_classes = [IsStaffRole]


class OverviewView(StaffView):
    def get(self, request):
        return Response(services.overview())


class ProductListView(StaffView):
    """Per-product demand numbers. Filters: ?trend=increasing|decreasing|stable|insufficient_data  ?risk=critical|warning|ok|stocked_out|no_recent_sales"""

    def get(self, request):
        return Response(services.product_list(request.query_params.get("trend"), request.query_params.get("risk")))


class ProductDetailView(StaffView):
    def get(self, request, product_id):
        product = get_object_or_404(Product.objects.select_related("category"), pk=product_id)
        return Response(services.product_detail(product))


class RestockView(StaffView):
    def get(self, request):
        return Response(services.restock_recommendations())


class SalesView(StaffView):
    """Total sales per day / week / month: ?granularity=day|week|month&days=N (N up to 365)."""

    def get(self, request):
        granularity = request.query_params.get("granularity", "day")
        if granularity not in GRANULARITIES:
            return Response({"detail": "granularity must be day, week or month"}, status=400)
        try:
            days = int(request.query_params.get("days", GRANULARITIES[granularity]))
        except ValueError:
            return Response({"detail": "days must be a number"}, status=400)
        return Response(services.sales_series(granularity, max(1, min(days, 365))))
