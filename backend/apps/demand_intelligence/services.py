from datetime import timedelta

from apps.demand_intelligence import data, statistics
from apps.products.models import Product

HISTORY_DAYS = 200   # enough for 6 months of monthly buckets and the 7 + 28 day windows
CHART_DAYS = 90

URGENCY_ORDER = {"urgent": 0, "soon": 1}


def _card(product: Product) -> dict:
    return {"product_id": product.id, "name": product.name, "category": product.category.name}


def analyze_all(products=None) -> list[dict]:
    """Demand numbers for every active product (one query for all the sales)."""
    products = products if products is not None else Product.objects.filter(status=Product.Status.ACTIVE).select_related("category")
    end = data.last_complete_day()
    rows_by_product = data.daily_product_rows(statistics.RECENT_DAYS + statistics.BASELINE_DAYS, end=end)
    results = []
    for product in products:
        daily = data.fill_days(rows_by_product.get(product.id, []), statistics.RECENT_DAYS + statistics.BASELINE_DAYS, end)
        analysis = statistics.analyze(daily, product.stock, product.low_stock_threshold, end)
        results.append({**_card(product), **analysis})
    return results


def overview() -> dict:
    products = analyze_all()
    selling = [p for p in products if p["recent_units"] or p["baseline_units"]]

    def pick(predicate, key, reverse=True, limit=5):
        return sorted((p for p in products if predicate(p)), key=key, reverse=reverse)[:limit]

    return {
        "as_of": data.last_complete_day().isoformat(),
        "windows": {"recent_days": statistics.RECENT_DAYS, "baseline_days": statistics.BASELINE_DAYS, "spike_days": statistics.BURST_DAYS},
        "counts": {
            "products": len(products),
            "with_sales": len(selling),
            "increasing": sum(p["trend"] == statistics.TREND_INCREASING for p in products),
            "decreasing": sum(p["trend"] == statistics.TREND_DECREASING for p in products),
            "spikes": sum(p["spike"] for p in products),
            "stock_shortages": sum(p["stock_state"] != "healthy" for p in products),
            "predicted_stockouts": sum(p["stockout_risk"] in ("critical", "warning", "stocked_out") for p in products),
        },
        "spikes": pick(lambda p: p["spike"], key=lambda p: p["burst_daily_average"]),
        "increasing": pick(lambda p: p["trend"] == statistics.TREND_INCREASING, key=lambda p: p["change_pct"] or 0),
        "decreasing": pick(lambda p: p["trend"] == statistics.TREND_DECREASING, key=lambda p: p["change_pct"] or 0, reverse=False),
        "at_risk": pick(
            lambda p: p["stockout_risk"] in ("critical", "warning", "stocked_out"),
            key=lambda p: (p["days_of_cover"] if p["days_of_cover"] is not None else 0), reverse=False,
        ),
        "top_sellers": sorted(selling, key=lambda p: p["recent_daily_average"], reverse=True)[:5],
    }


def product_list(trend: str | None = None, risk: str | None = None) -> list[dict]:
    products = analyze_all()
    if trend:
        products = [p for p in products if p["trend"] == trend]
    if risk:
        products = [p for p in products if p["stockout_risk"] == risk]
    return sorted(products, key=lambda p: (-p["recent_daily_average"], p["name"]))


def restock_recommendations() -> list[dict]:
    """Products that should be reordered, most urgent first."""
    recommended = [p for p in analyze_all() if p["restock"]]
    return sorted(
        recommended,
        key=lambda p: (URGENCY_ORDER[p["restock"]["urgency"]], p["days_of_cover"] if p["days_of_cover"] is not None else 0, p["name"]),
    )


def product_detail(product: Product) -> dict:
    """One product: the numbers plus chart series (daily with a 7-day moving average, weekly, monthly)."""
    end = data.last_complete_day()
    rows = data.daily_product_rows(HISTORY_DAYS, product_id=product.id, end=end).get(product.id, [])
    needed = statistics.RECENT_DAYS + statistics.BASELINE_DAYS
    daily_all = data.fill_days(rows, HISTORY_DAYS, end)
    analysis = statistics.analyze(daily_all[-needed:], product.stock, product.low_stock_threshold, end)

    moving = statistics.moving_average(daily_all)
    chart = [
        {"date": (end - timedelta(days=CHART_DAYS - 1 - i)).isoformat(), "units": daily_all[-CHART_DAYS + i], "moving_average_7d": round(moving[-CHART_DAYS + i], 2)}
        for i in range(CHART_DAYS)
    ]

    def periods(granularity, keep):
        return [
            {"period": b["period"].isoformat(), "units": b["units"], "revenue": b["revenue"], "orders": b["orders"]}
            for b in statistics.bucket(rows, granularity)[-keep:]
        ]

    return {
        **_card(product),
        **analysis,
        "daily": chart,
        "weekly": periods("week", 13),
        "monthly": periods("month", 6),
    }


def sales_series(granularity: str, days: int) -> dict:
    """Total sales (all products) per day, week or month."""
    rows = data.daily_totals(days)
    return {
        "granularity": granularity,
        "days": days,
        "series": [
            {"period": b["period"].isoformat(), "units": b["units"], "revenue": b["revenue"], "orders": b["orders"]}
            for b in statistics.bucket(rows, granularity)
        ],
    }
