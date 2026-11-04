from datetime import datetime, time, timedelta, timezone as dt_timezone
from decimal import Decimal

import pytest

from apps.demand_intelligence import data
from apps.orders.models import Order, OrderItem
from tests.conftest import SHIPPING

pytestmark = pytest.mark.django_db

DEMAND_URLS = ["/demand/overview/", "/demand/products/", "/demand/restock/", "/demand/sales/"]


@pytest.fixture()
def sell(make_user):
    buyer = make_user()

    def _sell(product, units, days_ago=0, status="CONFIRMED", payment="PAID"):
        day = data.last_complete_day() - timedelta(days=days_ago)
        total = product.price * units
        order = Order.objects.create(user=buyer, status=status, payment_status=payment, payment_method="cod",
                                     subtotal=total, tax=0, shipping=0, total=total, **SHIPPING)
        OrderItem.objects.create(order=order, product=product, name=product.name, unit_price=product.price, quantity=units)
        Order.objects.filter(pk=order.pk).update(created_at=datetime.combine(day, time(12, 0), tzinfo=dt_timezone.utc))
        return order

    return _sell


# ---------- access ----------

@pytest.mark.parametrize("url", DEMAND_URLS + ["/demand/products/{pid}/", "/analytics/products/", "/analytics/sales/"])
def test_demand_and_analytics_are_staff_only(client, auth_client, make_user, make_product, url):
    url = url.format(pid=make_product().id)
    assert client.get(url).status_code == 401
    assert auth_client(make_user()).get(url).status_code == 403
    ops = auth_client(make_user(role="OPERATIONS")).get(url)
    assert ops.status_code == 200
    assert auth_client(make_user(role="ADMIN")).get(url).status_code == 200


# ---------- demand endpoints ----------

def test_product_list_filters_and_ordering(auth_client, make_user, make_product, sell):
    fast, slow = make_product("Fast", stock=10), make_product("Slow", stock=500)
    for days_ago in range(0, 35):
        sell(fast, 3, days_ago=days_ago)
        sell(slow, 1, days_ago=days_ago)
    api = auth_client(make_user(role="OPERATIONS"))

    rows = api.get("/demand/products/").json()
    assert [r["name"] for r in rows] == ["Fast", "Slow"]                           # fastest seller first
    assert {r["name"] for r in api.get("/demand/products/?risk=critical").json()} == {"Fast"}
    assert api.get("/demand/products/?risk=ok").json()[0]["name"] == "Slow"
    assert api.get("/demand/products/?trend=increasing").json() == []
    assert set(rows[0]) >= {"trend", "spike", "recent_daily_average", "baseline_daily_average", "change_pct", "days_of_cover",
                            "stockout_risk", "predicted_stockout_date", "restock", "signals", "comparison"}


def test_product_detail_has_series_and_404s_for_unknown_products(auth_client, make_user, make_product, sell):
    product = make_product(stock=50)
    sell(product, 5, days_ago=2)
    api = auth_client(make_user(role="OPERATIONS"))
    body = api.get(f"/demand/products/{product.id}/").json()
    assert len(body["daily"]) == 90 and body["weekly"] and body["monthly"]
    assert sum(d["units"] for d in body["daily"]) == 5
    assert api.get("/demand/products/99999/").status_code == 404


def test_restock_endpoint_lists_only_what_needs_ordering(auth_client, make_user, make_product, sell):
    needs, fine = make_product("Needs", stock=5), make_product("Fine", stock=900)
    for days_ago in range(0, 35):
        sell(needs, 2, days_ago=days_ago)
        sell(fine, 2, days_ago=days_ago)
    rows = auth_client(make_user(role="OPERATIONS")).get("/demand/restock/").json()
    assert [r["name"] for r in rows] == ["Needs"] and rows[0]["restock"]["quantity"] > 0


def test_sales_series_granularity_and_validation(auth_client, make_user, make_product, sell):
    product = make_product(price="10.00", stock=100)
    sell(product, 2, days_ago=1)
    sell(product, 3, days_ago=8)
    api = auth_client(make_user(role="OPERATIONS"))

    day = api.get("/demand/sales/?granularity=day&days=30").json()
    assert day["granularity"] == "day" and [r["units"] for r in day["series"]] == [3, 2]
    assert Decimal(str(day["series"][0]["revenue"])) == Decimal("30")
    assert sum(r["units"] for r in api.get("/demand/sales/?granularity=week").json()["series"]) == 5
    assert sum(r["units"] for r in api.get("/demand/sales/?granularity=month").json()["series"]) == 5
    assert api.get("/demand/sales/?granularity=hour").status_code == 400
    assert api.get("/demand/sales/?days=abc").status_code == 400
    assert api.get("/demand/sales/?days=100000").json()["days"] == 365          # clamped


