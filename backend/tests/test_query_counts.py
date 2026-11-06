"""Guards against N+1 queries: an endpoint must run the same number of queries
whether it returns 3 rows or 15. If someone adds a lookup inside a loop, these fail."""
import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.audit import services as audit
from apps.cart import services as cart_services
from apps.events.models import DeadLetterEvent
from apps.inventory import services as inventory
from apps.interventions.models import Intervention

pytestmark = pytest.mark.django_db


def count_queries(api, url):
    with CaptureQueriesContext(connection) as queries:
        response = api.get(url)
    assert response.status_code == 200, (url, response.status_code, response.content[:200])
    return len(queries)


def assert_constant(api, url, grow):
    """Query count with a little data vs with a lot: must match (allowing 1 for pagination counts)."""
    grow(3)
    small = count_queries(api, url)
    grow(12)
    large = count_queries(api, url)
    assert large <= small + 1, f"{url}: {small} queries for ~3 rows but {large} for ~15 (an N+1 crept in)"


@pytest.fixture()
def products(make_category, make_product):
    from apps.categories.models import AttributeDefinition
    from apps.products import services

    category = make_category("Gadgets")
    AttributeDefinition.objects.create(category=category, key="color", label="Colour", value_type="TEXT")
    created = []

    def grow(total):
        while len(created) < total:
            product = make_product(f"Item {len(created)}", stock=20, category=category)
            services.set_attributes(product, [{"key": "color", "value": "red"}])
            created.append(product)
        return created

    return grow


def test_catalogue_list_and_search(client, products):
    assert_constant(client, "/products/", products)
    assert_constant(client, "/products/?q=item&ordering=price", products)


def test_recommendations(client, products):
    first = products(3)[0]
    assert_constant(client, f"/recommendations/products/{first.id}/similar/", products)


def test_cart_view(auth_client, make_user, products):
    user = make_user()
    api = auth_client(user)

    def grow(total):
        cart = cart_services.get_active_cart(user=user)
        for product in products(total)[:total]:
            if not cart.items.filter(product=product).exists():
                cart_services.add_item(cart, product.id, 1)

    assert_constant(api, "/cart/", grow)


def test_customer_and_staff_order_lists(auth_client, make_user, products, place_order):
    customer, ops = make_user(), make_user(role="OPERATIONS")

    def grow(total):
        existing = customer.orders.count()
        for product in products(total)[existing:total]:
            place_order(customer, (product, 1))

    assert_constant(auth_client(customer), "/orders/", grow)
    assert_constant(auth_client(ops), "/orders/admin/all/", grow)


def test_inventory_alerts_and_history(auth_client, make_user, products):
    ops = auth_client(make_user(role="OPERATIONS"))

    def grow(total):
        for product in products(total):
            if not product.alerts.exists():
                inventory.adjust_stock(product.id, -19, "ADJUSTMENT", "make it low")

    assert_constant(ops, "/inventory/", grow)
    assert_constant(ops, "/alerts/", grow)
    assert_constant(ops, f"/inventory/{products(3)[0].id}/history/", grow)


def test_event_interventions_and_audit_lists(auth_client, make_user, make_event):
    ops, admin = auth_client(make_user(role="OPERATIONS")), auth_client(make_user(role="ADMIN"))
    counter = {"n": 0}

    def grow(total):
        while counter["n"] < total:
            counter["n"] += 1
            make_event("PRODUCT_VIEWED", session=f"s{counter['n']}", entity=1, payload={"product_id": 1})
            Intervention.objects.create(session_key=f"s{counter['n']}", trigger_event_type="CART_ABANDONED", trigger_event_id="x", action="REMINDER", rule="r")
            DeadLetterEvent.objects.create(event_id=str(counter["n"]), raw_message="{}", error="boom")
            audit.record(None, "ALERT_RESOLVED", f"entry {counter['n']}")

    assert_constant(ops, "/events/", grow)
    assert_constant(ops, "/events/dead-letters/", grow)
    assert_constant(ops, "/interventions/", grow)
    assert_constant(admin, "/audit/", grow)


def test_demand_and_analytics_dashboards(auth_client, make_user, products, place_order):
    ops = auth_client(make_user(role="OPERATIONS"))
    buyer = make_user()

    def grow(total):
        for product in products(total):
            if not product.order_items.exists():
                place_order(buyer, (product, 1))

    for url in ("/demand/overview/", "/demand/products/", "/demand/restock/", "/analytics/sales/", "/analytics/products/", "/analytics/overview/"):
        assert_constant(ops, url, grow)


def test_the_operations_assistants_issue_summary(auth_client, make_user, products):
    from apps.ai_assistant.models import Conversation

    ops = make_user(role="OPERATIONS")
    conversation = Conversation.objects.create(user=ops, kind="operations")

    def ask():
        with CaptureQueriesContext(connection) as queries:
            from apps.ai_assistant import ops_orchestrator

            ops_orchestrator.handle_question(conversation, "What operational issues need attention?")
        return len(queries)

    products(3)
    small = ask()
    products(15)
    assert ask() <= small + 2
