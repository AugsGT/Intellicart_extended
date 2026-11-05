from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.audit import services as audit
from apps.audit.models import AppendOnlyError, AuditLog
from tests.conftest import PASSWORD

pytestmark = pytest.mark.django_db


@pytest.fixture()
def admin(make_user, auth_client):
    user = make_user(role="ADMIN")
    api = auth_client(user)
    api.user = user
    return api


def last():
    return AuditLog.objects.first()


# ---------- the log cannot be edited or erased ----------

def test_entries_cannot_be_modified_or_deleted():
    entry = audit.record(None, "ALERT_RESOLVED", "x")
    entry.summary = "tampered"
    with pytest.raises(AppendOnlyError):
        entry.save()
    with pytest.raises(AppendOnlyError):
        entry.delete()
    with pytest.raises(AppendOnlyError):
        AuditLog.objects.all().update(summary="tampered")
    with pytest.raises(AppendOnlyError):
        AuditLog.objects.all().delete()
    with pytest.raises(AppendOnlyError):
        AuditLog.objects.bulk_update([entry], ["summary"])
    assert AuditLog.objects.get().summary == "x"


def test_the_trail_outlives_the_account(make_user):
    staff = make_user(role="ADMIN", email="gone@example.com")
    audit.record(None, "ALERT_RESOLVED", "did something", actor=staff)
    staff.delete()
    entry = AuditLog.objects.get()
    assert entry.actor is None and entry.actor_label == "gone@example.com" and entry.actor_role == "ADMIN"


def test_secrets_are_never_stored():
    entry = audit.record(None, "USER_UPDATED", "x", details={"password": "hunter2", "token": "t", "refresh": "r", "card_number": "4111", "note": "ok"})
    assert entry.details == {"note": "ok"}


# ---------- who did what ----------

def test_product_changes_record_the_actor_and_only_what_changed(admin, make_category, make_product):
    category = make_category("Gadgets")
    created = admin.post("/products/", {"name": "Lamp", "price": "100.00", "category": category.id, "stock": 5}, format="json").json()
    entry = last()
    assert (entry.action, entry.entity_type, entry.entity_id, entry.actor_label, entry.actor_role) == ("PRODUCT_CREATED", "product", str(created["id"]), admin.user.email, "ADMIN")
    assert entry.details["initial_stock"] == 5

    admin.patch(f"/products/{created['id']}/", {"price": "120.00", "name": "Lamp"}, format="json")
    assert last().action == "PRODUCT_UPDATED" and last().details["changes"] == {"price": {"from": "100.00", "to": "120.00"}}

    before = AuditLog.objects.count()
    admin.patch(f"/products/{created['id']}/", {"name": "Lamp"}, format="json")      # nothing actually changed
    assert AuditLog.objects.count() == before

    admin.delete(f"/products/{created['id']}/")
    assert last().action == "PRODUCT_ARCHIVED"


def test_category_and_specification_changes(admin, make_category):
    category = admin.post("/categories/", {"name": "Toys", "slug": "toys"}, format="json").json()
    assert last().action == "CATEGORY_CREATED"
    admin.patch(f"/categories/{category['id']}/", {"name": "Toys & Games"}, format="json")
    assert last().action == "CATEGORY_UPDATED"
    admin.post("/categories/attributes/", {"category": category["id"], "key": "age", "label": "Age", "value_type": "TEXT"}, format="json")
    assert last().action == "ATTRIBUTE_CREATED"
    admin.delete(f"/categories/{category['id']}/")
    assert last().action == "CATEGORY_DELETED" and "Toys" in last().summary


def test_stock_changes_record_who_and_the_resulting_stock(admin, make_product):
    product = make_product(stock=10)
    admin.post(f"/inventory/{product.id}/restock/", {"quantity": 5, "note": "delivery"}, format="json")
    assert (last().action, last().details) == ("STOCK_RESTOCKED", {"quantity": 5, "note": "delivery", "stock_after": 15})
    admin.post(f"/inventory/{product.id}/adjust/", {"change": -3, "note": "damaged"}, format="json")
    assert (last().action, last().details["stock_after"], last().details["reason"]) == ("STOCK_ADJUSTED", 12, "damaged")

    before = AuditLog.objects.count()
    admin.post(f"/inventory/{product.id}/adjust/", {"change": -999, "note": "nope"}, format="json")     # refused: nothing happened, nothing logged
    assert AuditLog.objects.count() == before


def test_order_changes_by_staff_and_customers(auth_client, make_user, make_product, place_order):
    ops = make_user(role="OPERATIONS")
    customer = make_user()
    product = make_product(stock=20)
    first, second = place_order(customer, (product, 1)), place_order(customer, (product, 1))

    auth_client(ops).patch(f"/orders/{first.id}/status/", {"status": "SHIPPED"}, format="json")
    assert (last().action, last().details["from"], last().details["to"], last().actor_role) == ("ORDER_STATUS_CHANGED", "CONFIRMED", "SHIPPED", "OPERATIONS")

    auth_client(customer).post(f"/orders/{second.id}/cancel/")
    assert last().action == "ORDER_CANCELLED" and "the customer" in last().summary and last().actor_label == customer.email

    refused = AuditLog.objects.count()
    auth_client(customer).post(f"/orders/{first.id}/cancel/")            # already shipped: refused
    assert AuditLog.objects.count() == refused


