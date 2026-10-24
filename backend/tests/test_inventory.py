import pytest

from apps.inventory import services
from apps.inventory.models import Alert, StockMovement

pytestmark = pytest.mark.django_db


def test_restock_writes_ledger_and_updates_stock(auth_client, make_user, make_product):
    product = make_product(stock=3)
    admin = auth_client(make_user(role="ADMIN"))
    response = admin.post(f"/inventory/{product.id}/restock/", {"quantity": 10, "note": "supplier delivery"}, format="json")
    assert response.status_code == 200 and response.json()["stock"] == 13
    latest = StockMovement.objects.filter(product=product).first()
    assert (latest.change, latest.reason, latest.resulting_stock) == (10, "RESTOCK", 13)


def test_ledger_always_adds_up_to_current_stock(make_product):
    product = make_product(stock=10)
    services.adjust_stock(product.id, -4, "ADJUSTMENT", "damaged")
    services.adjust_stock(product.id, 6, "RESTOCK")
    product.refresh_from_db()
    assert sum(StockMovement.objects.filter(product=product).values_list("change", flat=True)) == product.stock == 12


def test_stock_cannot_go_negative(auth_client, make_user, make_product):
    product = make_product(stock=2)
    admin = auth_client(make_user(role="ADMIN"))
    response = admin.post(f"/inventory/{product.id}/adjust/", {"change": -5, "note": "recount"}, format="json")
    assert response.status_code == 400
    product.refresh_from_db()
    assert product.stock == 2 and StockMovement.objects.filter(product=product).count() == 1


def test_adjustment_needs_a_reason_and_a_nonzero_change(auth_client, make_user, make_product):
    product = make_product()
    admin = auth_client(make_user(role="ADMIN"))
    assert admin.post(f"/inventory/{product.id}/adjust/", {"change": -1}, format="json").status_code == 400
    assert admin.post(f"/inventory/{product.id}/adjust/", {"change": 0, "note": "x"}, format="json").status_code == 400


def test_inventory_permissions(client, auth_client, make_user, make_product):
    product = make_product()
    assert client.get("/inventory/").status_code == 401
    assert auth_client(make_user()).get("/inventory/").status_code == 403
    ops = auth_client(make_user(role="OPERATIONS"))
    assert ops.get("/inventory/").status_code == 200
    assert ops.get(f"/inventory/{product.id}/history/").status_code == 200
    assert ops.post(f"/inventory/{product.id}/restock/", {"quantity": 1}, format="json").status_code == 403


def test_low_stock_alert_opens_once_and_closes_after_restock(make_product):
    product = make_product(stock=10, threshold=5)
    services.adjust_stock(product.id, -6, "ADJUSTMENT", "sale")   # 4 left: at/below threshold
    services.adjust_stock(product.id, -1, "ADJUSTMENT", "sale")   # 3 left: still the same alert
    assert Alert.objects.filter(product=product, resolved=False).count() == 1

    services.adjust_stock(product.id, 20, "RESTOCK")              # 23 left: healthy
    assert not Alert.objects.filter(product=product, resolved=False).exists()
    assert Alert.objects.filter(product=product, resolved=True).count() == 1


def test_out_of_stock_alert_is_high_severity(make_product):
    product = make_product(stock=2, threshold=5)
    services.adjust_stock(product.id, -2, "ADJUSTMENT", "sale")
    assert Alert.objects.get(product=product, resolved=False).severity == "high"


def test_alerts_are_staff_only_and_can_be_resolved(client, auth_client, make_user, make_product):
    product = make_product(stock=1, threshold=5)
    services.adjust_stock(product.id, -1, "ADJUSTMENT", "sale")
    alert = Alert.objects.get(product=product)

    assert client.get("/alerts/").status_code == 401
    assert auth_client(make_user()).get("/alerts/").status_code == 403
    ops = auth_client(make_user(role="OPERATIONS"))
    assert ops.get("/alerts/?resolved=false").json()["count"] == 1
    assert ops.patch(f"/alerts/{alert.id}/resolve/").json()["resolved"] is True
    assert ops.get("/alerts/?resolved=false").json()["count"] == 0
