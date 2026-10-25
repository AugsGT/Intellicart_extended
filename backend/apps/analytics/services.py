from decimal import Decimal

from django.db.models import Avg, Count, DecimalField, ExpressionWrapper, F, Sum
from django.db.models.fields.json import KeyTextTransform

from apps.inventory.models import Alert
from apps.orders.models import Order
from apps.products.models import Product


def overview() -> dict:
    """Headline numbers for the operations overview. Orders and revenue count only
    successful orders (paid, not cancelled or failed)."""
    sales = Order.objects.successful().aggregate(orders=Count("id"), revenue=Sum("total"))
    stock = Product.objects.filter(status=Product.Status.ACTIVE).aggregate(units=Sum("stock"))
    return {
        "total_orders": sales["orders"],
        "total_revenue": sales["revenue"] or Decimal("0"),
        "open_alerts": Alert.objects.filter(resolved=False).count(),
        "total_stock_units": stock["units"] or 0,
    }


# ---- behaviour and sales analytics (ported from the FastAPI Analytics page) ----

def _top_products_by_event(event_type: str, key: str, limit: int = 10) -> list[dict]:
    from apps.events.models import Event

    rows = (
        Event.objects.filter(event_type=event_type, entity_id__isnull=False)
        .values("entity_id")
        .annotate(total=Count("id"))
        .order_by("-total", "entity_id")[:limit]
    )
    names = dict(Product.objects.filter(id__in=[r["entity_id"] for r in rows]).values_list("id", "name"))
    return [{"product_id": r["entity_id"], "name": names.get(r["entity_id"], f"Product #{r['entity_id']}"), key: r["total"]} for r in rows]


def product_behaviour() -> dict:
    """What shoppers look at, add to their carts and search for (from the event log)."""
    from apps.events.models import Event

    searches = (
        Event.objects.filter(event_type="PRODUCT_SEARCHED")
        .values(query=KeyTextTransform("query", "payload"))
        .annotate(total=Count("id"))
        .order_by("-total")[:10]
    )
    return {
        "most_viewed": _top_products_by_event("PRODUCT_VIEWED", "views"),
        "most_added_to_cart": _top_products_by_event("CART_ITEM_ADDED", "adds"),
        "most_searched": [{"query": r["query"], "count": r["total"]} for r in searches if r["query"]],
    }


def conversion_counts() -> tuple[int, int]:
    """(customers who viewed a product, how many of them also bought).

    A customer is a logged-in user, or an anonymous browser session when no user is
    known. A viewer counts as converted if their account bought, or their browser
    session bought. Limit: someone who browsed anonymously and then logged in before
    buying appears as two customers, so conversion can be slightly understated."""
    from apps.events.models import Event

    buyers = set(Event.objects.filter(event_type="ORDER_COMPLETED").values_list("user_id", "session_key").distinct())
    buyer_users = {user for user, _ in buyers if user}
    buyer_sessions = {session for _, session in buyers if session}

    customers: dict[tuple, bool] = {}
    for user_id, session_key in Event.objects.filter(event_type="PRODUCT_VIEWED").values_list("user_id", "session_key").distinct():
        key = ("user", user_id) if user_id else ("session", session_key) if session_key else None
        if key is None:
            continue
        converted = bool(user_id and user_id in buyer_users) or bool(session_key and session_key in buyer_sessions)
        customers[key] = customers.get(key, False) or converted
    return len(customers), sum(customers.values())


def sales_overview() -> dict:
    """Average order value, sales by category, checkout drop-off and view-to-purchase conversion.
    Revenue and order figures count only successful orders."""
    from apps.events.models import Event
    from apps.orders.models import OrderItem

    successful = Order.objects.successful()
    average = successful.aggregate(avg=Avg("total"))["avg"] or Decimal("0")

    line_value = ExpressionWrapper(F("unit_price") * F("quantity"), output_field=DecimalField(max_digits=14, decimal_places=2))
    by_category = (
        OrderItem.objects.filter(order__in=successful)
        .values(category_name=F("product__category__name"))
        .annotate(revenue=Sum(line_value), units=Sum("quantity"))
        .order_by("-revenue")
    )

    started = Event.objects.filter(event_type="CHECKOUT_STARTED").count()
    completed = Event.objects.filter(event_type="ORDER_COMPLETED").count()
    viewers, converted = conversion_counts()

    return {
        "average_order_value": average,
        "sales_by_category": [{"category": r["category_name"] or "Uncategorized", "revenue": r["revenue"], "units": r["units"]} for r in by_category],
        "checkout": {
            "checkout_started": started,
            "orders_completed": completed,
            "drop_off_rate": round(max(0.0, (started - completed) / started), 4) if started else 0.0,
        },
        "conversion": {
            "customers_who_viewed": viewers,
            "customers_who_bought": converted,
            "conversion_rate": round(converted / viewers, 4) if viewers else 0.0,
        },
    }
