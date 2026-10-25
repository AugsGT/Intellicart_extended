from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.cart import services as cart_services
from apps.orders import services
from apps.orders.models import Order
from tests.conftest import SHIPPING

pytestmark = pytest.mark.django_db


def test_requires_login(client):
    assert client.get("/customer-intelligence/me/purchase-history/").status_code == 401


def test_new_customer_has_empty_history(auth_client, make_user):
    data = auth_client(make_user()).get("/customer-intelligence/me/purchase-history/").json()
    assert data["orders"] == []
    assert data["stats"]["order_count"] == 0 and Decimal(data["stats"]["total_spent"]) == 0
    assert data["stats"]["average_days_between_orders"] is None


def test_only_successful_orders_count_as_purchases(auth_client, make_user, make_product, place_order):
    user = make_user()
    pen, book = make_product("Pen", price="10.00", stock=20), make_product("Book", price="500.00", stock=20)

    place_order(user, (pen, 3))
    kept = place_order(user, (book, 1), (pen, 1))
    cancelled = place_order(user, (book, 2))
    services.change_status(cancelled.id, "CANCELLED")
    cart_services.add_item(cart_services.get_active_cart(user=user), book.id, 1)
    with pytest.raises(services.PaymentDeclined):
        services.checkout(user, dict(SHIPPING), "card", "4000000000000002")

    data = auth_client(user).get("/customer-intelligence/me/purchase-history/").json()
    stats = data["stats"]
    assert stats["order_count"] == 2
    assert stats["items_purchased"] == 5            # 3 pens + 1 book + 1 pen; cancelled and failed excluded
    assert stats["cancelled_orders"] == 1 and stats["failed_orders"] == 1
    assert Decimal(stats["total_spent"]) == sum(o.total for o in Order.objects.successful())
    assert {o["order_id"] for o in data["orders"]} == {o.id for o in Order.objects.successful()}
    assert kept.id in {o["order_id"] for o in data["orders"]}
    assert cancelled.id not in {o["order_id"] for o in data["orders"]}

    top = stats["top_products"][0]
    assert top["name"] == "Pen" and top["quantity"] == 4


def test_purchase_frequency(auth_client, make_user, make_product, place_order):
    user, product = make_user(), make_product(stock=10)
    first, second = place_order(user, (product, 1)), place_order(user, (product, 1))
    Order.objects.filter(pk=first.pk).update(created_at=timezone.now() - timedelta(days=30))
    Order.objects.filter(pk=second.pk).update(created_at=timezone.now() - timedelta(days=10))

    stats = auth_client(user).get("/customer-intelligence/me/purchase-history/").json()["stats"]
    assert stats["average_days_between_orders"] == 20.0


def test_customers_cannot_see_each_others_history(auth_client, make_user, make_product, place_order):
    alice, bob = make_user(), make_user()
    place_order(alice, (make_product(), 1))
    assert auth_client(bob).get("/customer-intelligence/me/purchase-history/").json()["orders"] == []


def test_staff_history_endpoint_is_staff_only(auth_client, make_user, make_product, place_order):
    alice = make_user()
    place_order(alice, (make_product(), 1))
    url = f"/customer-intelligence/customers/{alice.id}/purchase-history/"
    assert auth_client(make_user()).get(url).status_code == 403
    assert auth_client(make_user(role="OPERATIONS")).get(url).json()["stats"]["order_count"] == 1
