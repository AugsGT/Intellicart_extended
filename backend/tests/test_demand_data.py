"""Demand numbers computed from real orders in the database."""
from datetime import datetime, time, timedelta, timezone as dt_timezone
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.db.models import Sum

from apps.demand_intelligence import data, services, statistics as st
from apps.demand_intelligence.detection import detect_demand_signals
from apps.events.models import OutboxEvent
from apps.inventory.models import Alert
from apps.orders.models import Order, OrderItem
from apps.products.models import Product
from tests.conftest import SHIPPING

pytestmark = pytest.mark.django_db


@pytest.fixture()
def sell(make_user):
    """sell(product, units, days_ago): a past order. days_ago=0 is the last complete day (yesterday)."""
    buyer = make_user()

    def _sell(product, units, days_ago=0, status="CONFIRMED", payment="PAID", today=False):
        day = data.last_complete_day() - timedelta(days=days_ago) if not today else data.last_complete_day() + timedelta(days=1)
        total = product.price * units
        order = Order.objects.create(user=buyer, status=status, payment_status=payment, payment_method="cod",
                                     subtotal=total, tax=0, shipping=0, total=total, **SHIPPING)
        OrderItem.objects.create(order=order, product=product, name=product.name, unit_price=product.price, quantity=units)
        Order.objects.filter(pk=order.pk).update(created_at=datetime.combine(day, time(12, 0), tzinfo=dt_timezone.utc))
        return order

    return _sell


def analysis(product):
    return next(p for p in services.analyze_all() if p["product_id"] == product.id)


# ---------- only real, completed demand counts ----------

def test_cancelled_failed_and_todays_orders_are_not_demand(make_product, sell):
    product = make_product(stock=100)
    sell(product, 4, days_ago=1)
    sell(product, 50, days_ago=1, status="CANCELLED", payment="REFUNDED")
    sell(product, 50, days_ago=1, status="FAILED", payment="FAILED")
    sell(product, 50, today=True)                                    # today is still in progress

    rows = data.daily_product_rows(35)[product.id]
    assert [(r["units"]) for r in rows] == [4]
    assert analysis(product)["recent_units"] == 4


def test_daily_series_fills_zero_days_and_keeps_products_apart(make_product, sell):
    a, b = make_product("A", stock=100), make_product("B", stock=100)
    sell(a, 2, days_ago=0)
    sell(a, 5, days_ago=3)
    sell(b, 9, days_ago=3)

    end = data.last_complete_day()
    rows = data.daily_product_rows(7)
    assert data.fill_days(rows[a.id], 7, end) == [0, 0, 0, 5, 0, 0, 2]
    assert data.fill_days(rows[b.id], 7, end) == [0, 0, 0, 9, 0, 0, 0]


def test_analysis_matches_hand_calculation(make_product, sell):
    product = make_product(stock=60)
    for days_ago in range(7, 35):                    # baseline: 2 a day for 28 days
        sell(product, 2, days_ago=days_ago)
    for days_ago in range(0, 7):                     # recent: 4 a day
        sell(product, 4, days_ago=days_ago)

    result = analysis(product)
    assert (result["recent_units"], result["baseline_units"]) == (28, 56)
    assert (result["recent_daily_average"], result["baseline_daily_average"], result["change_pct"]) == (4.0, 2.0, 100.0)
    assert result["trend"] == "increasing" and result["days_of_cover"] == 15.0 and result["stockout_risk"] == "ok"


# ---------- series for the dashboard ----------

def test_weekly_and_monthly_totals_add_up_to_the_daily_totals(make_product, sell):
    product = make_product(price="100.00", stock=1000)
    for days_ago in (0, 1, 2, 9, 20, 45):
        sell(product, 3, days_ago=days_ago)

    detail = services.product_detail(product)
    assert len(detail["daily"]) == 90 and detail["daily"][-1]["units"] == 3
    assert sum(d["units"] for d in detail["daily"]) == 18
    assert sum(w["units"] for w in detail["weekly"]) == 18 and sum(m["units"] for m in detail["monthly"]) == 18
    assert sum(w["revenue"] for w in detail["weekly"]) == pytest.approx(1800.0)

    total_daily = services.sales_series("day", 90)["series"]
    assert sum(r["units"] for r in total_daily) == 18
    weekly = services.sales_series("week", 90)["series"]
    assert sum(r["units"] for r in weekly) == 18 and all(date_ok(r["period"]) for r in weekly)


