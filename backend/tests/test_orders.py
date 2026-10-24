from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier

import pytest
from django.db import connection

from apps.cart import services as cart_services
from apps.cart.models import Cart
from apps.inventory.models import StockMovement
from apps.orders import services
from apps.orders.models import Order
from tests.conftest import SHIPPING

pytestmark = pytest.mark.django_db


def put_in_cart(api, product, quantity=1):
    return api.post("/cart/items/", {"product_id": product.id, "quantity": quantity}, format="json")


# ---------- checkout ----------

def test_checkout_requires_login(client, checkout_body):
    assert client.post("/orders/", checkout_body(), format="json").status_code == 401


def test_successful_checkout(auth_client, make_user, make_product, checkout_body):
    user, product = make_user(), make_product(price="100.00", stock=5)
    api = auth_client(user)
    put_in_cart(api, product, 2)

    response = api.post("/orders/", checkout_body(), format="json")
    assert response.status_code == 201, response.content
    order = response.json()
    assert order["status"] == "CONFIRMED" and order["payment_status"] == "PAID"
    assert Decimal(order["subtotal"]) == Decimal("200.00")
    assert Decimal(order["total"]) == Decimal("200.00") + Decimal("36.00") + Decimal("49.00")
    assert order["items"][0]["quantity"] == 2 and Decimal(order["items"][0]["unit_price"]) == Decimal("100.00")

    product.refresh_from_db()
    assert product.stock == 3
    movement = StockMovement.objects.filter(product=product).first()
    assert (movement.change, movement.reason, movement.reference) == (-2, "ORDER", f"order:{order['id']}")
    assert Cart.objects.get(user=user, status="CHECKED_OUT")  # kept as cart history
    assert api.get("/cart/").json()["items"] == []              # next cart is empty


def test_order_keeps_the_price_paid_after_the_product_price_changes(auth_client, make_user, make_product, checkout_body):
    user, product = make_user(), make_product(price="100.00")
    api = auth_client(user)
    put_in_cart(api, product)
    order_id = api.post("/orders/", checkout_body(), format="json").json()["id"]

    product.price = Decimal("250.00")
    product.save()
    assert Decimal(api.get(f"/orders/{order_id}/").json()["items"][0]["unit_price"]) == Decimal("100.00")


def test_checkout_with_empty_cart(auth_client, make_user, checkout_body):
    assert auth_client(make_user()).post("/orders/", checkout_body(), format="json").status_code == 400


def test_checkout_fails_cleanly_when_stock_ran_out(auth_client, make_user, make_product, checkout_body):
    user, product = make_user(), make_product(stock=3)
    api = auth_client(user)
    put_in_cart(api, product, 3)
    product.stock = 1   # someone else bought items since it was added to the cart
    product.save()

    response = api.post("/orders/", checkout_body(), format="json")
    assert response.status_code == 400 and "left in stock" in response.json()["detail"]
    assert not Order.objects.exists()
    assert Cart.objects.get(user=user).status == "ACTIVE"


def test_declined_card_records_failed_order_and_keeps_stock_and_cart(auth_client, make_user, make_product, checkout_body):
    user, product = make_user(), make_product(stock=5)
    api = auth_client(user)
    put_in_cart(api, product, 2)

    response = api.post("/orders/", checkout_body(payment_method="card", card_number="4000 0000 0000 0002"), format="json")
    assert response.status_code == 402
    assert response.json()["order"]["status"] == "FAILED"

    product.refresh_from_db()
    assert product.stock == 5
    assert not StockMovement.objects.filter(reason="ORDER").exists()
    assert Order.objects.get().payment_status == "FAILED"
    assert len(api.get("/cart/").json()["items"]) == 1  # can retry


@pytest.mark.parametrize(
    "overrides",
    [{"phone": "abc"}, {"postal_code": "!"}, {"payment_method": "bitcoin"}, {"payment_method": "card"}, {"full_name": ""}],
)
def test_checkout_validates_input(auth_client, make_user, make_product, checkout_body, overrides):
    api = auth_client(make_user())
    put_in_cart(api, make_product())
    assert api.post("/orders/", checkout_body(**overrides), format="json").status_code == 400
    assert not Order.objects.exists()


# ---------- ownership ----------

def test_customers_only_see_their_own_orders(auth_client, make_user, make_product, place_order):
    alice, bob = make_user(), make_user()
    order = place_order(alice, (make_product(), 1))

    assert [o["id"] for o in auth_client(alice).get("/orders/").json()["results"]] == [order.id]
    assert auth_client(bob).get("/orders/").json()["results"] == []
    assert auth_client(bob).get(f"/orders/{order.id}/").status_code == 404
    assert auth_client(alice).get(f"/orders/{order.id}/").status_code == 200


def test_customer_cannot_cancel_or_change_status_of_someone_elses_order(auth_client, make_user, make_product, place_order):
    alice, bob = make_user(), make_user()
    order = place_order(alice, (make_product(), 1))
    assert auth_client(bob).post(f"/orders/{order.id}/cancel/").status_code == 404
    assert auth_client(bob).patch(f"/orders/{order.id}/status/", {"status": "SHIPPED"}, format="json").status_code == 403
    order.refresh_from_db()
    assert order.status == "CONFIRMED"


def test_staff_can_see_any_order_but_anonymous_cannot(client, auth_client, make_user, make_product, place_order):
    order = place_order(make_user(), (make_product(), 1))
    assert client.get(f"/orders/{order.id}/").status_code == 401
    assert auth_client(make_user(role="OPERATIONS")).get(f"/orders/{order.id}/").status_code == 200
    assert auth_client(make_user()).get("/orders/admin/all/").status_code == 403
    assert auth_client(make_user(role="ADMIN")).get("/orders/admin/all/").json()["count"] == 1


