from decimal import Decimal

from django.db import transaction

from apps.accounts.models import User
from apps.cart.models import Cart
from apps.cart.pricing import calculate_totals
from apps.events.services import emit
from apps.inventory.services import InsufficientStock, apply_stock_change
from apps.orders import payments
from apps.orders.models import Order, OrderItem
from apps.products.models import Product

# Allowed status changes. DELIVERED, CANCELLED and FAILED are final.
TRANSITIONS = {
    Order.Status.CONFIRMED: {Order.Status.SHIPPED, Order.Status.CANCELLED},
    Order.Status.SHIPPED: {Order.Status.DELIVERED, Order.Status.CANCELLED},
    Order.Status.DELIVERED: set(),
    Order.Status.CANCELLED: set(),
    Order.Status.FAILED: set(),
}


class CheckoutError(Exception):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class PaymentDeclined(Exception):
    def __init__(self, order):
        super().__init__("Payment was declined")
        self.order = order


def checkout(user, shipping: dict, payment_method: str, card_number: str = "", idempotency_key: str = "") -> Order:
    """Turn the user's active cart into an order.

    Everything happens in one transaction. Products are row-locked (in id order, so
    two checkouts cannot deadlock) before stock is checked, so two customers can
    never both buy the last unit.

    Idempotency: if the caller sends the same `idempotency_key` again (a double click,
    or a retry after a network timeout), no second order is created and the first result
    is returned. The customer's own row is locked first, so even two simultaneous
    requests with one key cannot both create an order.

    Raises CheckoutError (empty cart, unavailable product, not enough stock) or
    PaymentDeclined (the declined attempt is saved as a FAILED order; stock and cart
    are left untouched).
    """
    with transaction.atomic():
        User.objects.select_for_update().filter(pk=user.pk).first()    # one checkout at a time per customer
        if idempotency_key:
            existing = Order.objects.filter(user=user, idempotency_key=idempotency_key).first()
            if existing is not None:
                existing.replayed = True
                if existing.status == Order.Status.FAILED:
                    raise PaymentDeclined(existing)                     # the same decline, not a new charge attempt
                return existing

        cart = Cart.objects.select_for_update().filter(user=user, status=Cart.Status.ACTIVE).first()
        items = list(cart.items.all()) if cart else []
        if not items:
            raise CheckoutError("Cart is empty")

        quantities = {item.product_id: item.quantity for item in items}
        products = {
            p.id: p for p in Product.objects.select_for_update().filter(id__in=quantities).order_by("id")
        }

        for product_id, quantity in quantities.items():
            product = products.get(product_id)
            if product is None or product.status != Product.Status.ACTIVE:
                raise CheckoutError("A product in your cart is no longer available")
            if quantity > product.stock:
                raise CheckoutError(f"Only {product.stock} of '{product.name}' left in stock")

        subtotal = sum((products[pid].price * qty for pid, qty in quantities.items()), Decimal("0"))
        totals = calculate_totals(subtotal)
        result = payments.charge(totals["total"], payment_method, card_number)

        order = Order.objects.create(
            user=user,
            status=Order.Status.CONFIRMED if result.success else Order.Status.FAILED,
            payment_status=Order.PaymentStatus.PAID if result.success else Order.PaymentStatus.FAILED,
            payment_method=payment_method,
            payment_reference=result.reference,
            idempotency_key=idempotency_key,
            **shipping,
            **totals,
        )
        for product_id, quantity in quantities.items():
            product = products[product_id]
            OrderItem.objects.create(
                order=order, product=product, name=product.name, unit_price=product.price, quantity=quantity
            )

        emit(
            "ORDER_CREATED",
            user=user,
            entity_id=order.id,
            payload={"order_id": order.id, "total": str(order.total), "item_count": sum(quantities.values())},
        )
        if result.success:
            for product_id, quantity in quantities.items():
                apply_stock_change(products[product_id], -quantity, "ORDER", reference=f"order:{order.id}")
            cart.status = Cart.Status.CHECKED_OUT
            cart.save(update_fields=["status", "updated_at"])
            emit(
                "PAYMENT_SUCCEEDED",
                user=user,
                entity_id=order.id,
                payload={"order_id": order.id, "amount": str(order.total), "method": payment_method},
            )
            emit("ORDER_COMPLETED", user=user, entity_id=order.id, payload={"order_id": order.id, "total": str(order.total)})
        else:
            emit(
                "PAYMENT_FAILED",
                user=user,
                entity_id=order.id,
                payload={"order_id": order.id, "amount": str(order.total), "method": payment_method, "reason": result.reason},
            )

    if not result.success:
        # Raised after the transaction so the FAILED order record is committed.
        raise PaymentDeclined(order)
    return order


def can_transition(current: str, target: str) -> bool:
    return target in TRANSITIONS.get(current, set())


@transaction.atomic
def change_status(order_id: int, target: str, user=None) -> Order:
    """Move an order to a new status. Cancelling puts the stock back and marks the
    payment REFUNDED (mock). `user` limits the lookup to that customer's own orders."""
    orders = Order.objects.select_for_update()
    if user is not None:
        orders = orders.filter(user=user)
    order = orders.filter(pk=order_id).first()
    if order is None:
        raise CheckoutError("Order not found", status_code=404)

    if not can_transition(order.status, target):
        raise CheckoutError(f"Cannot change an order from {order.status} to {target}")

    if target == Order.Status.CANCELLED:
        items = list(order.items.all())
        products = Product.objects.select_for_update().filter(id__in=[i.product_id for i in items]).order_by("id")
        by_id = {p.id: p for p in products}
        for item in items:
            apply_stock_change(by_id[item.product_id], item.quantity, "CANCELLATION", reference=f"order:{order.id}")
        if order.payment_status == Order.PaymentStatus.PAID:
            order.payment_status = Order.PaymentStatus.REFUNDED

    order.status = target
    order.save()
    if target == Order.Status.CANCELLED:
        emit("ORDER_CANCELLED", user=order.user_id, entity_id=order.id, payload={"order_id": order.id, "total": str(order.total)})
    return order
