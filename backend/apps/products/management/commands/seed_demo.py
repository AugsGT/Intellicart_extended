"""Loads SAMPLE catalogue data for development and demos.

Run:  python manage.py seed_demo

The products, specifications and warranty details below are invented sample data,
not real product documentation. Safe to run twice: existing items are skipped.
"""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import User

from apps.categories.models import AttributeDefinition, Category
from apps.inventory import services as inventory
from apps.products import services
from apps.products.models import Product

TEXT, NUMBER = "TEXT", "NUMBER"

# (slug, name, parent slug)
CATEGORIES = [
    ("electronics", "Electronics", None),
    ("laptops", "Laptops", "electronics"),
    ("phones", "Phones", "electronics"),
    ("audio", "Audio", "electronics"),
    ("furniture", "Furniture", None),
    ("office-chairs", "Office Chairs", "furniture"),
]

# (category slug, key, label, type, unit)
ATTRIBUTES = [
    ("electronics", "warranty_months", "Warranty duration", NUMBER, "months"),
    ("electronics", "warranty_type", "Warranty type", TEXT, ""),
    ("electronics", "service_coverage", "Service coverage", TEXT, ""),
    ("laptops", "model", "Model", TEXT, ""),
    ("laptops", "processor", "Processor", TEXT, ""),
    ("laptops", "ram_gb", "RAM", NUMBER, "GB"),
    ("laptops", "storage_gb", "Storage", NUMBER, "GB"),
    ("laptops", "display", "Display", TEXT, ""),
    ("laptops", "battery_hours", "Battery life (claimed)", NUMBER, "hours"),
    ("laptops", "build_quality", "Build", TEXT, ""),
    ("phones", "ram_gb", "RAM", NUMBER, "GB"),
    ("phones", "storage_gb", "Storage", NUMBER, "GB"),
    ("phones", "camera_mp", "Main camera", NUMBER, "MP"),
    ("phones", "battery_mah", "Battery", NUMBER, "mAh"),
    ("audio", "noise_cancellation", "Noise cancellation", TEXT, ""),
    ("audio", "battery_hours", "Battery life (claimed)", NUMBER, "hours"),
    ("furniture", "warranty_months", "Warranty duration", NUMBER, "months"),
    ("furniture", "warranty_type", "Warranty type", TEXT, ""),
    ("office-chairs", "material", "Material", TEXT, ""),
    ("office-chairs", "weight_capacity_kg", "Weight capacity", NUMBER, "kg"),
]

