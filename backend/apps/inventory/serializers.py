from rest_framework import serializers

from apps.inventory.models import Alert, StockMovement
from apps.inventory.services import stock_status
from apps.products.models import Product


class InventoryItemSerializer(serializers.ModelSerializer):
    product_id = serializers.IntegerField(source="id", read_only=True)
    status = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = ["product_id", "name", "stock", "low_stock_threshold", "status"]

    def get_status(self, product):
        return stock_status(product.stock, product.low_stock_threshold)


class StockMovementSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockMovement
        fields = ["id", "change", "reason", "resulting_stock", "note", "reference", "created_at"]


class RestockSerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=1, max_value=100000)
    note = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")


class AdjustmentSerializer(serializers.Serializer):
    change = serializers.IntegerField(min_value=-100000, max_value=100000)
    note = serializers.CharField(max_length=300)  # a reason is mandatory for manual corrections

    def validate_change(self, value):
        if value == 0:
            raise serializers.ValidationError("Change cannot be zero")
        return value


class AlertSerializer(serializers.ModelSerializer):
    product_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = Alert
        fields = ["id", "type", "severity", "message", "product_id", "resolved", "created_at", "resolved_at"]
