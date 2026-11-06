import logging
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from django.core.cache import cache
from django.db import connection
from django.urls import URLResolver, get_resolver
from rest_framework.test import APIClient

from apps.cart import services as cart_services
from apps.orders import services as order_services
from apps.orders.models import Order
from apps.products.models import Product
from tests.conftest import SHIPPING

pytestmark = pytest.mark.django_db

METHODS = ["get", "post", "put", "patch", "delete"]


# ---------- every endpoint, systematically ----------

def all_routes():
    """Every route in the project as a concrete path (converters replaced by example values)."""
    def walk(patterns, prefix=""):
        for pattern in patterns:
            route = str(pattern.pattern)
            if isinstance(pattern, URLResolver):
                yield from walk(pattern.url_patterns, prefix + route)
            else:
                yield prefix + route

    routes = []
    for route in walk(get_resolver().url_patterns):
        if route.startswith("admin/"):
            continue
        for converter in ("<int:pk>", "<int:product_id>", "<int:item_id>", "<int:user_id>"):
            route = route.replace(converter, "1")
        routes.append("/" + route)
    return sorted(set(routes))


# The ONLY operations a visitor who is not logged in may perform. Everything else must answer 401.
PUBLIC = {
    ("get", "/health/"), ("post", "/auth/login/"), ("post", "/auth/refresh/"), ("post", "/users/register/"),
    ("get", "/categories/"), ("get", "/categories/1/"), ("get", "/categories/1/attributes/"),
    ("get", "/products/"), ("get", "/products/1/"),
    ("get", "/cart/"), ("post", "/cart/items/"), ("patch", "/cart/items/1/"), ("delete", "/cart/items/1/"),
    ("get", "/recommendations/products/1/similar/"), ("get", "/recommendations/products/1/frequently-bought-together/"),
    ("get", "/recommendations/products/1/substitutes/"), ("get", "/recommendations/recently-viewed/"),
    ("get", "/recommendations/cart-based/"), ("post", "/recommendations/click/"),
    ("post", "/events/checkout-started/"),
    ("get", "/interventions/active/"), ("post", "/interventions/1/dismiss/"), ("post", "/interventions/1/click/"),
}


def test_the_route_list_is_complete_enough_to_trust():
    routes = all_routes()
    assert len(routes) > 60
    for expected in ("/orders/", "/audit/", "/ops-assistant/conversations/", "/demand/overview/", "/assistant/conversations/1/confirm/"):
        assert expected in routes


def test_anonymous_visitors_are_refused_everywhere_except_the_public_list():
    client = APIClient()
    problems = []
    for path in all_routes():
        for method in METHODS:
            cache.clear()                                   # the sweep makes hundreds of requests; keep rate limits out of the way
            status = getattr(client, method)(path, {}, format="json").status_code
            if (method, path) in PUBLIC:
                if status >= 500:
                    problems.append(f"{method.upper()} {path} (public) crashed with {status}")
            elif status not in (401, 403, 405):
                problems.append(f"{method.upper()} {path} answered {status} to an anonymous visitor")
    assert problems == []


STAFF_ONLY_PREFIXES = (
    "/inventory/", "/alerts/", "/demand/", "/analytics/", "/audit/", "/ops-assistant/", "/orders/admin/", "/orders/1/status/",
    "/customer-intelligence/customers/", "/customer-intelligence/high-intent/", "/recommendations/stats/",
)
STAFF_ONLY_EXACT = {"/users/", "/users/1/", "/events/", "/events/dead-letters/", "/interventions/"}
CATALOGUE_WRITES = {"/categories/", "/categories/1/", "/categories/attributes/", "/products/", "/products/1/"}


def test_customers_cannot_reach_staff_features_or_change_the_catalogue(make_user, make_product):
    make_product()
    customer = APIClient()
    customer.force_authenticate(user=make_user())
    problems = []
    for path in all_routes():
        for method in METHODS:
            staff_route = path.startswith(STAFF_ONLY_PREFIXES) or path in STAFF_ONLY_EXACT
            catalogue_write = path in CATALOGUE_WRITES and method != "get"
            if not (staff_route or catalogue_write):
                continue
            cache.clear()
            status = getattr(customer, method)(path, {}, format="json").status_code
            if status not in (403, 405):
                problems.append(f"{method.upper()} {path} answered {status} to a customer")
    assert problems == []


# ---------- errors never leak ----------

def test_an_unexpected_failure_is_logged_but_never_shown(client, monkeypatch, caplog):
    def explode(*args, **kwargs):
        raise RuntimeError("secret internals: database password is hunter2")

    monkeypatch.setattr("apps.products.views.services.search_products", explode)
    with caplog.at_level(logging.ERROR, logger="intellicart.errors"):
        response = client.get("/products/")
    assert response.status_code == 500
    assert response.json() == {"detail": "Something went wrong on our side. Please try again."}
    assert "hunter2" not in response.content.decode() and "Traceback" not in response.content.decode()
    assert "secret internals" in caplog.text                                     # the operator still gets the full story


def test_unknown_urls_get_a_json_404(client):
    response = client.get("/definitely/not/here/")
    assert response.status_code == 404 and response.json() == {"detail": "Not found."}


