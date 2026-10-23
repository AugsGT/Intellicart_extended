from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.products.models import Product


class OrderQuerySet(models.QuerySet):
    def successful(self):
        """Orders that count as real purchases: paid and not cancelled or failed.

        Purchase history, recommendations and demand statistics must all use this,
        never a raw Order query, so failed and cancelled orders cannot leak in.
        """
        return self.filter(payment_status=Order.PaymentStatus.PAID).exclude(
            status__in=[Order.Status.CANCELLED, Order.Status.FAILED]
        )


class Order(models.Model):
    class Status(models.TextChoices):
        CONFIRMED = "CONFIRMED", "Confirmed"
        SHIPPED = "SHIPPED", "Shipped"
        DELIVERED = "DELIVERED", "Delivered"
        CANCELLED = "CANCELLED", "Cancelled"
        FAILED = "FAILED", "Failed"

    class PaymentStatus(models.TextChoices):
        PAID = "PAID", "Paid"
        FAILED = "FAILED", "Failed"
        REFUNDED = "REFUNDED", "Refunded"

    class PaymentMethod(models.TextChoices):
        CARD = "card", "Card"
        UPI = "upi", "UPI"
        COD = "cod", "Cash on delivery"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="orders")
    status = models.CharField(max_length=12, choices=Status.choices, db_index=True)
    payment_status = models.CharField(max_length=10, choices=PaymentStatus.choices)
    payment_method = models.CharField(max_length=10, choices=PaymentMethod.choices)
    # The payment gateway is a MOCK (apps.orders.payments). No real money moves.
    payment_reference = models.CharField(max_length=50, blank=True)
    # Sent by the browser with the checkout request so a repeated request cannot create a second order.
    idempotency_key = models.CharField(max_length=64, blank=True)

    full_name = models.CharField(max_length=200)
    address_line1 = models.CharField(max_length=300)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20)
    phone = models.CharField(max_length=20)

    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    tax = models.DecimalField(max_digits=10, decimal_places=2)
    shipping = models.DecimalField(max_digits=10, decimal_places=2)
    total = models.DecimalField(max_digits=10, decimal_places=2)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = OrderQuerySet.as_manager()

    class Meta:
        ordering = ["-id"]
        indexes = [models.Index(fields=["user", "-created_at"]), models.Index(fields=["payment_status", "status", "created_at"])]
        constraints = [
            models.CheckConstraint(condition=Q(total__gte=0), name="order_total_not_negative"),
            models.UniqueConstraint(fields=["user", "idempotency_key"], condition=~Q(idempotency_key=""), name="one_order_per_idempotency_key"),
        ]


class OrderItem(models.Model):
    """Price and name are copied from the product at purchase time."""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="order_items")
    name = models.CharField(max_length=200)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField()

    class Meta:
        ordering = ["id"]
        constraints = [models.CheckConstraint(condition=Q(quantity__gte=1), name="order_item_quantity_positive")]
