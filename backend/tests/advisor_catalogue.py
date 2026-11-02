"""A small catalogue built to exercise the shopping advisor, mirroring the brief's examples."""
import pytest

from apps.categories.models import AttributeDefinition, Category
from apps.products import services as product_services
from apps.products.models import Product
from apps.inventory import services as inventory

TEXT, NUMBER = "TEXT", "NUMBER"


def build_catalogue():
    electronics = Category.objects.create(name="Electronics", slug="electronics")
    furniture = Category.objects.create(name="Furniture", slug="furniture")
    cats = {
        "laptops": Category.objects.create(name="Laptops", slug="laptops", parent=electronics),
        "phones": Category.objects.create(name="Phones", slug="phones", parent=electronics),
        "audio": Category.objects.create(name="Audio", slug="audio", parent=electronics),
        "chairs": Category.objects.create(name="Office Chairs", slug="office-chairs", parent=furniture),
    }

    def define(category, key, label, kind, unit=""):
        AttributeDefinition.objects.create(category=category, key=key, label=label, value_type=kind, unit=unit)

    for key, label, kind, unit in [("warranty_months", "Warranty duration", NUMBER, "months"), ("warranty_type", "Warranty type", TEXT, ""),
                                   ("service_coverage", "Service coverage", TEXT, "")]:
        define(electronics, key, label, kind, unit)
    for key, label, kind, unit in [("processor", "Processor", TEXT, ""), ("ram_gb", "RAM", NUMBER, "GB"), ("storage_gb", "Storage", NUMBER, "GB"),
                                   ("display", "Display", TEXT, ""), ("battery_hours", "Battery life (claimed)", NUMBER, "hours"),
                                   ("build_quality", "Build", TEXT, "")]:
        define(cats["laptops"], key, label, kind, unit)
    define(cats["phones"], "camera_mp", "Main camera", NUMBER, "MP")
    define(cats["phones"], "battery_mah", "Battery", NUMBER, "mAh")
    define(cats["audio"], "noise_cancellation", "Noise cancellation", TEXT)
    define(cats["audio"], "battery_hours", "Battery life (claimed)", NUMBER, "hours")
    define(furniture, "warranty_months", "Warranty duration", NUMBER, "months")
    define(furniture, "warranty_type", "Warranty type", TEXT)
    define(cats["chairs"], "material", "Material", TEXT)
    define(cats["chairs"], "weight_capacity_kg", "Weight capacity", NUMBER, "kg")

    products = {}

    def add(key, name, category, price, brand, stock=10, **attributes):
        product = Product.objects.create(name=name, category=cats[category], price=price, brand=brand, stock=0, low_stock_threshold=2)
        product_services.set_attributes(product, [{"key": k, "value": v} for k, v in attributes.items()])
        if stock:
            inventory.adjust_stock(product.id, stock, "INITIAL")
        products[key] = Product.objects.get(pk=product.pk)

    add("alpha", "Alpha 14 Laptop", "laptops", "55000", "Nimbus", battery_hours=14, ram_gb=16, storage_gb=512, warranty_months=24,
        warranty_type="On-site", service_coverage="Pan-India service centres", build_quality="Aluminium chassis", processor="8-core", display='14" FHD')
    add("bravo", "Bravo 13 Laptop", "laptops", "50000", "Slate", battery_hours=12, ram_gb=8, storage_gb=256, warranty_months=12, warranty_type="Carry-in")
    add("endurance", "Endurance 15 Laptop", "laptops", "58000", "Volt", battery_hours=20, ram_gb=8, storage_gb=512, warranty_months=12, warranty_type="Carry-in")
    add("gamer", "Gamer 17 Laptop", "laptops", "75000", "Forge", battery_hours=6, ram_gb=16, storage_gb=1024, warranty_months=12)
    add("ghost", "Ghost 14 Laptop", "laptops", "40000", "Nimbus", stock=0, battery_hours=10)
    add("plain", "Plain Laptop", "laptops", "45000", "Plain")                       # no attributes at all
    add("camx", "Cam X Phone", "phones", "30000", "Orbit", camera_mp=50, battery_mah=5000, warranty_months=12, warranty_type="Manufacturer")
    add("camlite", "Cam Lite Phone", "phones", "15000", "Orbit", camera_mp=12, battery_mah=6000, warranty_months=12)
    add("anc", "Pulse ANC Earbuds", "audio", "2800", "Pulse", noise_cancellation="Active", battery_hours=7, warranty_months=12, warranty_type="Replacement")
    add("buds", "Pulse Go Earbuds", "audio", "1500", "Pulse", noise_cancellation="None", battery_hours=9, warranty_months=6)
    add("proanc", "Studio ANC Headphones", "audio", "5000", "Studio", noise_cancellation="Active", battery_hours=30)
    add("ergo", "ErgoMesh Office Chair", "chairs", "8999", "Ergo", material="Mesh and nylon", weight_capacity_kg=120, warranty_months=36, warranty_type="Parts")
    add("basic", "Basic Task Chair", "chairs", "3499", "Ergo", material="Fabric", weight_capacity_kg=100, warranty_months=12)
    return products


@pytest.fixture()
def catalogue(db):
    return build_catalogue()
