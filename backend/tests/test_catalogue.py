import pytest

from apps.categories.models import AttributeDefinition
from apps.inventory.models import StockMovement
from apps.products.models import Product

pytestmark = pytest.mark.django_db


@pytest.fixture()
def laptop_setup(make_category):
    electronics = make_category("Electronics")
    laptops = make_category("Laptops", parent=electronics)
    phones = make_category("Phones", parent=electronics)
    AttributeDefinition.objects.create(category=electronics, key="warranty_months", label="Warranty", value_type="NUMBER", unit="months")
    AttributeDefinition.objects.create(category=laptops, key="processor", label="Processor", value_type="TEXT")
    return electronics, laptops, phones


# ---------- categories ----------

def test_categories_are_public_but_only_admin_writes(client, auth_client, make_user):
    assert client.get("/categories/").status_code == 200
    assert client.post("/categories/", {"name": "X", "slug": "x"}, format="json").status_code == 401
    assert auth_client(make_user()).post("/categories/", {"name": "X", "slug": "x"}, format="json").status_code == 403
    assert auth_client(make_user(role="ADMIN")).post("/categories/", {"name": "X", "slug": "x"}, format="json").status_code == 201


def test_category_cannot_become_its_own_descendant(auth_client, make_user, laptop_setup):
    electronics, laptops, _ = laptop_setup
    admin = auth_client(make_user(role="ADMIN"))
    response = admin.patch(f"/categories/{electronics.id}/", {"parent": laptops.id}, format="json")
    assert response.status_code == 400


def test_category_with_products_cannot_be_deleted(auth_client, make_user, make_product, laptop_setup):
    _, laptops, _ = laptop_setup
    make_product(category=laptops)
    response = auth_client(make_user(role="ADMIN")).delete(f"/categories/{laptops.id}/")
    assert response.status_code == 400


# ---------- product writes and attributes ----------

def product_body(category, **overrides):
    return {"name": "Nimbus 14", "price": "58999.00", "category": category.id, "stock": 7, **overrides}


def test_customer_cannot_create_products(client, auth_client, make_user, laptop_setup):
    _, laptops, _ = laptop_setup
    assert client.post("/products/", product_body(laptops), format="json").status_code == 401
    assert auth_client(make_user()).post("/products/", product_body(laptops), format="json").status_code == 403
    assert auth_client(make_user(role="OPERATIONS")).post("/products/", product_body(laptops), format="json").status_code == 403


def test_admin_creates_product_with_attributes_and_ledger_entry(auth_client, make_user, laptop_setup):
    _, laptops, _ = laptop_setup
    body = product_body(laptops, attributes_input=[{"key": "processor", "value": "8-core"}, {"key": "warranty_months", "value": 24}])
    response = auth_client(make_user(role="ADMIN")).post("/products/", body, format="json")
    assert response.status_code == 201, response.content
    data = response.json()
    assert data["stock"] == 7 and data["category_name"] == "Laptops"
    values = {a["key"]: a["value"] for a in data["attributes"]}
    assert values["processor"] == "8-core" and float(values["warranty_months"]) == 24  # parent-category attribute allowed
    movement = StockMovement.objects.get(product_id=data["id"])
    assert movement.change == 7 and movement.reason == "INITIAL"


def test_attributes_must_belong_to_the_products_category(auth_client, make_user, laptop_setup):
    _, _, phones = laptop_setup
    body = product_body(phones, attributes_input=[{"key": "processor", "value": "8-core"}])
    response = auth_client(make_user(role="ADMIN")).post("/products/", body, format="json")
    assert response.status_code == 400
    assert not Product.objects.exists()  # nothing half-created


def test_number_attribute_rejects_text(auth_client, make_user, laptop_setup):
    _, laptops, _ = laptop_setup
    body = product_body(laptops, attributes_input=[{"key": "warranty_months", "value": "two years"}])
    assert auth_client(make_user(role="ADMIN")).post("/products/", body, format="json").status_code == 400


def test_negative_price_is_rejected(auth_client, make_user, laptop_setup):
    _, laptops, _ = laptop_setup
    response = auth_client(make_user(role="ADMIN")).post("/products/", product_body(laptops, price="-1"), format="json")
    assert response.status_code == 400


def test_stock_cannot_be_edited_through_product_update(auth_client, make_user, make_product):
    product = make_product(stock=5)
    response = auth_client(make_user(role="ADMIN")).patch(f"/products/{product.id}/", {"stock": 999}, format="json")
    assert response.status_code == 400
    product.refresh_from_db()
    assert product.stock == 5


def test_delete_archives_the_product(client, auth_client, make_user, make_product):
    product = make_product()
    assert auth_client(make_user(role="ADMIN")).delete(f"/products/{product.id}/").status_code == 204
    product.refresh_from_db()
    assert product.status == "ARCHIVED"
    assert client.get("/products/").json()["count"] == 0          # hidden from the catalogue
    assert client.get(f"/products/{product.id}/").status_code == 200  # still reachable by id (order history)


def test_only_staff_can_list_archived(client, auth_client, make_user, make_product):
    make_product(status="ARCHIVED")
    assert client.get("/products/?status=all").json()["count"] == 0
    assert auth_client(make_user()).get("/products/?status=all").json()["count"] == 0
    assert auth_client(make_user(role="OPERATIONS")).get("/products/?status=all").json()["count"] == 1


# ---------- search, filter, sort, pagination ----------

@pytest.fixture()
def catalogue(make_product, laptop_setup):
    electronics, laptops, phones = laptop_setup
    make_product("Nimbus Laptop", "50000", category=laptops, brand="Nimbus", description="for programming")
    make_product("Forge Laptop", "70000", category=laptops, brand="Forge")
    make_product("Orbit Phone", "30000", category=phones, brand="Orbit")
    make_product("Sold Out Phone", "10000", category=phones, stock=0)
    return electronics, laptops, phones


def names(response):
    return [p["name"] for p in response.json()["results"]]


def test_search_by_text(client, catalogue):
    assert names(client.get("/products/?q=programming")) == ["Nimbus Laptop"]
    assert names(client.get("/products/?q=orbit")) == ["Orbit Phone"]  # matches name and brand, case-insensitive


def test_filter_by_price_range_and_stock(client, catalogue):
    assert names(client.get("/products/?min_price=40000&max_price=60000")) == ["Nimbus Laptop"]
    assert "Sold Out Phone" not in names(client.get("/products/?in_stock=true"))
    assert "Sold Out Phone" in names(client.get("/products/"))


def test_category_filter_includes_subcategories(client, catalogue):
    electronics, laptops, _ = catalogue
    assert len(names(client.get(f"/products/?category={electronics.id}"))) == 4
    assert names(client.get(f"/products/?category={laptops.id}")) == ["Nimbus Laptop", "Forge Laptop"]


def test_filter_by_brand(client, catalogue):
    assert names(client.get("/products/?brand=forge")) == ["Forge Laptop"]


def test_sorting(client, catalogue):
    assert names(client.get("/products/?ordering=price"))[0] == "Sold Out Phone"
    assert names(client.get("/products/?ordering=-price"))[0] == "Forge Laptop"
    assert names(client.get("/products/?ordering=name"))[0] == "Forge Laptop"


def test_pagination(client, catalogue):
    page = client.get("/products/?page_size=3").json()
    assert page["count"] == 4 and len(page["results"]) == 3 and page["next"]
    assert len(client.get("/products/?page_size=3&page=2").json()["results"]) == 1


def test_page_size_is_capped(client, catalogue):
    from config.pagination import StandardPagination

    assert StandardPagination.max_page_size == 100
