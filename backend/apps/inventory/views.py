from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsAdminRole, IsStaffRole
from apps.audit import services as audit
from apps.inventory import services
from apps.inventory.models import Alert, StockMovement
from apps.inventory.serializers import (
    AdjustmentSerializer,
    AlertSerializer,
    InventoryItemSerializer,
    RestockSerializer,
    StockMovementSerializer,
)
from apps.products.models import Product


class InventoryListView(generics.ListAPIView):
    permission_classes = [IsStaffRole]
    serializer_class = InventoryItemSerializer
    queryset = Product.objects.order_by("id")


class StockHistoryView(generics.ListAPIView):
    permission_classes = [IsStaffRole]
    serializer_class = StockMovementSerializer

    def get_queryset(self):
        return StockMovement.objects.filter(product_id=self.kwargs["product_id"])


class RestockView(APIView):
    permission_classes = [IsAdminRole]

    def post(self, request, product_id):
        get_object_or_404(Product, pk=product_id)
        serializer = RestockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.adjust_stock(product_id, serializer.validated_data["quantity"], "RESTOCK", serializer.validated_data["note"])
        product = Product.objects.get(pk=product_id)
        audit.record(request, "STOCK_RESTOCKED", f"Added {serializer.validated_data['quantity']} units to {product.name}",
                     entity_type="product", entity_id=product_id,
                     details={"quantity": serializer.validated_data["quantity"], "note": serializer.validated_data["note"], "stock_after": product.stock})
        return Response(InventoryItemSerializer(product).data)


class AdjustStockView(APIView):
    permission_classes = [IsAdminRole]

    def post(self, request, product_id):
        get_object_or_404(Product, pk=product_id)
        serializer = AdjustmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            services.adjust_stock(product_id, serializer.validated_data["change"], "ADJUSTMENT", serializer.validated_data["note"])
        except services.InsufficientStock as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        product = Product.objects.get(pk=product_id)
        audit.record(request, "STOCK_ADJUSTED", f"Adjusted {product.name} by {serializer.validated_data['change']:+d}",
                     entity_type="product", entity_id=product_id,
                     details={"change": serializer.validated_data["change"], "reason": serializer.validated_data["note"], "stock_after": product.stock})
        return Response(InventoryItemSerializer(product).data)


class AlertListView(generics.ListAPIView):
    permission_classes = [IsStaffRole]
    serializer_class = AlertSerializer

    def get_queryset(self):
        alerts = Alert.objects.all()
        resolved = self.request.query_params.get("resolved")
        if resolved in ("true", "false"):
            alerts = alerts.filter(resolved=(resolved == "true"))
        return alerts


class AlertResolveView(APIView):
    permission_classes = [IsStaffRole]

    def patch(self, request, pk):
        alert = get_object_or_404(Alert, pk=pk)
        if not alert.resolved:
            alert.resolved = True
            alert.resolved_at = timezone.now()
            alert.save(update_fields=["resolved", "resolved_at"])
            audit.record(request, "ALERT_RESOLVED", f"Resolved alert: {alert.message}", entity_type="alert", entity_id=alert.id,
                         details={"type": alert.type})
        return Response(AlertSerializer(alert).data)
