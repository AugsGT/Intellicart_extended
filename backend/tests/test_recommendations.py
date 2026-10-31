import json
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.cart import services as cart_services
from apps.events.consumer import process_message
from apps.events.models import OutboxEvent
from apps.orders import services as order_services
from apps.recommendations import services
from tests.conftest import SHIPPING

pytestmark = pytest.mark.django_db


def names(recommended):
    return [r.product.name for r in recommended]


# ---------- similar ----------

def test_similar_products_share_category_prefer_stock_and_nearest_price(make_category, make_product):
    laptops, phones = make_category("Laptops"), make_category("Phones")
    base = make_product("Base", "50000", category=laptops)
    make_product("Near", "52000", category=laptops)
    make_product("Far", "90000", category=laptops)
    make_product("Sold out", "50100", category=laptops, stock=0)
    make_product("Archived", "50050", category=laptops, status="ARCHIVED")
    make_product("Phone", "50000", category=phones)

    recommended = services.similar_products(base)
    assert names(recommended) == ["Near", "Far", "Sold out"]       # in stock first, then nearest price
    assert all("Laptops" in r.reason for r in recommended)


# ---------- frequently bought together ----------

def test_frequently_bought_counts_only_successful_orders(make_user, make_product):
    laptop, mouse, bag, cable = (make_product(n, stock=20) for n in ("Laptop", "Mouse", "Bag", "Cable"))
    a, b, c = make_user(), make_user(), make_user()
    def buy(user, *products):
        cart = cart_services.get_active_cart(user=user)
        for product in products:
            cart_services.add_item(cart, product.id, 1)
        return order_services.checkout(user, dict(SHIPPING), "cod")

    buy(a, laptop, mouse)
    buy(b, laptop, mouse)
    cancelled = buy(c, laptop, bag)
    order_services.change_status(cancelled.id, "CANCELLED")
    cart_services.add_item(cart_services.get_active_cart(user=c), cable.id, 1)
    cart_services.add_item(cart_services.get_active_cart(user=c), laptop.id, 1)
    with pytest.raises(order_services.PaymentDeclined):
        order_services.checkout(c, dict(SHIPPING), "card", "4000000000000002")

    recommended = services.frequently_bought_with(laptop)
    assert names(recommended) == ["Mouse"]                      # cancelled (Bag) and failed (Cable) are ignored
    assert recommended[0].reason == "Bought together in 2 orders"


# ---------- substitutes ----------

def test_substitutes_only_when_product_is_low_or_out(make_category, make_product):
    chairs = make_category("Chairs")
    healthy = make_product("Healthy", "100", stock=50, category=chairs)
    assert services.substitutes(healthy) == []

    low = make_product("Low", "1000", stock=1, category=chairs, threshold=5)
    make_product("Close", "1100", stock=40, category=chairs)
    make_product("Distant", "5000", stock=40, category=chairs)
    make_product("Also low", "1000", stock=2, category=chairs, threshold=5)
    # In-stock same-category products by nearest price; "Also low" is excluded because it is low too.
    assert names(services.substitutes(low)) == ["Close", "Healthy", "Distant"]


# ---------- recently viewed ----------

def test_recently_viewed_for_a_guest_session_and_a_user(make_user, make_product, make_event):
    one, two, three = make_product("One"), make_product("Two"), make_product("Three")
    user = make_user()
    now = timezone.now()
    make_event("PRODUCT_VIEWED", session="s1", entity=one.id, when=now - timedelta(minutes=3))
    make_event("PRODUCT_VIEWED", session="s1", entity=two.id, when=now - timedelta(minutes=2))
    make_event("PRODUCT_VIEWED", user=user, entity=three.id, when=now - timedelta(minutes=1))
    make_event("PRODUCT_VIEWED", session="someone-else", entity=one.id)

    assert names(services.recently_viewed(None, "s1")) == ["Two", "One"]            # newest first
    assert names(services.recently_viewed(None, "s1", exclude_product_id=two.id)) == ["One"]
    assert names(services.recently_viewed(user.id, "")) == ["Three"]
    assert services.recently_viewed(None, "") == []


# ---------- cart based ----------

def test_cart_based_prefers_co_purchases_then_same_category(make_user, make_category, make_product):
    laptops = make_category("Laptops")
    laptop = make_product("Laptop", category=laptops, stock=20)
    mouse = make_product("Mouse", stock=20)
    other_laptop = make_product("Other laptop", category=laptops)
    make_product("Out of stock laptop", category=laptops, stock=0)

    buyer = make_user()
    cart = cart_services.get_active_cart(user=buyer)
    cart_services.add_item(cart, laptop.id, 1)
    cart_services.add_item(cart, mouse.id, 1)
    order_services.checkout(buyer, dict(SHIPPING), "cod")

    shopper = make_user()
    cart = cart_services.get_active_cart(user=shopper)
    cart_services.add_item(cart, laptop.id, 1)
    recommended = services.cart_based(cart)
    assert names(recommended) == ["Mouse", "Other laptop"]
    assert "bought with" in recommended[0].reason and recommended[1].product == other_laptop
    assert services.cart_based(cart_services.get_active_cart(user=make_user())) == []   # empty cart


# ---------- personalized ----------

