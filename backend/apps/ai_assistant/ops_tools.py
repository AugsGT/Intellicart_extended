"""Tools for the OPERATIONS assistant. Everything here is read-only and computed
from live application data; nothing is estimated by the language model.

Safety rules, enforced in code:
* `dispatch` refuses anyone who is not ADMIN or OPERATIONS, even if a view forgot to.
* No tool writes, deletes or sends anything. There is no tool for orders, stock,
  products, users or settings, so the assistant cannot change them. (Any future
  write action must need explicit confirmation and server-side authorization.)
* Arguments come from a model or from parsed text, so they are checked and clamped.
"""
from datetime import timedelta
from decimal import Decimal

from django.db import connection
from django.db.models import Count, F, Sum
from django.utils import timezone

from apps.accounts.permissions import STAFF_ROLES
from apps.demand_intelligence import data as demand_data
from apps.demand_intelligence import services as demand_services
from apps.demand_intelligence import statistics as demand_statistics
from apps.events.health import system_health
from apps.events.models import DeadLetterEvent, Event
from apps.inventory.models import Alert, StockMovement
from apps.orders.models import Order, OrderItem
from apps.products.models import Product

MAX_DAYS = 180


class NotAllowed(Exception):
    pass


def _days(value, default: int = 30) -> int:
    try:
        return max(1, min(int(value), MAX_DAYS))
    except (TypeError, ValueError):
        return default


def _num(value):
    return float(value) if isinstance(value, Decimal) else value


def _pct(current, reference):
    change = demand_statistics.pct_change(current, reference)
    return None if change is None else round(change, 1)


# ---- orders ---------------------------------------------------------------

def _order_stats(start, end) -> dict:
    orders = Order.objects.filter(created_at__gte=start, created_at__lt=end)
    by_status = dict(orders.values_list("status").annotate(n=Count("id")))
    accepted = orders.filter(payment_status__in=[Order.PaymentStatus.PAID, Order.PaymentStatus.REFUNDED]).count()
    cancelled = by_status.get(Order.Status.CANCELLED, 0)
    failed = by_status.get(Order.Status.FAILED, 0)
    sales = Order.objects.successful().filter(created_at__gte=start, created_at__lt=end).aggregate(revenue=Sum("total"), n=Count("id"))
    successful = sales["n"] or 0
    return {
        "orders_placed": orders.count(),
        "by_status": by_status,
        "accepted_orders": accepted,
        "cancelled_orders": cancelled,
        "failed_payments": failed,
        "successful_orders": successful,
        "revenue": _num(sales["revenue"] or 0),
        "average_order_value": round(_num(sales["revenue"] or 0) / successful, 2) if successful else None,
        "cancellation_rate": round(cancelled / accepted, 4) if accepted else None,
        "payment_failure_rate": round(failed / (accepted + failed), 4) if (accepted + failed) else None,
    }


def get_order_analytics(args: dict, user=None) -> dict:
    days = _days(args.get("days"))
    end = timezone.now()
    start, previous_start = end - timedelta(days=days), end - timedelta(days=2 * days)
    return {
        "period_days": days,
        "current": _order_stats(start, end),
        "previous_period": _order_stats(previous_start, start),
        "definitions": {
            "cancellation_rate": "cancelled orders divided by accepted orders (orders whose payment succeeded)",
            "payment_failure_rate": "failed payments divided by all payment attempts",
            "successful_orders": "paid orders that were not cancelled",
        },
    }


# ---- sales history ----------------------------------------------------------

def get_sales_history(args: dict, user=None) -> dict:
    days = _days(args.get("days"))
    end = demand_data.last_complete_day()
    granularity = args.get("granularity") if args.get("granularity") in ("day", "week", "month") else (
        "day" if days <= 14 else "week" if days <= 120 else "month")

    def totals(period_end):
        rows = demand_data.daily_totals(days, end=period_end)
        return rows, sum(r["units"] for r in rows), float(sum(r["revenue"] for r in rows)), sum(r["orders"] for r in rows)

    rows, units, revenue, orders = totals(end)
    _, previous_units, previous_revenue, previous_orders = totals(end - timedelta(days=days))
    series = demand_statistics.bucket(rows, granularity)
    return {
        "period_days": days,
        "ends_on": end.isoformat(),
        "granularity": granularity,
        "units": units, "revenue": revenue, "orders": orders,
        "previous_period": {"units": previous_units, "revenue": previous_revenue, "orders": previous_orders},
        "change_units_pct": _pct(units, previous_units),
        "change_revenue_pct": _pct(revenue, previous_revenue),
        "series": [{"period": b["period"].isoformat(), "units": b["units"], "revenue": round(b["revenue"], 2)} for b in series],
        "note": "Completed orders only; the current day is excluded because it is not finished.",
    }


