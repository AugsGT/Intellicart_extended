from django.db import transaction
from django.utils import timezone

from apps.events.services import emit
from apps.inventory.models import Alert, StockMovement
from apps.products.models import Product


class InsufficientStock(Exception):
    def __init__(self, product, available):
        self.product = product
        self.available = available
        super().__init__(f"Only {available} of '{product.name}' left in stock")


def stock_status(stock: int, threshold: int) -> str:
    if stock <= 0:
        return "out_of_stock"
    if stock <= threshold:
        return "low_stock"
    return "healthy"


def apply_stock_change(product: Product, change: int, reason: str, note: str = "", reference: str = "") -> StockMovement:
    """Change stock and write the ledger row.

    The caller MUST already hold a row lock on `product` (select_for_update inside
    transaction.atomic); checkout does this for all its products at once.
    """
    previous_stock = product.stock
    new_stock = previous_stock + change
    if new_stock < 0:
        raise InsufficientStock(product, previous_stock)

    product.stock = new_stock
    product.save(update_fields=["stock", "updated_at"])
    movement = StockMovement.objects.create(
        product=product, change=change, reason=reason, resulting_stock=new_stock, note=note, reference=reference
    )
    _sync_low_stock_alert(product)
    _emit_stock_events(product, previous_stock, change, reason)
    return movement


def _emit_stock_events(product: Product, previous_stock: int, change: int, reason: str) -> None:
    """Domain events for a stock change (written to the outbox in the same transaction)."""
    emit(
        "INVENTORY_UPDATED",
        entity_id=product.id,
        payload={"product_id": product.id, "change": change, "stock": product.stock, "reason": reason},
    )

    # STOCK_LOW once when stock falls to the threshold, and again when it hits zero,
    # not on every change while it stays low.
    threshold = product.low_stock_threshold
    now_low = product.stock <= threshold
    crossed_threshold = previous_stock > threshold
    hit_zero = product.stock == 0 and previous_stock > 0
    if now_low and (crossed_threshold or hit_zero):
        emit(
            "STOCK_LOW",
            entity_id=product.id,
            payload={"product_id": product.id, "stock": product.stock, "threshold": threshold},
        )

    # Back in stock after being sold out (a brand-new product is not "restocked").
    if previous_stock == 0 and product.stock > 0 and reason != "INITIAL":
        emit("STOCK_RESTOCKED", entity_id=product.id, payload={"product_id": product.id, "stock": product.stock})


@transaction.atomic
def adjust_stock(product_id: int, change: int, reason: str, note: str = "", reference: str = "") -> StockMovement:
    """Lock the product row, then change its stock."""
    product = Product.objects.select_for_update().get(pk=product_id)
    return apply_stock_change(product, change, reason, note, reference)


def _sync_low_stock_alert(product: Product) -> None:
    """Keep one open alert while stock is at or below the threshold (updated as
    stock keeps falling); close it once stock is healthy again."""
    open_alerts = Alert.objects.filter(product=product, type=Alert.Type.STOCK_LOW, resolved=False)
    if product.stock <= product.low_stock_threshold:
        what = "out of stock" if product.stock == 0 else f"low on stock ({product.stock} left)"
        fields = {"severity": "high" if product.stock == 0 else "medium", "message": f"{product.name} is {what}"}
        if open_alerts.exists():
            open_alerts.update(**fields)
        else:
            Alert.objects.create(type=Alert.Type.STOCK_LOW, product=product, **fields)
    else:
        open_alerts.update(resolved=True, resolved_at=timezone.now())
