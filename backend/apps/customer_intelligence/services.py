"""Purchase history. Only SUCCESSFUL orders (paid, not cancelled/failed) count as
purchases; cancelled and failed orders are reported separately and never feed the
statistics. Browsing, search and cart activity are events, not purchases (Phase 5).
"""
from decimal import Decimal

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Max, Sum

from apps.orders.models import Order, OrderItem


def purchase_history(user, order_limit: int = 50) -> dict:
    successful = Order.objects.successful().filter(user=user)
    return {
        "stats": purchase_stats(user),
        "orders": [_order_summary(order) for order in successful.prefetch_related("items")[:order_limit]],
    }


def purchase_stats(user) -> dict:
    successful = Order.objects.successful().filter(user=user)
    totals = successful.aggregate(order_count=Count("id"), total_spent=Sum("total"), last_purchase_at=Max("created_at"))

    line_value = ExpressionWrapper(F("unit_price") * F("quantity"), output_field=DecimalField(max_digits=14, decimal_places=2))
    products = (
        OrderItem.objects.filter(order__in=successful)
        .values("product_id", "name")
        .annotate(units=Sum("quantity"), spent=Sum(line_value), last_purchased_at=Max("order__created_at"))
        .order_by("-units", "-last_purchased_at")
    )
    top_products = [
        {"product_id": p["product_id"], "name": p["name"], "quantity": p["units"], "spent": p["spent"],
         "last_purchased_at": p["last_purchased_at"]}
        for p in products[:5]
    ]
    items_purchased = sum(p["units"] for p in products)

    dates = list(successful.order_by("created_at").values_list("created_at", flat=True))
    gaps = [(later - earlier).total_seconds() / 86400 for earlier, later in zip(dates, dates[1:])]
    average_days_between_orders = round(sum(gaps) / len(gaps), 1) if gaps else None

    not_completed = Order.objects.filter(user=user).values("status").annotate(n=Count("id"))
    counts = {row["status"]: row["n"] for row in not_completed}

    return {
        "order_count": totals["order_count"],
        "total_spent": totals["total_spent"] or Decimal("0"),
        "items_purchased": items_purchased,
        "last_purchase_at": totals["last_purchase_at"],
        "average_days_between_orders": average_days_between_orders,  # None until a second purchase
        "top_products": top_products,
        "cancelled_orders": counts.get(Order.Status.CANCELLED, 0),
        "failed_orders": counts.get(Order.Status.FAILED, 0),
    }


def _order_summary(order: Order) -> dict:
    return {
        "order_id": order.id,
        "status": order.status,
        "total": order.total,
        "purchased_at": order.created_at,
        "items": [
            {"product_id": i.product_id, "name": i.name, "unit_price": i.unit_price, "quantity": i.quantity}
            for i in order.items.all()
        ],
    }