def test_demand_alerts_appear_on_the_existing_alerts_endpoint(auth_client, make_user, make_product, sell):
    from apps.demand_intelligence.detection import detect_demand_signals

    product = make_product("Hot", stock=500)
    for days_ago in range(3, 35):
        sell(product, 1, days_ago=days_ago)
    for days_ago in range(0, 3):
        sell(product, 4, days_ago=days_ago)
    detect_demand_signals()
    alerts = auth_client(make_user(role="OPERATIONS")).get("/alerts/?resolved=false").json()["results"]
    assert [a["type"] for a in alerts] == ["DEMAND_SPIKE"]


# ---------- analytics ----------

def test_product_behaviour_counts_events(auth_client, make_user, make_product, make_event):
    lamp, desk = make_product("Lamp"), make_product("Desk")
    for _ in range(3):
        make_event("PRODUCT_VIEWED", session="a", entity=lamp.id)
    make_event("PRODUCT_VIEWED", session="a", entity=desk.id)
    make_event("CART_ITEM_ADDED", session="a", entity=desk.id)
    for query in ("lamp", "lamp", "chair"):
        make_event("PRODUCT_SEARCHED", session="a", payload={"query": query})

    body = auth_client(make_user(role="OPERATIONS")).get("/analytics/products/").json()
    assert body["most_viewed"][0] == {"product_id": lamp.id, "name": "Lamp", "views": 3}
    assert body["most_added_to_cart"] == [{"product_id": desk.id, "name": "Desk", "adds": 1}]
    assert body["most_searched"] == [{"query": "lamp", "count": 2}, {"query": "chair", "count": 1}]


def test_sales_overview_counts_only_successful_orders(auth_client, make_user, make_category, make_product, make_event, sell):
    gadgets = make_category("Gadgets")
    product = make_product("Gadget", "100.00", stock=100, category=gadgets)
    sell(product, 2, days_ago=1)                                                        # 200
    sell(product, 1, days_ago=2)                                                        # 100
    sell(product, 9, days_ago=1, status="CANCELLED", payment="REFUNDED")                # ignored
    sell(product, 9, days_ago=1, status="FAILED", payment="FAILED")                     # ignored

    for _ in range(4):
        make_event("CHECKOUT_STARTED", session="s")
    for _ in range(3):
        make_event("ORDER_COMPLETED", session="s", payload={"order_id": 1})
    make_event("PRODUCT_VIEWED", session="viewer-1", entity=product.id)
    make_event("PRODUCT_VIEWED", session="viewer-2", entity=product.id)
    make_event("ORDER_COMPLETED", session="viewer-1", payload={"order_id": 2})

    body = auth_client(make_user(role="OPERATIONS")).get("/analytics/sales/").json()
    assert Decimal(body["average_order_value"]) == Decimal("150")                       # (200 + 100) / 2 orders
    assert body["sales_by_category"] == [{"category": "Gadgets", "revenue": "300.00", "units": 3}]
    assert body["checkout"] == {"checkout_started": 4, "orders_completed": 4, "drop_off_rate": 0.0}
    assert body["conversion"] == {"customers_who_viewed": 2, "customers_who_bought": 1, "conversion_rate": 0.5}


def test_conversion_matches_a_logged_in_viewer_to_their_own_purchase(make_user, make_event):
    from apps.analytics.services import conversion_counts

    buyer, browser = make_user(), make_user()
    make_event("PRODUCT_VIEWED", user=buyer, session="phone-browser", entity=1)           # viewed while logged in
    make_event("ORDER_COMPLETED", user=buyer, payload={"order_id": 1})                    # purchase carries the account only
    make_event("PRODUCT_VIEWED", user=browser, session="laptop-browser", entity=1)        # viewed, never bought
    make_event("PRODUCT_VIEWED", session="guest-1", entity=1)                             # anonymous, never bought

    assert conversion_counts() == (3, 1)
