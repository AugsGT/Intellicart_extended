from django.db import transaction
from rest_framework import serializers

from apps.inventory import services as inventory
from apps.products import services
from apps.products.models import Product


class AttributeInputSerializer(serializers.Serializer):
    key = serializers.SlugField()
    value = serializers.JSONField()


class ProductSerializer(serializers.ModelSerializer):
    attributes = serializers.SerializerMethodField()
    attributes_input = AttributeInputSerializer(many=True, write_only=True, required=False)
    category_name = serializers.CharField(source="category.name", read_only=True)
    stock_status = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id", "name", "description", "price", "category", "category_name", "brand", "image",
            "stock", "low_stock_threshold", "stock_status", "status", "attributes", "attributes_input",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "status", "created_at", "updated_at"]

    def get_attributes(self, product):
        return [
            {"key": a.definition.key, "label": a.definition.label, "value": a.value, "unit": a.definition.unit}
            for a in product.attributes.all()
        ]

    def get_stock_status(self, product):
        return inventory.stock_status(product.stock, product.low_stock_threshold)

    def validate_price(self, value):
        if value < 0:
            raise serializers.ValidationError("Price cannot be negative")
        return value

    def validate(self, attrs):
        if self.instance is not None and "stock" in attrs:
            raise serializers.ValidationError({"stock": "Change stock with the inventory endpoints"})
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        attributes = validated_data.pop("attributes_input", [])
        initial_stock = validated_data.pop("stock", 0)
        product = Product.objects.create(stock=0, **validated_data)
        self._save_attributes(product, attributes)
        if initial_stock:
            inventory.adjust_stock(product.id, initial_stock, reason="INITIAL", note="Initial stock")
            product.refresh_from_db()
        return product

    @transaction.atomic
    def update(self, instance, validated_data):
        attributes = validated_data.pop("attributes_input", None)
        product = super().update(instance, validated_data)
        if attributes is not None or "category" in validated_data:
            # A category change must not leave attributes that no longer apply.
            self._save_attributes(product, attributes if attributes is not None else [])
        return product

    def _save_attributes(self, product, attributes):
        try:
            services.set_attributes(product, attributes)
        except services.ProductAttributeError as error:
            raise serializers.ValidationError({"attributes_input": str(error)})