def test_resolving_an_alert_is_logged_once(auth_client, make_user, make_product):
    from apps.inventory import services as inventory

    product = make_product(stock=3, threshold=5)
    inventory.adjust_stock(product.id, -1, "ADJUSTMENT", "recount")
    ops = auth_client(make_user(role="OPERATIONS"))
    alert_id = ops.get("/alerts/").json()["results"][0]["id"]
    ops.patch(f"/alerts/{alert_id}/resolve/")
    ops.patch(f"/alerts/{alert_id}/resolve/")
    assert AuditLog.objects.filter(action="ALERT_RESOLVED").count() == 1


def test_account_changes_by_an_administrator(admin, make_user):
    target = make_user()
    admin.patch(f"/users/{target.id}/", {"role": "OPERATIONS"}, format="json")
    entry = last()
    assert entry.action == "USER_UPDATED" and entry.details["changes"] == {"role": {"from": "CUSTOMER", "to": "OPERATIONS"}}
    admin.delete(f"/users/{target.id}/")
    assert last().action == "USER_DEACTIVATED" and last().entity_id == str(target.id)


def test_logins_failed_attempts_and_staff_logins(client, make_user):
    customer, ops = make_user(email="shopper@example.com"), make_user(role="OPERATIONS", email="ops@example.com")

    client.post("/auth/login/", {"email": "shopper@example.com", "password": "wrong-password"}, format="json")
    entry = last()
    assert entry.action == "LOGIN_FAILED" and entry.actor is None and entry.details == {"email": "shopper@example.com"}
    assert "wrong-password" not in str(entry.details) + entry.summary

    client.post("/auth/login/", {"email": "shopper@example.com", "password": PASSWORD}, format="json")      # a customer logging in is not logged
    assert not AuditLog.objects.filter(action="STAFF_LOGIN").exists()
    client.post("/auth/login/", {"email": "ops@example.com", "password": PASSWORD}, format="json")
    assert last().action == "STAFF_LOGIN" and last().actor == ops


def test_questions_to_the_operations_assistant_are_recorded(auth_client, make_user):
    ops = auth_client(make_user(role="OPERATIONS"))
    conversation = ops.post("/ops-assistant/conversations/", {}, format="json").json()["id"]
    ops.post(f"/ops-assistant/conversations/{conversation}/messages/", {"text": "What is our current cancellation rate?"}, format="json")
    entry = last()
    assert entry.action == "OPS_ASSISTANT_QUERY" and entry.details["question"] == "What is our current cancellation rate?"
    assert entry.details["tools"] == ["get_order_analytics"]


# ---------- the caller's address ----------

class FakeRequest:
    def __init__(self, meta):
        self.META = meta


def test_forwarded_addresses_are_only_believed_behind_a_trusted_proxy(settings):
    request = FakeRequest({"REMOTE_ADDR": "10.0.0.5", "HTTP_X_FORWARDED_FOR": "203.0.113.9, 10.0.0.5"})
    settings.TRUST_PROXY_HEADERS = False
    assert audit.client_ip(request) == "10.0.0.5"                 # a client cannot choose its own logged address
    settings.TRUST_PROXY_HEADERS = True
    assert audit.client_ip(request) == "203.0.113.9"


# ---------- reading the log ----------

def test_only_administrators_can_read_it_and_nobody_can_change_it(client, auth_client, make_user, admin):
    audit.record(None, "ALERT_RESOLVED", "x")
    for url in ("/audit/", "/audit/actions/"):
        assert client.get(url).status_code == 401
        assert auth_client(make_user()).get(url).status_code == 403
        assert auth_client(make_user(role="OPERATIONS")).get(url).status_code == 403
        assert admin.get(url).status_code == 200
    for method in ("post", "patch", "put", "delete"):
        assert getattr(admin, method)("/audit/", {}, format="json").status_code == 405


def test_filters(admin, make_user):
    from django.db import connection

    ops = make_user(role="OPERATIONS", email="night.shift@example.com")
    audit.record(None, "ALERT_RESOLVED", "old thing", actor=ops, entity_type="alert", entity_id=1)
    audit.record(None, "PRODUCT_UPDATED", "older", entity_type="product", entity_id=9)
    audit.record(None, "PRODUCT_UPDATED", "new thing", actor=admin.user, entity_type="product", entity_id=9)
    # The log cannot be backdated through the application, so set a past date with SQL, for this test only.
    with connection.cursor() as cursor:
        cursor.execute("UPDATE audit_auditlog SET created_at = %s WHERE summary = 'older'", [timezone.now() - timedelta(days=10)])

    def results(query):
        return sorted(e["summary"] for e in admin.get(f"/audit/{query}").json()["results"])

    assert results("") == ["new thing", "old thing", "older"]
    assert results("?action=ALERT_RESOLVED") == ["old thing"]
    assert results("?actor=night.shift") == ["old thing"]
    assert results("?entity_type=product&entity_id=9") == ["new thing", "older"]
    assert results("?since=" + (timezone.now() - timedelta(days=2)).date().isoformat()) == ["new thing", "old thing"]
    assert results("?until=" + (timezone.now() - timedelta(days=5)).date().isoformat()) == ["older"]


def test_entries_cannot_be_backdated():
    entry = audit.record(None, "ALERT_RESOLVED", "x")
    AuditLog.objects.bulk_create([AuditLog(action="ALERT_RESOLVED", summary="y", created_at=timezone.now() - timedelta(days=30))])
    assert AuditLog.objects.get(summary="y").created_at > entry.created_at - timedelta(minutes=1)


def test_the_action_list_covers_everything_that_is_recorded(admin):
    actions = {a["action"] for a in admin.get("/audit/actions/").json()}
    assert {"ORDER_STATUS_CHANGED", "STOCK_ADJUSTED", "USER_UPDATED", "PRODUCT_UPDATED", "OPS_ASSISTANT_QUERY", "LOGIN_FAILED"} <= actions