# ---- product performance -----------------------------------------------------

def _sales_by_product(start_date, end_date) -> dict[int, dict]:
    rows = (
        OrderItem.objects.filter(order__in=Order.objects.successful(), order__created_at__date__gte=start_date, order__created_at__date__lte=end_date)
        .values("product_id", product_name=F("product__name"))
        .annotate(units=Sum("quantity"), revenue=Sum(F("unit_price") * F("quantity")), orders=Count("order_id", distinct=True))
    )
    return {r["product_id"]: {"name": r["product_name"], "units": r["units"], "revenue": _num(r["revenue"]), "orders": r["orders"]} for r in rows}


def get_product_performance(args: dict, user=None) -> dict:
    days = _days(args.get("days"))
    limit = max(1, min(int(args.get("limit") or 5), 20)) if str(args.get("limit") or "5").isdigit() else 5
    end = demand_data.last_complete_day()
    current = _sales_by_product(end - timedelta(days=days - 1), end)
    previous = _sales_by_product(end - timedelta(days=2 * days - 1), end - timedelta(days=days))
    ranked = sorted(current.items(), key=lambda item: (-item[1]["units"], item[1]["name"]))[:limit]
    return {
        "period_days": days,
        "ends_on": end.isoformat(),
        "top_by_units": [
            {"product_id": pid, **row, "previous_units": previous.get(pid, {}).get("units", 0),
             "change_units_pct": _pct(row["units"], previous.get(pid, {}).get("units", 0))}
            for pid, row in ranked
        ],
        "products_with_sales": len(current),
    }


# ---- demand ---------------------------------------------------------------------

def _slim(item: dict) -> dict:
    keys = ("product_id", "name", "trend", "trend_z", "spike", "recent_daily_average", "baseline_daily_average", "burst_daily_average",
            "change_pct", "stock", "stock_state", "days_of_cover", "stockout_risk", "predicted_stockout_date", "restock", "signals")
    return {k: item[k] for k in keys}


def get_demand_trends(args: dict, user=None) -> dict:
    overview = demand_services.overview()
    everything = demand_services.product_list()
    return {
        "as_of": overview["as_of"],
        "counts": overview["counts"],
        "spikes": [_slim(p) for p in overview["spikes"]],
        "increasing": [_slim(p) for p in overview["increasing"]],
        "decreasing": [_slim(p) for p in overview["decreasing"]],
        "at_risk": [_slim(p) for p in overview["at_risk"]],
        "restock": [_slim(p) for p in demand_services.restock_recommendations()],
        "products_without_enough_history": [p["name"] for p in everything if p["trend"] == "insufficient_data"],
        "method": "Last 7 days vs the previous 28; a trend needs a change of 25% or more that is also beyond normal weekly variation. Descriptive statistics, not a forecast.",
    }


# ---- inventory -----------------------------------------------------------------

def _find_product(args: dict):
    if args.get("product_id") not in (None, ""):
        try:
            return Product.objects.filter(pk=int(args["product_id"])).first()
        except (TypeError, ValueError):
            return None
    return None


def get_inventory_statistics(args: dict, user=None) -> dict:
    days = _days(args.get("days"))
    since = timezone.now() - timedelta(days=days)
    movements = StockMovement.objects.filter(created_at__gte=since)
    product = _find_product(args)

    def by_reason(qs):
        rows = qs.values("reason").annotate(units=Sum("change"), count=Count("id"))
        return {r["reason"]: {"units": r["units"], "movements": r["count"]} for r in rows}

    if product is not None:
        own = movements.filter(product=product)
        reasons = by_reason(own)
        net = sum(r["units"] for r in reasons.values())
        adjustments = list(own.filter(reason=StockMovement.Reason.ADJUSTMENT).values("change", "note", "created_at")[:5])
        return {
            "scope": "product",
            "product": {"product_id": product.id, "name": product.name},
            "period_days": days,
            "stock_now": product.stock,
            "stock_at_start": product.stock - net,
            "net_change": net,
            "movements_by_reason": reasons,
            "recent_manual_adjustments": [{"change": a["change"], "note": a["note"], "at": a["created_at"].isoformat()} for a in adjustments],
            "ledger_consistent": (product.stock_movements.aggregate(t=Sum("change"))["t"] or 0) == product.stock,
        }

    products = list(Product.objects.filter(status=Product.Status.ACTIVE))
    states = {"healthy": 0, "low_stock": 0, "out_of_stock": 0}
    for p in products:
        states[demand_statistics.classify_stock(p.stock, p.low_stock_threshold)] += 1
    net_by_product = (
        movements.values("product_id", product_name=F("product__name")).annotate(net=Sum("change")).order_by("net")
    )
    return {
        "scope": "all",
        "period_days": days,
        "active_products": len(products),
        "total_units_in_stock": sum(p.stock for p in products),
        "stock_states": states,
        "movements_by_reason": by_reason(movements),
        "net_change": sum(r["units"] for r in by_reason(movements).values()),
        "biggest_decreases": [{"product_id": r["product_id"], "name": r["product_name"], "net_change": r["net"]} for r in net_by_product[:5] if r["net"] < 0],
        "biggest_increases": [{"product_id": r["product_id"], "name": r["product_name"], "net_change": r["net"]}
                              for r in reversed(list(net_by_product)[-5:]) if r["net"] > 0],
    }


