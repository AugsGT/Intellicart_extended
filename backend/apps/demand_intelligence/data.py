"""Reads sales history from the orders tables.

Only SUCCESSFUL orders count (paid, not cancelled, not failed), through
Order.objects.successful(): a cancelled or failed order is not demand that was met.
Days are UTC calendar days, and today is excluded because it is not finished.
"""
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, F, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from apps.orders.models import Order, OrderItem


def last_complete_day() -> date:
    return timezone.now().date() - timedelta(days=1)


def daily_product_rows(days: int, product_id: int | None = None, end: date | None = None) -> dict[int, list[dict]]:
    """product id -> rows [{"day", "units", "revenue", "orders"}] for the `days` days ending at `end`."""
    end = end or last_complete_day()
    start = end - timedelta(days=days - 1)
    items = OrderItem.objects.filter(
        order__in=Order.objects.successful(), order__created_at__date__gte=start, order__created_at__date__lte=end
    )
    if product_id is not None:
        items = items.filter(product_id=product_id)
    rows = (
        items.annotate(day=TruncDate("order__created_at"))
        .values("product_id", "day")
        .annotate(units=Sum("quantity"), revenue=Sum(F("unit_price") * F("quantity")), orders=Count("order_id", distinct=True))
        .order_by("product_id", "day")
    )
    by_product: dict[int, list[dict]] = defaultdict(list)
    for row in rows:
        by_product[row["product_id"]].append(row)
    return by_product


def fill_days(rows: list[dict], days: int, end: date) -> list[int]:
    """Units per day for exactly `days` days ending at `end`, with zeros on days without sales."""
    by_day = {row["day"]: row["units"] for row in rows}
    return [by_day.get(end - timedelta(days=offset), 0) for offset in range(days - 1, -1, -1)]


def daily_totals(days: int, end: date | None = None) -> list[dict]:
    """All products together, one row per day that had sales."""
    end = end or last_complete_day()
    start = end - timedelta(days=days - 1)
    rows = (
        OrderItem.objects.filter(
            order__in=Order.objects.successful(), order__created_at__date__gte=start, order__created_at__date__lte=end
        )
        .annotate(day=TruncDate("order__created_at"))
        .values("day")
        .annotate(units=Sum("quantity"), revenue=Sum(F("unit_price") * F("quantity")), orders=Count("order_id", distinct=True))
        .order_by("day")
    )
    return [{**row, "revenue": row["revenue"] or Decimal(0)} for row in rows]