def date_ok(text):
    return datetime.fromisoformat(text).weekday() == 0            # weekly buckets start on a Monday


def test_moving_average_series_in_the_detail(make_product, sell):
    product = make_product(stock=1000)
    for days_ago in range(0, 7):
        sell(product, 7, days_ago=days_ago)
    detail = services.product_detail(product)
    last = detail["daily"][-1]
    assert last["units"] == 7 and last["moving_average_7d"] == 7.0
    assert detail["daily"][-8]["moving_average_7d"] == 0.0         # before the burst the average is zero


# ---------- overview and restocking ----------

def test_overview_counts_each_kind_of_signal_separately(make_product, sell):
    rising = make_product("Rising", stock=500)
    shortage = make_product("Shortage", stock=2, threshold=5)
    soon = make_product("Soon", stock=20)
    for days_ago in range(7, 35):
        sell(rising, 2, days_ago=days_ago)
        sell(soon, 2, days_ago=days_ago)
    for days_ago in range(0, 7):
        sell(rising, 4, days_ago=days_ago)
        sell(soon, 2, days_ago=days_ago)

    counts = services.overview()["counts"]
    assert counts["increasing"] == 1 and counts["stock_shortages"] == 1
    assert counts["predicted_stockouts"] == 1          # "Soon": 20 units at 2/day = 10 days
    names = [p["name"] for p in services.overview()["at_risk"]]
    assert names == ["Soon"]


def test_restock_recommendations_put_the_most_urgent_first(make_product, sell):
    urgent, soon, fine = make_product("Urgent", stock=6), make_product("Soon", stock=20), make_product("Fine", stock=500)
    for product in (urgent, soon, fine):
        for days_ago in range(0, 35):
            sell(product, 2, days_ago=days_ago)

    recommendations = services.restock_recommendations()
    assert [r["name"] for r in recommendations] == ["Urgent", "Soon"]
    assert recommendations[0]["restock"]["urgency"] == "urgent" and recommendations[0]["restock"]["quantity"] == 54   # ceil(2*30) - 6


def test_computing_every_product_uses_a_fixed_number_of_queries(make_product, sell, django_assert_max_num_queries):
    for number in range(15):
        product = make_product(f"P{number}", stock=50)
        sell(product, 2, days_ago=1)
    with django_assert_max_num_queries(4):
        assert len(services.analyze_all()) == 15


# ---------- detection: events and alerts ----------

def make_spiking_product(make_product, sell, stock=500):
    product = make_product("Spiker", stock=stock)
    for days_ago in range(3, 35):
        sell(product, 1, days_ago=days_ago)
    for days_ago in range(0, 3):
        sell(product, 4, days_ago=days_ago)
    return product


def test_a_spike_raises_one_alert_and_one_event_then_stays_quiet(make_product, sell):
    product = make_spiking_product(make_product, sell)
    OutboxEvent.objects.all().delete()

    assert detect_demand_signals() == {"spikes_flagged": 1, "stockout_risks_flagged": 0}
    event = OutboxEvent.objects.get(event_type="DEMAND_SPIKE_DETECTED")
    assert event.entity_id == product.id
    assert event.payload["recent_daily_average"] == 4.0 and event.payload["baseline_daily_average"] == pytest.approx(1.0, abs=0.2)
    alert = Alert.objects.get(type="DEMAND_SPIKE")
    assert alert.product_id == product.id and "Sudden demand spike" in alert.message

    assert detect_demand_signals()["spikes_flagged"] == 0               # same spike: not reported again
    assert OutboxEvent.objects.filter(event_type="DEMAND_SPIKE_DETECTED").count() == 1


