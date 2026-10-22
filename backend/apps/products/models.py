from decimal import Decimal

from django.db import models
from django.db.models import Q

from apps.categories.models import AttributeDefinition, Category


class Product(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        ARCHIVED = "ARCHIVED", "Archived"

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products")
    brand = models.CharField(max_length=100, blank=True)
    image = models.CharField(max_length=500, blank=True)
    # Stock is only changed through apps.inventory.services so every change is in the ledger.
    stock = models.PositiveIntegerField(default=0)
    low_stock_threshold = models.PositiveIntegerField(default=10)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]
        constraints = [models.CheckConstraint(condition=Q(price__gte=Decimal("0")), name="product_price_not_negative")]
        indexes = [
            models.Index(fields=["status", "category"]),
            models.Index(fields=["price"]),
            models.Index(fields=["name"]),
        ]

    def __str__(self):
        return self.name


class ProductAttribute(models.Model):
    """One specification value, e.g. RAM = 16 for a laptop. Which attributes a
    product may have is decided by its category (see AttributeDefinition)."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="attributes")
    definition = models.ForeignKey(AttributeDefinition, on_delete=models.PROTECT)
    value_text = models.CharField(max_length=200, blank=True)
    value_number = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["product", "definition"], name="one_value_per_attribute")]

    @property
    def value(self):
        if self.definition.value_type == AttributeDefinition.ValueType.NUMBER:
            return self.value_number
        return self.value_text
