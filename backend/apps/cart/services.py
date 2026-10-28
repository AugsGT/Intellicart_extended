from decimal import Decimal

from django.db import transaction

from apps.cart.models import Cart, CartItem
from apps.cart.pricing import calculate_totals, money
from apps.events.services import emit
from apps.products.models import Product

MAX_QUANTITY_PER_ITEM = 99


class CartError(Exception):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def get_active_cart(user=None, session_key=None) -> Cart:
    """The caller's ACTIVE cart, created if missing. Owner is a user OR a session key."""
    if user is not None:
        cart, _ = Cart.objects.get_or_create(user=user, status=Cart.Status.ACTIVE)
    else:
        cart, _ = Cart.objects.get_or_create(session_key=session_key, status=Cart.Status.ACTIVE)
    return cart


def _check_available(product: Product, quantity: int) -> None:
    if product.status != Product.Status.ACTIVE:
        raise CartError("Product is not available", status_code=404)
    if product.stock <= 0:
        raise CartError("Product is out of stock")
    if quantity > product.stock:
        raise CartError(f"Only {product.stock} of '{product.name}' available")


def add_item(cart: Cart, product_id: int, quantity: int) -> None:
    if not 1 <= quantity <= MAX_QUANTITY_PER_ITEM:
        raise CartError(f"Quantity must be between 1 and {MAX_QUANTITY_PER_ITEM}")
    product = Product.objects.filter(pk=product_id).first()
    if product is None:
        raise CartError("Product not found", status_code=404)

    existing = CartItem.objects.filter(cart=cart, product=product).first()
    new_quantity = (existing.quantity if existing else 0) + quantity
    _check_available(product, new_quantity)

    if existing:
        existing.quantity = new_quantity
        existing.save(update_fields=["quantity", "updated_at"])
    else:
        CartItem.objects.create(cart=cart, product=product, quantity=quantity)
    cart.save(update_fields=["updated_at"])
    emit(
        "CART_ITEM_ADDED",
        user=cart.user_id,
        session_key=cart.session_key or "",
        entity_id=product.id,
        payload={"product_id": product.id, "quantity": quantity},
    )


def update_item(cart: Cart, item_id: int, quantity: int) -> None:
    if not 1 <= quantity <= MAX_QUANTITY_PER_ITEM:
        raise CartError(f"Quantity must be between 1 and {MAX_QUANTITY_PER_ITEM}")
    item = _get_item(cart, item_id)
    _check_available(item.product, quantity)
    item.quantity = quantity
    item.save(update_fields=["quantity", "updated_at"])
    cart.save(update_fields=["updated_at"])


def remove_item(cart: Cart, item_id: int) -> None:
    item = _get_item(cart, item_id)
    product_id = item.product_id
    item.delete()
    cart.save(update_fields=["updated_at"])
    emit(
        "CART_ITEM_REMOVED",
        user=cart.user_id,
        session_key=cart.session_key or "",
        entity_id=product_id,
        payload={"product_id": product_id},
    )


def _get_item(cart: Cart, item_id: int) -> CartItem:
    # Looked up inside the caller's own cart, so another customer's item id is simply "not found".
    item = CartItem.objects.select_related("product").filter(cart=cart, pk=item_id).first()
    if item is None:
        raise CartError("Cart item not found", status_code=404)
    return item


@transaction.atomic
def merge_session_cart(user, session_key: str) -> Cart:
    """After login: move the anonymous cart's items into the user's cart.

    Quantities are added and capped at available stock. The anonymous cart is kept
    with status MERGED so history is not lost.
    """
    user_cart = get_active_cart(user=user)
    session_cart = Cart.objects.filter(session_key=session_key, status=Cart.Status.ACTIVE).first()
    if session_cart is None:
        return user_cart

    for item in session_cart.items.select_related("product"):
        product = item.product
        if product.status != Product.Status.ACTIVE or product.stock <= 0:
            continue
        existing = CartItem.objects.filter(cart=user_cart, product=product).first()
        wanted = (existing.quantity if existing else 0) + item.quantity
        quantity = min(wanted, product.stock, MAX_QUANTITY_PER_ITEM)
        if existing:
            existing.quantity = quantity
            existing.save(update_fields=["quantity", "updated_at"])
        else:
            CartItem.objects.create(cart=user_cart, product=product, quantity=quantity)

    session_cart.status = Cart.Status.MERGED
    session_cart.save(update_fields=["status", "updated_at"])
    user_cart.save(update_fields=["updated_at"])
    return user_cart


def cart_view(cart: Cart) -> dict:
    """The cart as the API returns it, priced from current product prices."""
    items = []
    subtotal = Decimal("0")
    for item in cart.items.select_related("product"):
        product = item.product
        line_total = money(product.price * item.quantity)
        subtotal += line_total
        items.append(
            {
                "id": item.id,
                "product_id": product.id,
                "name": product.name,
                "price": product.price,
                "image": product.image,
                "stock": product.stock,
                "quantity": item.quantity,
                "line_total": line_total,
            }
        )
    return {"id": cart.id, "items": items, **calculate_totals(subtotal)}