# ---- alerts, health, events ------------------------------------------------------

def get_stock_alerts(args: dict, user=None) -> dict:
    open_alerts = Alert.objects.filter(resolved=False).select_related("product")
    by_type = dict(open_alerts.values_list("type").annotate(n=Count("id")))
    return {
        "open_alerts": open_alerts.count(),
        "by_type": by_type,
        "alerts": [
            {"type": a.type, "severity": a.severity, "message": a.message, "product_id": a.product_id, "raised_at": a.created_at.isoformat()}
            for a in open_alerts.order_by("-created_at")[:20]
        ],
    }


def get_system_health(args: dict, user=None) -> dict:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        database = "up"
    except Exception:
        database = "down"
    health = system_health()
    health["last_event_processed_at"] = health["last_event_processed_at"].isoformat() if health["last_event_processed_at"] else None
    return {"database": database, **health}


def get_event_statistics(args: dict, user=None) -> dict:
    hours = max(1, min(int(args.get("hours") or 24), 24 * 14)) if str(args.get("hours") or "24").isdigit() else 24
    since = timezone.now() - timedelta(hours=hours)
    counts = dict(Event.objects.filter(processed_at__gte=since).values_list("event_type").annotate(n=Count("id")))
    return {
        "period_hours": hours,
        "events_processed": sum(counts.values()),
        "by_type": dict(sorted(counts.items(), key=lambda item: -item[1])),
        "payment_failures": counts.get("PAYMENT_FAILED", 0),
        "dead_letters_unresolved": DeadLetterEvent.objects.filter(resolved_at__isnull=True).count(),
    }


TOOL_FUNCTIONS = {
    "get_order_analytics": get_order_analytics,
    "get_inventory_statistics": get_inventory_statistics,
    "get_demand_trends": get_demand_trends,
    "get_product_performance": get_product_performance,
    "get_stock_alerts": get_stock_alerts,
    "get_sales_history": get_sales_history,
    "get_system_health": get_system_health,
    "get_event_statistics": get_event_statistics,
}


def _tool(name, description, properties=None):
    return {"type": "function", "function": {"name": name, "description": description, "parameters": {"type": "object", "properties": properties or {}}}}


_DAYS = {"days": {"type": "integer", "description": "How many days back (1-180, default 30)"}}

TOOLS = [
    _tool("get_order_analytics", "Order counts by status, cancellation rate, payment failure rate, revenue and average order value, compared with the previous period.", _DAYS),
    _tool("get_inventory_statistics", "Stock levels and stock movements (sold, restocked, cancelled, adjusted). Give product_id to explain one product's stock change.",
          {**_DAYS, "product_id": {"type": "integer"}}),
    _tool("get_demand_trends", "Demand spikes, rising and falling products, products at risk of running out, and restock suggestions."),
    _tool("get_product_performance", "Best-selling products by units and revenue, compared with the previous period.", {**_DAYS, "limit": {"type": "integer"}}),
    _tool("get_stock_alerts", "Open operational alerts (low stock, demand spikes, predicted stockouts)."),
    _tool("get_sales_history", "Total sales over time (units, revenue, orders), compared with the previous period.",
          {**_DAYS, "granularity": {"type": "string", "enum": ["day", "week", "month"]}}),
    _tool("get_system_health", "Database, event outbox backlog, dead letters and queue status."),
    _tool("get_event_statistics", "Counts of recent business events by type.", {"hours": {"type": "integer"}}),
]


def dispatch(name: str, args, user) -> dict:
    """Run a tool for a staff member. Refuses anyone else."""
    if user is None or not getattr(user, "is_authenticated", False) or user.role not in STAFF_ROLES:
        raise NotAllowed("The operations assistant is only available to staff")
    function = TOOL_FUNCTIONS.get(name)
    if function is None:
        return {"error": f"Unknown tool '{name}'"}
    return function(args if isinstance(args, dict) else {}, user=user)