# (name, category slug, brand, price INR, stock, description, {attribute: value})
PRODUCTS = [
    ("Nimbus 14 Developer Laptop", "laptops", "Nimbus", "58999", 12, "14-inch laptop for programming and travel.",
     {"model": "N14-D", "processor": "8-core 2.9 GHz", "ram_gb": 16, "storage_gb": 512, "display": "14\" 1920x1200",
      "battery_hours": 14, "build_quality": "Aluminium chassis", "warranty_months": 24,
      "warranty_type": "On-site", "service_coverage": "Pan-India service centres"}),
    ("Forge 15 Gaming Laptop", "laptops", "Forge", "74999", 6, "15-inch laptop with a dedicated GPU.",
     {"model": "F15-G", "processor": "8-core 3.3 GHz", "ram_gb": 16, "storage_gb": 1024, "display": "15.6\" 144 Hz",
      "battery_hours": 6, "build_quality": "Plastic with metal lid", "warranty_months": 12,
      "warranty_type": "Carry-in", "service_coverage": "Major cities"}),
    ("Slate Air 13 Laptop", "laptops", "Slate", "52999", 20, "Light 13-inch laptop for everyday work.",
     {"model": "SA-13", "processor": "6-core 2.4 GHz", "ram_gb": 8, "storage_gb": 256, "display": "13.3\" 1920x1080",
      "battery_hours": 12, "build_quality": "Magnesium alloy", "warranty_months": 12, "warranty_type": "Carry-in"}),
    ("Orbit X Phone", "phones", "Orbit", "34999", 25, "Phone with a 50 MP main camera.",
     {"ram_gb": 8, "storage_gb": 256, "camera_mp": 50, "battery_mah": 5000, "warranty_months": 12,
      "warranty_type": "Manufacturer", "service_coverage": "Pan-India service centres"}),
    ("Orbit Lite Phone", "phones", "Orbit", "17999", 40, "Budget phone with a large battery.",
     {"ram_gb": 6, "storage_gb": 128, "camera_mp": 48, "battery_mah": 6000, "warranty_months": 12,
      "warranty_type": "Manufacturer"}),
    ("Pulse ANC Earbuds", "audio", "Pulse", "2799", 60, "Wireless earbuds with active noise cancellation.",
     {"noise_cancellation": "Active", "battery_hours": 7, "warranty_months": 12, "warranty_type": "Replacement"}),
    ("Pulse Go Earbuds", "audio", "Pulse", "1499", 80, "Wireless earbuds, no noise cancellation.",
     {"noise_cancellation": "None", "battery_hours": 9, "warranty_months": 6, "warranty_type": "Replacement"}),
    ("ErgoMesh Office Chair", "office-chairs", "Ergo", "8999", 15, "Mesh-back chair with lumbar support.",
     {"material": "Mesh and nylon", "weight_capacity_kg": 120, "warranty_months": 36, "warranty_type": "Parts"}),
    ("Basic Task Chair", "office-chairs", "Ergo", "3499", 5, "Simple fixed-arm task chair.",
     {"material": "Fabric", "weight_capacity_kg": 100, "warranty_months": 12, "warranty_type": "Parts"}),
]


# Development-only accounts, created only with --with-demo-users and only when DEBUG is on.
DEMO_PASSWORD = "demo-password-123"
DEMO_USERS = [
    ("admin@intellicart.local", "demo_admin", "ADMIN"),
    ("ops@intellicart.local", "demo_ops", "OPERATIONS"),
    ("customer@intellicart.local", "demo_customer", "CUSTOMER"),
]


class Command(BaseCommand):
    help = "Load sample categories, specifications and products (development only)."

    def add_arguments(self, parser):
        parser.add_argument("--with-demo-users", action="store_true", help="Also create admin/ops/customer demo accounts")

    @transaction.atomic
    def handle(self, *args, **options):
        categories = {}
        for slug, name, parent_slug in CATEGORIES:
            parent = categories.get(parent_slug)
            categories[slug], _ = Category.objects.get_or_create(slug=slug, defaults={"name": name, "parent": parent})

        for slug, key, label, value_type, unit in ATTRIBUTES:
            AttributeDefinition.objects.get_or_create(
                category=categories[slug], key=key, defaults={"label": label, "value_type": value_type, "unit": unit}
            )

        created = 0
        for name, slug, brand, price, stock, description, attributes in PRODUCTS:
            if Product.objects.filter(name=name).exists():
                continue
            product = Product.objects.create(
                name=name, category=categories[slug], brand=brand, price=price, description=description,
                low_stock_threshold=5, stock=0,
            )
            services.set_attributes(product, [{"key": k, "value": v} for k, v in attributes.items()])
            inventory.adjust_stock(product.id, stock, reason="INITIAL", note="Sample data")
            created += 1

        self.stdout.write(self.style.SUCCESS(f"Sample data ready ({created} new products)."))

        if options["with_demo_users"]:
            if not settings.DEBUG:
                raise CommandError("Demo users are only created when DJANGO_DEBUG=True")
            for email, username, role in DEMO_USERS:
                if not User.objects.filter(email=email).exists():
                    User.objects.create_user(username=username, email=email, password=DEMO_PASSWORD, role=role)
            self.stdout.write(self.style.SUCCESS("Demo users ready (see DEMO_USERS in seed_demo.py)."))
