from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.products.models import Product


class Cart(models.Model):
    """A shopping cart owned by a logged-in user, or by an anonymous browser
    (identified by a random session key) until that person logs in.

    Carts are kept after checkout (status CHECKED_OUT) so cart history exists.
    """

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        CHECKED_OUT = "CHECKED_OUT", "Checked out"
        MERGED = "MERGED", "Merged into a user cart"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="carts")
    session_key = models.CharField(max_length=64, null=True, blank=True, db_index=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE)
    abandonment_flagged_at = models.DateTimeField(null=True, blank=True)  # set by the Phase 6 scanner
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            # exactly one owner
            models.CheckConstraint(
                condition=(Q(user__isnull=False) & Q(session_key__isnull=True))
                | (Q(user__isnull=True) & Q(session_key__isnull=False)),
                name="cart_has_exactly_one_owner",
            ),
            # at most one ACTIVE cart per owner
            models.UniqueConstraint(
                fields=["user"], condition=Q(status="ACTIVE", user__isnull=False), name="one_active_cart_per_user"
            ),
            models.UniqueConstraint(
                fields=["session_key"], condition=Q(status="ACTIVE", session_key__isnull=False), name="one_active_cart_per_session"
            ),
        ]


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(fields=["cart", "product"], name="one_row_per_product_in_cart"),
            models.CheckConstraint(condition=Q(quantity__gte=1), name="cart_item_quantity_positive"),
        ]