def test_responses_carry_security_headers(client):
    headers = client.get("/health/")
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["Referrer-Policy"] == "same-origin"


def test_oversized_request_bodies_are_rejected(client):
    huge = {"email": "a@example.com", "password": "x" * (2 * 1024 * 1024)}
    response = client.post("/auth/login/", huge, format="json")
    assert response.status_code == 413 and response.json() == {"detail": "The request body is too large."}


# ---------- brute force and abuse ----------

def test_registration_is_rate_limited(client):
    codes = [client.post("/users/register/", {"username": f"u{n}", "email": f"u{n}@example.com", "password": "Str0ng-pass-phrase"}, format="json").status_code
             for n in range(22)]
    assert codes[:20] == [201] * 20 and 429 in codes[20:]


def test_every_endpoint_has_a_default_rate_limit(settings):
    classes = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"]
    assert "rest_framework.throttling.AnonRateThrottle" in classes and "rest_framework.throttling.UserRateThrottle" in classes
    assert settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["login"] == "10/min"


# ---------- checkout idempotency ----------

def place(api, body, key=None):
    headers = {"HTTP_IDEMPOTENCY_KEY": key} if key else {}
    return api.post("/orders/", body, format="json", **headers)


def test_repeating_a_checkout_with_the_same_key_creates_one_order(auth_client, make_user, make_product, checkout_body):
    user, product = make_user(), make_product(stock=5)
    api = auth_client(user)
    api.post("/cart/items/", {"product_id": product.id, "quantity": 2}, format="json")

    first = place(api, checkout_body(), "attempt-1")
    second = place(api, checkout_body(), "attempt-1")                    # a double click, or a retry after a timeout
    assert (first.status_code, second.status_code) == (201, 200)
    assert first.json()["id"] == second.json()["id"]
    assert Order.objects.count() == 1
    product.refresh_from_db()
    assert product.stock == 3                                            # stock was taken once


def test_a_repeated_declined_payment_returns_the_same_failure_not_a_new_attempt(auth_client, make_user, make_product, checkout_body):
    user, product = make_user(), make_product(stock=5)
    api = auth_client(user)
    api.post("/cart/items/", {"product_id": product.id, "quantity": 1}, format="json")
    body = checkout_body(payment_method="card", card_number="4000 0000 0000 0002")

    first, second = place(api, body, "attempt-9"), place(api, body, "attempt-9")
    assert first.status_code == second.status_code == 402
    assert first.json()["order"]["id"] == second.json()["order"]["id"]
    assert Order.objects.count() == 1                                    # one failed attempt on record, not two


def test_a_new_key_is_a_new_attempt(auth_client, make_user, make_product, checkout_body):
    user, product = make_user(), make_product(stock=5)
    api = auth_client(user)
    api.post("/cart/items/", {"product_id": product.id, "quantity": 1}, format="json")
    assert place(api, checkout_body(payment_method="card", card_number="4000 0000 0000 0002"), "try-1").status_code == 402
    assert place(api, checkout_body(), "try-2").status_code == 201       # the customer fixed the card and tried again
    assert Order.objects.count() == 2


def test_requests_without_a_key_behave_as_before(auth_client, make_user, make_product, checkout_body):
    user, product = make_user(), make_product(stock=5)
    api = auth_client(user)
    api.post("/cart/items/", {"product_id": product.id, "quantity": 1}, format="json")
    assert place(api, checkout_body()).status_code == 201
    assert place(api, checkout_body()).status_code == 400                # empty cart now


def test_keys_belong_to_one_customer(auth_client, make_user, make_product, checkout_body):
    product = make_product(stock=10)
    alice, bob = auth_client(make_user()), auth_client(make_user())
    for api in (alice, bob):
        api.post("/cart/items/", {"product_id": product.id, "quantity": 1}, format="json")
    assert place(alice, checkout_body(), "same-key").status_code == 201
    assert place(bob, checkout_body(), "same-key").status_code == 201    # not mistaken for Alice's order
    assert Order.objects.count() == 2


@pytest.mark.parametrize("key", ["x" * 65, "has space", "semi;colon", "<script>"])
def test_malformed_keys_are_rejected(auth_client, make_user, make_product, checkout_body, key):
    user, product = make_user(), make_product()
    api = auth_client(user)
    api.post("/cart/items/", {"product_id": product.id, "quantity": 1}, format="json")
    assert place(api, checkout_body(), key).status_code == 400 and Order.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_two_simultaneous_requests_with_one_key_create_one_order(make_user, make_product):
    user, product = make_user(), make_product(stock=5)
    cart_services.add_item(cart_services.get_active_cart(user=user), product.id, 1)
    barrier = threading.Barrier(2)

    def attempt(_):
        try:
            barrier.wait(timeout=10)
            order = order_services.checkout(user, dict(SHIPPING), "cod", idempotency_key="double-click")
            return "replayed" if getattr(order, "replayed", False) else "created"
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = sorted(pool.map(attempt, range(2)))

    assert results == ["created", "replayed"]
    assert Order.objects.count() == 1 and Product.objects.get(pk=product.pk).stock == 4
