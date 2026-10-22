from django.db import models

from apps.products.models import Product


class StockMovement(models.Model):
    """Append-only ledger: every change to Product.stock has exactly one row here."""

    class Reason(models.TextChoices):
        INITIAL = "INITIAL", "Initial stock"
        RESTOCK = "RESTOCK", "Restock"
        ORDER = "ORDER", "Order placed"
        CANCELLATION = "CANCELLATION", "Order cancelled"
        ADJUSTMENT = "ADJUSTMENT", "Manual adjustment"

    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="stock_movements")
    change = models.IntegerField()
    reason = models.CharField(max_length=20, choices=Reason.choices)
    resulting_stock = models.PositiveIntegerField()
    note = models.CharField(max_length=300, blank=True)
    reference = models.CharField(max_length=50, blank=True)  # e.g. "order:12"
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-id"]
        indexes = [models.Index(fields=["product", "-created_at"])]
        constraints = [models.CheckConstraint(condition=~models.Q(change=0), name="movement_change_not_zero")]


class Alert(models.Model):
    class Type(models.TextChoices):
        STOCK_LOW = "STOCK_LOW", "Low stock"
        DEMAND_SPIKE = "DEMAND_SPIKE", "Sudden demand spike"
        STOCKOUT_RISK = "STOCKOUT_RISK", "Predicted stockout"

    type = models.CharField(max_length=20, choices=Type.choices, db_index=True)
    severity = models.CharField(max_length=10, default="medium")
    message = models.CharField(max_length=500)
    product = models.ForeignKey(Product, null=True, on_delete=models.CASCADE, related_name="alerts")
    resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-id"]