def test_the_spike_alert_closes_when_the_spike_is_over(make_product, sell):
    product = make_spiking_product(make_product, sell)
    detect_demand_signals()
    assert Alert.objects.filter(type="DEMAND_SPIKE", resolved=False).count() == 1

    # Time moves on: the burst orders are now 4+ days old, so the last 3 days are quiet.
    for order in Order.objects.all():
        Order.objects.filter(pk=order.pk).update(created_at=order.created_at - timedelta(days=4))
    detect_demand_signals()
    assert Alert.objects.filter(type="DEMAND_SPIKE", resolved=False).count() == 0
    assert Alert.objects.filter(type="DEMAND_SPIKE", resolved=True).count() == 1


def test_a_predicted_stockout_raises_a_separate_alert_and_it_closes_after_restocking(make_product, sell):
    from apps.inventory import services as inventory

    product = make_product("Running out", stock=10)
    for days_ago in range(0, 35):
        sell(product, 2, days_ago=days_ago)

    assert detect_demand_signals()["stockout_risks_flagged"] == 1
    alert = Alert.objects.get(type="STOCKOUT_RISK")
    assert alert.severity == "high" and "Running out may run out soon" in alert.message
    assert not Alert.objects.filter(type="DEMAND_SPIKE").exists()
    assert detect_demand_signals()["stockout_risks_flagged"] == 0

    inventory.adjust_stock(product.id, 200, "RESTOCK")
    detect_demand_signals()
    assert not Alert.objects.filter(type="STOCKOUT_RISK", resolved=False).exists()


def test_the_demand_event_follows_its_contract(make_product, sell):
    from apps.events import contracts

    make_spiking_product(make_product, sell)
    detect_demand_signals()
    payload = OutboxEvent.objects.get(event_type="DEMAND_SPIKE_DETECTED").payload
    assert all(key in payload for key in contracts.EVENTS["DEMAND_SPIKE_DETECTED"][1])


# ---------- the sample-history generator ----------

def test_the_sample_history_produces_every_kind_of_signal_and_a_consistent_ledger(make_category, make_product):
    category = make_category("Sample")
    names = ["Nimbus 14 Developer Laptop", "Forge 15 Gaming Laptop", "Pulse ANC Earbuds", "Pulse Go Earbuds", "Basic Task Chair", "Orbit X Phone"]
    products = {n: make_product(n, "1000", stock=10, category=category, threshold=5) for n in names}

    call_command("seed_order_history", "--seed", "42")
    results = {p["name"]: p for p in services.analyze_all()}

    assert results["Nimbus 14 Developer Laptop"]["trend"] == "increasing"
    assert results["Forge 15 Gaming Laptop"]["trend"] == "decreasing"
    assert results["Pulse ANC Earbuds"]["spike"] is True
    assert results["Pulse Go Earbuds"]["stockout_risk"] == "critical"
    assert results["Basic Task Chair"]["stock_state"] == "low_stock"
    assert results["Orbit X Phone"]["trend"] in ("stable", "insufficient_data") and not results["Orbit X Phone"]["spike"]

    for product in Product.objects.all():          # the ledger always explains the stock level
        assert product.stock_movements.aggregate(total=Sum("change"))["total"] == product.stock
        assert product.stock >= 0
    assert Order.objects.filter(status__in=["CANCELLED", "FAILED"]).exists()          # present in the data...
    assert Order.objects.successful().count() < Order.objects.count()                  # ...but not counted


def test_the_generator_does_not_duplicate_and_replace_regenerates(make_category, make_product):
    category = make_category("Sample")
    make_product("Orbit X Phone", "1000", stock=10, category=category)

    call_command("seed_order_history", "--seed", "1")
    first = Order.objects.count()
    call_command("seed_order_history", "--seed", "1")                      # again: nothing happens
    assert Order.objects.count() == first
    call_command("seed_order_history", "--seed", "1", "--replace")        # regenerate: same data, no leftovers
    assert Order.objects.count() == first
    product = Product.objects.get()
    assert product.stock_movements.aggregate(total=Sum("change"))["total"] == product.stock
