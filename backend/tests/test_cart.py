from decimal import Decimal

import pytest

from apps.cart.models import Cart, CartItem

pytestmark = pytest.mark.django_db


def session(client_factory, key):
    from rest_framework.test import APIClient

    api = APIClient()
    api.credentials(HTTP_X_SESSION_ID=key)
    return api


def add(api, product, quantity=1):
    return api.post("/cart/items/", {"product_id": product.id, "quantity": quantity}, format="json")


# ---------- anonymous carts ----------

def test_anonymous_cart_needs_a_session_header(client):
    assert client.get("/cart/").status_code == 400


def test_anonymous_cart_add_update_remove(make_product):
    product = make_product(price="10.00", stock=5)
    api = session(None, "browser-1")
    cart = add(api, product, 2).json()
    item_id = cart["items"][0]["id"]
    assert cart["items"][0]["quantity"] == 2

    assert api.patch(f"/cart/items/{item_id}/", {"quantity": 4}, format="json").json()["items"][0]["quantity"] == 4
    assert api.delete(f"/cart/items/{item_id}/").json()["items"] == []


def test_two_browsers_never_share_a_cart(make_product):
    product = make_product()
    add(session(None, "browser-1"), product)
    assert session(None, "browser-2").get("/cart/").json()["items"] == []


# ---------- ownership ----------

def test_customer_cannot_touch_another_customers_cart_item(auth_client, make_user, make_product):
    product = make_product()
    alice, bob = auth_client(make_user()), auth_client(make_user())
    item_id = add(alice, product).json()["items"][0]["id"]

    assert bob.patch(f"/cart/items/{item_id}/", {"quantity": 3}, format="json").status_code == 404
    assert bob.delete(f"/cart/items/{item_id}/").status_code == 404
    assert CartItem.objects.get(pk=item_id).quantity == 1
    assert bob.get("/cart/").json()["items"] == []


def test_logged_in_user_cannot_reach_a_session_cart_by_header(auth_client, make_user, make_product):
    product = make_product()
    add(session(None, "someone-elses-browser"), product)

    user_api = auth_client(make_user())
    user_api.credentials(HTTP_X_SESSION_ID="someone-elses-browser")
    assert user_api.get("/cart/").json()["items"] == []  # the token decides the owner, not the header


def test_user_cart_belongs_to_user_and_is_persistent(auth_client, make_user, make_product):
    user = make_user()
    product = make_product()
    add(auth_client(user), product)
    assert auth_client(user).get("/cart/").json()["items"][0]["product_id"] == product.id  # new "device"
    assert Cart.objects.get(user=user).session_key is None


# ---------- stock rules ----------

def test_cannot_add_more_than_stock(make_product):
    product = make_product(stock=2)
    api = session(None, "b")
    assert add(api, product, 3).status_code == 400
    assert add(api, product, 2).status_code == 201
    assert add(api, product, 1).status_code == 400  # 3 total > 2 in stock


def test_cannot_add_out_of_stock_or_archived_product(make_product):
    api = session(None, "b")
    assert add(api, make_product(stock=0)).status_code == 400
    assert add(api, make_product(name="Old", status="ARCHIVED")).status_code == 404


def test_quantity_must_be_positive(make_product):
    product = make_product()
    api = session(None, "b")
    assert add(api, product, 0).status_code == 400
    assert add(api, product, -1).status_code == 400


# ---------- totals ----------

def test_totals_with_tax_and_shipping(make_product):
    cart = add(session(None, "b"), make_product(price="100.00")).json()
    assert Decimal(cart["subtotal"]) == Decimal("100.00")
    assert Decimal(cart["tax"]) == Decimal("18.00")
    assert Decimal(cart["shipping"]) == Decimal("49.00")
    assert Decimal(cart["total"]) == Decimal("167.00")


def test_free_shipping_from_999(make_product):
    cart = add(session(None, "b"), make_product(price="999.00")).json()
    assert Decimal(cart["shipping"]) == Decimal("0.00")


def test_tax_is_rounded_to_two_places(make_product):
    cart = add(session(None, "b"), make_product(price="33.33")).json()
    assert Decimal(cart["tax"]) == Decimal("6.00")  # 5.9994 rounds to 6.00
    assert Decimal(cart["total"]) == Decimal("33.33") + Decimal("6.00") + Decimal("49.00")


# ---------- merge on login ----------

def test_merge_moves_session_items_into_user_cart(auth_client, make_user, make_product):
    shirt, mug = make_product("Shirt", stock=5), make_product("Mug", stock=5)
    add(session(None, "guest"), shirt, 2)

    user = make_user()
    api = auth_client(user)
    add(api, shirt, 1)
    add(api, mug, 1)
    api.credentials(HTTP_X_SESSION_ID="guest")
    merged = api.post("/cart/merge/").json()

    quantities = {i["name"]: i["quantity"] for i in merged["items"]}
    assert quantities == {"Shirt": 3, "Mug": 1}
    assert Cart.objects.get(session_key="guest").status == "MERGED"
    assert session(None, "guest").get("/cart/").json()["items"] == []  # a fresh empty cart


def test_merge_caps_quantity_at_stock(auth_client, make_user, make_product):
    product = make_product(stock=3)
    add(session(None, "guest"), product, 3)
    api = auth_client(make_user())
    add(api, product, 2)
    api.credentials(HTTP_X_SESSION_ID="guest")
    assert api.post("/cart/merge/").json()["items"][0]["quantity"] == 3


def test_merge_requires_login(make_product):
    assert session(None, "guest").post("/cart/merge/").status_code == 401