# ---------- lifecycle ----------

def test_staff_moves_order_through_its_lifecycle(auth_client, make_user, make_product, place_order):
    order = place_order(make_user(), (make_product(), 1))
    ops = auth_client(make_user(role="OPERATIONS"))
    assert ops.patch(f"/orders/{order.id}/status/", {"status": "SHIPPED"}, format="json").json()["status"] == "SHIPPED"
    assert ops.patch(f"/orders/{order.id}/status/", {"status": "DELIVERED"}, format="json").json()["status"] == "DELIVERED"


@pytest.mark.parametrize("path", [("DELIVERED",), ("CONFIRMED", "CONFIRMED")])
def test_invalid_transitions_are_rejected(auth_client, make_user, make_product, place_order, path):
    order = place_order(make_user(), (make_product(), 1))
    ops = auth_client(make_user(role="OPERATIONS"))
    assert ops.patch(f"/orders/{order.id}/status/", {"status": path[0]}, format="json").status_code == 400
    assert ops.patch(f"/orders/{order.id}/status/", {"status": "banana"}, format="json").status_code == 400
    order.refresh_from_db()
    assert order.status == "CONFIRMED"


def test_delivered_order_is_final(auth_client, make_user, make_product, place_order):
    order = place_order(make_user(), (make_product(), 1))
    ops = auth_client(make_user(role="OPERATIONS"))
    for status in ("SHIPPED", "DELIVERED"):
        ops.patch(f"/orders/{order.id}/status/", {"status": status}, format="json")
    assert ops.patch(f"/orders/{order.id}/status/", {"status": "CANCELLED"}, format="json").status_code == 400


def test_cancelling_restores_stock_and_refunds(auth_client, make_user, make_product, place_order):
    user, product = make_user(), make_product(stock=5)
    order = place_order(user, (product, 2))
    product.refresh_from_db()
    assert product.stock == 3

    response = auth_client(user).post(f"/orders/{order.id}/cancel/")
    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED" and response.json()["payment_status"] == "REFUNDED"
    product.refresh_from_db()
    assert product.stock == 5
    assert StockMovement.objects.filter(product=product).first().reason == "CANCELLATION"


def test_cancelling_twice_does_not_restock_twice(auth_client, make_user, make_product, place_order):
    user, product = make_user(), make_product(stock=5)
    order = place_order(user, (product, 2))
    api = auth_client(user)
    assert api.post(f"/orders/{order.id}/cancel/").status_code == 200
    assert api.post(f"/orders/{order.id}/cancel/").status_code == 400
    product.refresh_from_db()
    assert product.stock == 5


def test_customer_cannot_cancel_after_shipping(auth_client, make_user, make_product, place_order):
    user = make_user()
    order = place_order(user, (make_product(), 1))
    auth_client(make_user(role="OPERATIONS")).patch(f"/orders/{order.id}/status/", {"status": "SHIPPED"}, format="json")
    assert auth_client(user).post(f"/orders/{order.id}/cancel/").status_code == 400


def test_successful_queryset_excludes_cancelled_and_failed(make_user, make_product, place_order):
    user, product = make_user(), make_product(stock=10)
    kept = place_order(user, (product, 1))
    cancelled = place_order(user, (product, 1))
    services.change_status(cancelled.id, "CANCELLED")
    with pytest.raises(services.PaymentDeclined):
        cart_services.add_item(cart_services.get_active_cart(user=user), product.id, 1)
        services.checkout(user, dict(SHIPPING), "card", "4000000000000002")

    assert list(Order.objects.successful()) == [kept]
    assert Order.objects.count() == 3


# ---------- concurrency ----------

@pytest.mark.django_db(transaction=True)
def test_two_customers_cannot_both_buy_the_last_unit(make_user, make_product):
    product = make_product(stock=1)
    users = [make_user(), make_user()]
    for user in users:
        cart_services.add_item(cart_services.get_active_cart(user=user), product.id, 1)

    barrier = Barrier(2)

    def buy(user):
        try:
            barrier.wait(timeout=10)
            services.checkout(user, dict(SHIPPING), "cod")
            return "ok"
        except services.CheckoutError:
            return "refused"
        finally:
            connection.close()  # each thread has its own database connection

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = sorted(pool.map(buy, users))

    product.refresh_from_db()
    assert results == ["ok", "refused"]
    assert product.stock == 0
    assert Order.objects.successful().count() == 1
    assert StockMovement.objects.filter(reason="ORDER").count() == 1


@pytest.mark.django_db(transaction=True)
def test_stock_never_goes_negative_under_many_simultaneous_checkouts(make_user, make_product):
    product = make_product(stock=3)
    users = [make_user() for _ in range(8)]
    for user in users:
        cart_services.add_item(cart_services.get_active_cart(user=user), product.id, 1)

    barrier = Barrier(len(users))

    def buy(user):
        try:
            barrier.wait(timeout=10)
            services.checkout(user, dict(SHIPPING), "cod")
            return "ok"
        except services.CheckoutError:
            return "refused"
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=len(users)) as pool:
        results = list(pool.map(buy, users))

    product.refresh_from_db()
    assert results.count("ok") == 3 and results.count("refused") == 5
    assert product.stock == 0
    ledger = sum(StockMovement.objects.filter(product=product).values_list("change", flat=True))
    assert ledger == product.stock
