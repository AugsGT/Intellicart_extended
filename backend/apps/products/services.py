from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Q

from apps.categories.models import AttributeDefinition, Category, definitions_for_category
from apps.products.models import Product, ProductAttribute

ORDERINGS = {
    "price": "price",
    "-price": "-price",
    "name": "name",
    "-name": "-name",
    "newest": "-created_at",
}


class ProductAttributeError(Exception):
    """Raised when attribute input does not fit the product's category."""


def search_products(params, include_archived: bool = False):
    """Catalogue search used by the API and by the AI advisor's tools.

    params may contain: q, category, brand, min_price, max_price, in_stock, ordering.
    A category filter includes its subcategories.
    """
    products = Product.objects.select_related("category").prefetch_related("attributes__definition")
    if not include_archived:
        products = products.filter(status=Product.Status.ACTIVE)

    query = (params.get("q") or "").strip()
    if query:
        products = products.filter(Q(name__icontains=query) | Q(description__icontains=query) | Q(brand__icontains=query))

    category_id = params.get("category")
    if category_id:
        category = Category.objects.filter(pk=category_id).first()
        products = products.filter(category_id__in=category.descendant_ids() if category else [])

    if params.get("brand"):
        products = products.filter(brand__iexact=params["brand"])
    if params.get("min_price") not in (None, ""):
        products = products.filter(price__gte=params["min_price"])
    if params.get("max_price") not in (None, ""):
        products = products.filter(price__lte=params["max_price"])
    if str(params.get("in_stock", "")).lower() in ("1", "true", "yes"):
        products = products.filter(stock__gt=0)

    return products.order_by(ORDERINGS.get(params.get("ordering"), "id"), "id")


def set_attributes(product: Product, attributes: list[dict]) -> None:
    """Replace a product's attribute values. Each item is {"key": ..., "value": ...}.

    Raises ProductAttributeError if a key is not defined for the product's category
    (or its parents), or a number attribute gets a non-number.
    """
    allowed = {d.key: d for d in definitions_for_category(product.category)}
    rows = []
    for item in attributes:
        key = item.get("key")
        definition = allowed.get(key)
        if definition is None:
            raise ProductAttributeError(f"Attribute '{key}' does not apply to category '{product.category.name}'")
        row = ProductAttribute(product=product, definition=definition)
        if definition.value_type == AttributeDefinition.ValueType.NUMBER:
            try:
                row.value_number = Decimal(str(item.get("value")))
            except InvalidOperation:
                raise ProductAttributeError(f"Attribute '{key}' must be a number")
        else:
            row.value_text = str(item.get("value", ""))[:200]
        rows.append(row)

    with transaction.atomic():
        product.attributes.all().delete()
        ProductAttribute.objects.bulk_create(rows)
