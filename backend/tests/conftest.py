import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.accounts.models import User

PASSWORD = "Str0ng-pass-phrase"


@pytest.fixture(autouse=True)
def clear_throttle_cache():
    """Throttle counters live in the cache; keep tests independent."""
    cache.clear()


@pytest.fixture()
def client():
    return APIClient()


@pytest.fixture()
def make_user(db):
    def _make(role=User.Role.CUSTOMER, email=None, password=PASSWORD):
        count = User.objects.count() + 1
        email = email or f"user{count}@example.com"
        return User.objects.create_user(username=f"user{count}", email=email, password=password, role=role)

    return _make


@pytest.fixture()
def login_as(client):
    """Log in through the real endpoint and return an authorized client."""

    def _login(user, password=PASSWORD):
        response = client.post("/auth/login/", {"email": user.email, "password": password}, format="json")
        assert response.status_code == 200, response.content
        authed = APIClient()
        authed.credentials(HTTP_AUTHORIZATION=f"Bearer {response.json()['access']}")
        authed.tokens = response.json()
        return authed

    return _login


@pytest.fixture(autouse=True)
def fast_password_hashing(settings):
    """Tests create many users; the production hasher is deliberately slow."""
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@pytest.fixture()
def auth_client():
    """A client authenticated as `user` without going through login."""

    def _auth(user):
        authed = APIClient()
        authed.force_authenticate(user=user)
        return authed

    return _auth


@pytest.fixture()
def make_category(db):
    from apps.categories.models import Category

    def _make(name, parent=None):
        return Category.objects.create(name=name, slug=name.lower().replace(" ", "-"), parent=parent)

    return _make


@pytest.fixture()
def make_product(db, make_category):
    from decimal import Decimal

    from apps.inventory import services as inventory
    from apps.products.models import Product

    default_category = {}

    def _make(name="Widget", price="100.00", stock=10, category=None, threshold=2, **extra):
        if category is None:
            if "c" not in default_category:
                default_category["c"] = make_category("Default")
            category = default_category["c"]
        product = Product.objects.create(
            name=name, price=Decimal(price), category=category, low_stock_threshold=threshold, stock=0, **extra
        )
        if stock:
            inventory.adjust_stock(product.id, stock, reason="INITIAL")
            product.refresh_from_db()
        return product

    return _make


SHIPPING = {
    "full_name": "Test Buyer",
    "address_line1": "1 Test Street",
    "city": "Testville",
    "state": "TS",
    "postal_code": "560001",
    "phone": "9999999999",
}


@pytest.fixture()
def checkout_body():
    def _body(**overrides):
        return {**SHIPPING, "payment_method": "cod", **overrides}

    return _body


@pytest.fixture()
def place_order(db):
    """Put products in a user's cart and check out (service layer, no HTTP)."""
    from apps.cart import services as cart_services
    from apps.orders import services as order_services

    def _place(user, *lines, method="cod"):
        cart = cart_services.get_active_cart(user=user)
        for product, quantity in lines:
            cart_services.add_item(cart, product.id, quantity)
        return order_services.checkout(user, dict(SHIPPING), method)

    return _place


@pytest.fixture()
def make_event(db):
    """Create a processed event-log row directly (as if the consumer had stored it)."""
    import uuid

    from django.utils import timezone

    from apps.events.models import Event

    def _make(event_type, user=None, session="", entity=None, payload=None, when=None):
        return Event.objects.create(
            event_id=uuid.uuid4(),
            event_type=event_type,
            user_id=getattr(user, "id", user),
            session_key=session,
            entity_id=entity,
            payload=payload or {},
            occurred_at=when or timezone.now(),
        )

    return _make
