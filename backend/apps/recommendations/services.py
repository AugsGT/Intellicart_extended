"""Explainable recommendations: counts, categories and price closeness - no
trained model. Every recommended product carries a plain-language `reason`.

Only SUCCESSFUL orders (Order.objects.successful(): paid, not cancelled or failed)
count as purchases, so failed and cancelled orders never influence co-purchases
or personalization.
"""
from collections import Counter, namedtuple

from django.db.models import Count, F, Max, Q

from apps.events.models import Event
from apps.orders.models import Order, OrderItem
from apps.products.models import Product

Recommended = namedtuple("Recommended", ["product", "reason"])

KINDS = ("similar", "frequently_bought_together", "substitutes", "recently_viewed", "cart_based", "personalized", "advisor")


def _available(products):
    return products.filter(status=Product.Status.ACTIVE).select_related("category").prefetch_related("attributes__definition")


def _identity_filter(user_id, session_key) -> Q:
    """Events belonging to this customer: their user id and/or their browser session."""
    condition = Q(pk__in=[])
    if user_id:
        condition |= Q(user_id=user_id)
    if session_key:
        condition |= Q(session_key=session_key)
    return condition


def similar_products(product: Product, limit: int = 6) -> list[Recommended]:
    """Same category, in-stock first, nearest price first."""
    candidates = _available(Product.objects.filter(category=product.category)).exclude(pk=product.pk)
    ranked = sorted(candidates, key=lambda p: (p.stock <= 0, abs(p.price - product.price), p.id))
    return [Recommended(p, f"Same category ({product.category.name}) at a similar price") for p in ranked[:limit]]


def frequently_bought_with(product: Product, limit: int = 6) -> list[Recommended]:
    """Products that appear in the same successful orders as this one."""
    orders_with_product = OrderItem.objects.filter(product=product, order__in=Order.objects.successful()).values("order_id")
    rows = (
        OrderItem.objects.filter(order_id__in=orders_with_product)
        .exclude(product=product)
        .filter(product__status=Product.Status.ACTIVE)
        .values("product_id")
        .annotate(orders=Count("order_id", distinct=True))
        .order_by("-orders", "product_id")[:limit]
    )
    products = _available(Product.objects).in_bulk([row["product_id"] for row in rows])
    return [
        Recommended(products[row["product_id"]], f"Bought together in {row['orders']} order{'s' if row['orders'] != 1 else ''}")
        for row in rows
    ]


def substitutes(product: Product, limit: int = 3) -> list[Recommended]:
    """In-stock alternatives, only when this product is low or out of stock."""
    if product.stock > product.low_stock_threshold:
        return []
    candidates = _available(Product.objects.filter(category=product.category, stock__gt=F("low_stock_threshold"))).exclude(pk=product.pk)
    ranked = sorted(candidates, key=lambda p: (abs(p.price - product.price), p.id))
    return [Recommended(p, "In stock now, similar category and price") for p in ranked[:limit]]


def recently_viewed(user_id, session_key: str, exclude_product_id=None, limit: int = 6) -> list[Recommended]:
    rows = (
        Event.objects.filter(_identity_filter(user_id, session_key), event_type="PRODUCT_VIEWED", entity_id__isnull=False)
        .values("entity_id")
        .annotate(last=Max("occurred_at"))
        .order_by("-last")[: limit + 1]
    )
    ids = [row["entity_id"] for row in rows if row["entity_id"] != exclude_product_id][:limit]
    products = _available(Product.objects).in_bulk(ids)
    return [Recommended(products[i], "You viewed this recently") for i in ids if i in products]


def cart_based(cart, limit: int = 6) -> list[Recommended]:
    """Things bought together with what is in the cart, then more from the same categories."""
    items = list(cart.items.select_related("product"))
    if not items:
        return []
    in_cart = {item.product_id for item in items}

    together = Counter()
    for item in items:
        for rec in frequently_bought_with(item.product, limit=10):
            if rec.product.id not in in_cart and rec.product.stock > 0:
                together[rec.product.id] += 1
    chosen = [Recommended(p, "Often bought with items in your cart") for p in _available(Product.objects).in_bulk(list(together)).values()]
    chosen.sort(key=lambda r: (-together[r.product.id], r.product.id))

    if len(chosen) < limit:
        taken = in_cart | {r.product.id for r in chosen}
        categories = {item.product.category_id for item in items}
        more = _available(Product.objects.filter(category_id__in=categories, stock__gt=0)).exclude(id__in=taken).order_by("id")
        chosen += [Recommended(p, f"More from {p.category.name}, which is in your cart") for p in more[: limit - len(chosen)]]
    return chosen[:limit]


def personalized(user, limit: int = 6) -> list[Recommended]:
    """For a logged-in customer: weight their categories by what they bought (3),
    added to cart (2) and viewed (1), then suggest in-stock products from the top
    categories that they have not already bought."""
    scores: Counter = Counter()
    best_weight: dict[int, int] = {}   # category id -> weight of its strongest signal so far
    best_label: dict[int, str] = {}    # category id -> wording for the explanation

    def add(category_id, weight, label):
        scores[category_id] += weight
        if weight > best_weight.get(category_id, 0):
            best_weight[category_id] = weight
            best_label[category_id] = label

    bought = OrderItem.objects.filter(order__in=Order.objects.successful().filter(user=user))
    bought_ids = set(bought.values_list("product_id", flat=True))
    for row in bought.values("product__category_id").annotate(n=Count("id")):
        add(row["product__category_id"], 3 * row["n"], "bought")

    for event_type, weight, label in (("CART_ITEM_ADDED", 2, "added to your cart"), ("PRODUCT_VIEWED", 1, "viewed")):
        product_ids = list(Event.objects.filter(user_id=user.id, event_type=event_type, entity_id__isnull=False).values_list("entity_id", flat=True))
        categories = dict(Product.objects.filter(id__in=product_ids).values_list("id", "category_id"))
        for product_id in product_ids:
            if product_id in categories:
                add(categories[product_id], weight, label)

    if not scores:
        return []

    names = dict(Product.objects.filter(category_id__in=scores).values_list("category_id", "category__name"))
    results: list[Recommended] = []
    for category_id, _ in scores.most_common(3):
        candidates = _available(Product.objects.filter(category_id=category_id, stock__gt=0)).exclude(id__in=bought_ids).order_by("id")
        reason = f"Because you {best_label[category_id]} items in {names.get(category_id, 'this category')}"
        results += [Recommended(p, reason) for p in candidates[: max(2, limit // 3)]]
    return results[:limit]


def stats() -> list[dict]:
    """Per recommendation kind: lists served, clicks, purchases and rates (from the event log).
    'Served' counts lists shown, a proxy for impressions."""
    rows = []
    for kind in KINDS:
        served = Event.objects.filter(event_type="RECOMMENDATION_GENERATED", payload__kind=kind).count()
        clicks = Event.objects.filter(event_type="RECOMMENDATION_CLICKED", payload__kind=kind).count()
        purchases = Event.objects.filter(event_type="RECOMMENDATION_PURCHASED", payload__kind=kind).count()
        rows.append(
            {
                "kind": kind,
                "served": served,
                "clicks": clicks,
                "purchases": purchases,
                "click_rate": round(clicks / served, 4) if served else None,
                "purchase_rate": round(purchases / clicks, 4) if clicks else None,
            }
        )
    return rows