def test_personalized_uses_bought_categories_and_skips_what_was_bought(make_user, make_category, make_product, place_order):
    laptops, chairs = make_category("Laptops"), make_category("Chairs")
    bought = make_product("Bought laptop", category=laptops)
    make_product("Another laptop", category=laptops)
    make_product("A chair", category=chairs)
    user = make_user()
    place_order(user, (bought, 1))

    recommended = services.personalized(user)
    assert names(recommended) == ["Another laptop"]             # only categories the customer showed interest in
    assert "Bought laptop" not in names(recommended)
    assert recommended[0].reason == "Because you bought items in Laptops"


def test_personalized_ignores_cancelled_orders_and_new_customers(make_user, make_category, make_product, place_order):
    laptops = make_category("Laptops")
    product = make_product("Laptop", category=laptops)
    make_product("Another laptop", category=laptops)
    user = make_user()
    order = place_order(user, (product, 1))
    order_services.change_status(order.id, "CANCELLED")

    assert services.personalized(user) == []                    # a cancelled purchase tells us nothing
    assert services.personalized(make_user()) == []


def test_personalized_falls_back_to_views_and_cart_activity(make_user, make_category, make_product, make_event):
    phones = make_category("Phones")
    seen = make_product("Seen phone", category=phones)
    make_product("Other phone", category=phones)
    user = make_user()
    make_event("PRODUCT_VIEWED", user=user, entity=seen.id)
    recommended = services.personalized(user)
    assert recommended[0].reason == "Because you viewed items in Phones"


# ---------- API, events and attribution ----------

def test_endpoints_return_reasons_and_record_that_a_list_was_served(client, make_category, make_product):
    laptops = make_category("Laptops")
    base = make_product("Base", category=laptops)
    make_product("Other", category=laptops)
    OutboxEvent.objects.all().delete()

    body = client.get(f"/recommendations/products/{base.id}/similar/").json()
    assert body[0]["name"] == "Other" and "reason" in body[0] and "attributes" in body[0]
    served = OutboxEvent.objects.get(event_type="RECOMMENDATION_GENERATED")
    assert served.payload["kind"] == "similar" and served.payload["product_ids"] == [body[0]["id"]]

    OutboxEvent.objects.all().delete()
    assert client.get(f"/recommendations/products/{base.id}/frequently-bought-together/").json() == []
    assert not OutboxEvent.objects.filter(event_type="RECOMMENDATION_GENERATED").exists()   # empty lists are not "served"
    assert client.get("/recommendations/products/99999/similar/").status_code == 404


def test_personalized_endpoint_needs_login(client, auth_client, make_user):
    assert client.get("/recommendations/personalized/").status_code == 401
    assert auth_client(make_user()).get("/recommendations/personalized/").json() == []


def test_click_is_recorded_and_validated(client, make_product):
    product = make_product()
    OutboxEvent.objects.all().delete()
    client.credentials(HTTP_X_SESSION_ID="s9")
    assert client.post("/recommendations/click/", {"kind": "similar", "product_id": product.id}, format="json").status_code == 202
    click = OutboxEvent.objects.get(event_type="RECOMMENDATION_CLICKED")
    assert (click.session_key, click.payload) == ("s9", {"kind": "similar", "product_id": product.id})
    assert client.post("/recommendations/click/", {"kind": "nonsense", "product_id": product.id}, format="json").status_code == 400
    assert client.post("/recommendations/click/", {"kind": "similar", "product_id": 99999}, format="json").status_code == 404


def test_purchase_of_a_clicked_recommendation_is_attributed(make_user, make_product, make_event, place_order):
    user = make_user()
    clicked, other = make_product("Clicked"), make_product("Other")
    make_event("RECOMMENDATION_CLICKED", user=user, entity=clicked.id, payload={"kind": "cart_based", "product_id": clicked.id})
    make_event(
        "RECOMMENDATION_CLICKED", user=user, entity=other.id, payload={"kind": "similar", "product_id": other.id},
        when=timezone.now() - timedelta(days=30),   # too old to count
    )
    order = place_order(user, (clicked, 1), (other, 1))
    OutboxEvent.objects.all().delete()

    completed = {"event_id": "6f1b7a00-0000-4000-8000-000000000001", "event_type": "ORDER_COMPLETED", "user_id": user.id,
                 "session_id": None, "entity_id": order.id, "payload": {"order_id": order.id, "total": "1"},
                 "timestamp": timezone.now().isoformat()}
    process_message(json.dumps(completed))

    purchased = list(OutboxEvent.objects.filter(event_type="RECOMMENDATION_PURCHASED"))
    assert len(purchased) == 1
    assert purchased[0].payload == {"kind": "cart_based", "product_id": clicked.id, "order_id": order.id}


def test_stats_show_rates_and_are_staff_only(client, auth_client, make_user, make_event):
    for _ in range(4):
        make_event("RECOMMENDATION_GENERATED", payload={"kind": "similar", "product_ids": [1]})
    make_event("RECOMMENDATION_CLICKED", payload={"kind": "similar", "product_id": 1})
    make_event("RECOMMENDATION_PURCHASED", payload={"kind": "similar", "product_id": 1, "order_id": 1})

    assert client.get("/recommendations/stats/").status_code == 401
    assert auth_client(make_user()).get("/recommendations/stats/").status_code == 403
    rows = {r["kind"]: r for r in auth_client(make_user(role="OPERATIONS")).get("/recommendations/stats/").json()}
    assert rows["similar"] == {"kind": "similar", "served": 4, "clicks": 1, "purchases": 1, "click_rate": 0.25, "purchase_rate": 1.0}
    assert rows["personalized"]["click_rate"] is None
