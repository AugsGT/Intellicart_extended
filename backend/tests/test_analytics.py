from decimal import Decimal

import pytest

from apps.orders import services

pytestmark = pytest.mark.django_db


def test_overview_is_staff_only(client, auth_client, make_user):
    assert client.get("/analytics/overview/").status_code == 401
    assert auth_client(make_user()).get("/analytics/overview/").status_code == 403
    assert auth_client(make_user(role="OPERATIONS")).get("/analytics/overview/").status_code == 200


def test_overview_counts_only_successful_orders(auth_client, make_user, make_product, place_order):
    product = make_product(price="100.00", stock=10, threshold=1)
    user = make_user()
    place_order(user, (product, 1))                       # counts
    cancelled = place_order(user, (product, 1))
    services.change_status(cancelled.id, "CANCELLED")     # does not count, stock restored

    data = auth_client(make_user(role="ADMIN")).get("/analytics/overview/").json()
    assert data["total_orders"] == 1
    assert Decimal(data["total_revenue"]) == Decimal("100.00") + Decimal("18.00") + Decimal("49.00")
    assert data["total_stock_units"] == 9
    assert data["open_alerts"] == 0
