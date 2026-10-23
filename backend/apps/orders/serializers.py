import re

from rest_framework import serializers

from apps.orders.models import Order, OrderItem


class OrderItemSerializer(serializers.ModelSerializer):
    product_id = serializers.IntegerField(read_only=True)
    line_total = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = ["id", "product_id", "name", "unit_price", "quantity", "line_total"]

    def get_line_total(self, item):
        return item.unit_price * item.quantity


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    user_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = Order
        fields = [
            "id", "user_id", "status", "payment_status", "payment_method",
            "full_name", "address_line1", "city", "state", "postal_code", "phone",
            "subtotal", "tax", "shipping", "total", "items", "created_at", "updated_at",
        ]


class CheckoutSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=200)
    address_line1 = serializers.CharField(max_length=300)
    city = serializers.CharField(max_length=100)
    state = serializers.CharField(max_length=100)
    postal_code = serializers.CharField(max_length=20)
    phone = serializers.CharField(max_length=20)
    payment_method = serializers.ChoiceField(choices=Order.PaymentMethod.choices)
    card_number = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")

    def validate_postal_code(self, value):
        if not re.fullmatch(r"[A-Za-z0-9 -]{4,10}", value.strip()):
            raise serializers.ValidationError("Enter a valid postal code")
        return value.strip()

    def validate_phone(self, value):
        digits = re.sub(r"[\s()+-]", "", value)
        if not digits.isdigit() or not 7 <= len(digits) <= 15:
            raise serializers.ValidationError("Enter a valid phone number")
        return value.strip()

    def validate(self, attrs):
        if attrs["payment_method"] == Order.PaymentMethod.CARD:
            digits = attrs.get("card_number", "").replace(" ", "")
            if not digits.isdigit() or not 12 <= len(digits) <= 19:
                raise serializers.ValidationError({"card_number": "Enter a valid card number"})
        else:
            attrs["card_number"] = ""
        return attrs


class StatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Order.Status.choices)
