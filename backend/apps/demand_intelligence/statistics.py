"""Demand statistics: plain, explainable arithmetic on daily unit sales.

THIS IS NOT FORECASTING. Nothing here is a trained model or a prediction of future
demand. It describes what has happened (averages, percentage changes, comparison
with a historical baseline) and applies fixed, documented thresholds. The one
forward-looking number, "days of cover", is simply stock divided by recent selling
speed: it assumes the recent pace continues, and says so.

Input everywhere is a list of units sold per day, oldest first, ending on the last
COMPLETE day (today is excluded because it is still in progress).

Windows
    recent    the last 7 days
    baseline  the 28 days before that (the historical pace to compare against)
    burst     the last 3 days (for spotting sudden spikes)
"""
import math
from datetime import date, timedelta
from statistics import mean, pstdev

# ---- thresholds (all in one place; change them here and the tests show the effect) ----
RECENT_DAYS = 7
BASELINE_DAYS = 28
BURST_DAYS = 3

TREND_THRESHOLD_PCT = 25     # recent pace this far above/below the baseline pace = increasing/decreasing
MIN_BASELINE_UNITS = 10      # fewer units than this in the baseline window = not enough history to judge
MIN_RECENT_UNITS = 5         # "increasing" also needs at least this many recent units (avoids noise)
TREND_MIN_Z = 2.0            # ...and the difference must be statistically meaningful: with few sales per day, week-to-week
                             # swings of +-50% are ordinary randomness. z = (recent - expected) / sqrt(expected), where
                             # expected is what the baseline pace predicts for the recent week (Poisson counting noise).

SPIKE_SIGMA = 3              # a spike must exceed baseline mean + 3 standard deviations...
SPIKE_MIN_RATIO = 2          # ...and be at least twice the baseline mean...
SPIKE_MIN_UNITS = 6          # ...and be at least this many units in the burst window

LEAD_TIME_DAYS = 7           # how long a restock takes to arrive
WARNING_COVER_DAYS = 14      # stock covering fewer days than this deserves attention
TARGET_COVER_DAYS = 30       # restock enough to cover this many days at the current pace

TREND_INCREASING, TREND_DECREASING, TREND_STABLE, TREND_UNKNOWN = "increasing", "decreasing", "stable", "insufficient_data"


def moving_average(series: list[float], window: int = RECENT_DAYS) -> list[float]:
    """Trailing average: each day averaged with the days before it (fewer at the start)."""
    result = []
    for index in range(len(series)):
        part = series[max(0, index - window + 1): index + 1]
        result.append(sum(part) / len(part))
    return result


def pct_change(current: float, reference: float) -> float | None:
    """Percentage change from reference to current, or None if there is nothing to compare with."""
    if reference == 0:
        return None
    return (current - reference) / reference * 100


def classify_stock(stock: int, threshold: int) -> str:
    if stock <= 0:
        return "out_of_stock"
    if stock <= threshold:
        return "low_stock"
    return "healthy"


def analyze(daily: list[int], stock: int, low_stock_threshold: int, last_day: date) -> dict:
    """All the demand numbers for one product. `daily` ends on `last_day`."""
    needed = RECENT_DAYS + BASELINE_DAYS
    daily = [0] * max(0, needed - len(daily)) + list(daily)   # a newer product has no history: zeros

    recent = daily[-RECENT_DAYS:]
    baseline = daily[-(RECENT_DAYS + BASELINE_DAYS):-RECENT_DAYS]
    burst = daily[-BURST_DAYS:]
    previous_week = daily[-2 * RECENT_DAYS:-RECENT_DAYS]

    recent_avg, baseline_avg = sum(recent) / RECENT_DAYS, sum(baseline) / BASELINE_DAYS
    burst_avg = sum(burst) / BURST_DAYS
    baseline_std = pstdev(baseline)
    change = pct_change(recent_avg, baseline_avg)
    expected_recent = baseline_avg * RECENT_DAYS
    z = (sum(recent) - expected_recent) / math.sqrt(expected_recent) if expected_recent > 0 else None

    # ---- trend ----
    if sum(baseline) < MIN_BASELINE_UNITS:
        trend = TREND_UNKNOWN
    elif change is not None and z is not None and change >= TREND_THRESHOLD_PCT and z >= TREND_MIN_Z and sum(recent) >= MIN_RECENT_UNITS:
        trend = TREND_INCREASING
    elif change is not None and z is not None and change <= -TREND_THRESHOLD_PCT and z <= -TREND_MIN_Z:
        trend = TREND_DECREASING
    else:
        trend = TREND_STABLE

    # ---- sudden spike (a threshold anomaly on the burst window) ----
    spike_threshold = max(baseline_avg + SPIKE_SIGMA * baseline_std, SPIKE_MIN_RATIO * baseline_avg)
    spike = sum(burst) >= SPIKE_MIN_UNITS and burst_avg > spike_threshold

    # ---- stock cover ----
    # Planning velocity is the highest of the recent, baseline and (during a spike) burst pace:
    # the cautious choice, because it gives the shortest cover.
    velocity = max(recent_avg, baseline_avg, burst_avg if spike else 0)
    stock_state = classify_stock(stock, low_stock_threshold)
    cover = stock / velocity if velocity > 0 else None

    if stock <= 0 and velocity > 0:
        risk = "stocked_out"
    elif cover is None:
        risk = "no_recent_sales"
    elif cover < LEAD_TIME_DAYS:
        risk = "critical"
    elif cover < WARNING_COVER_DAYS:
        risk = "warning"
    else:
        risk = "ok"

    stockout_date = None
    if cover is not None and risk in ("critical", "warning"):
        stockout_date = last_day + timedelta(days=1 + int(cover))

    # ---- restock suggestion ----
    restock = None
    needs_attention = risk in ("stocked_out", "critical", "warning") or (stock_state != "healthy" and velocity > 0)
    if needs_attention:
        quantity = max(0, math.ceil(velocity * TARGET_COVER_DAYS) - stock)
        if quantity > 0:
            cover_text = f"{stock} in stock covers about {cover:.1f} days" if cover is not None else f"{stock} in stock"
            restock = {
                "quantity": quantity,
                "urgency": "urgent" if risk in ("stocked_out", "critical") else "soon",
                "reason": (
                    f"Selling about {velocity:.1f} units per day; {cover_text}. "
                    f"Ordering {quantity} would cover {TARGET_COVER_DAYS} days at that pace (a restock takes about {LEAD_TIME_DAYS} days)."
                ),
            }

    # ---- separate, clearly labelled signals ----
    signals = []
    if spike:
        signals.append({"type": "DEMAND_SPIKE", "detail": (
            f"{sum(burst)} units in the last {BURST_DAYS} days ({burst_avg:.1f}/day) against a usual {baseline_avg:.1f}/day "
            f"(threshold {spike_threshold:.1f}/day)")})
    if trend == TREND_INCREASING:
        signals.append({"type": "DEMAND_INCREASING", "detail": f"Last {RECENT_DAYS} days up {change:.0f}% on the previous {BASELINE_DAYS}-day pace (z={z:.1f}, beyond normal week-to-week variation)"})
    if trend == TREND_DECREASING:
        signals.append({"type": "DEMAND_DECREASING", "detail": f"Last {RECENT_DAYS} days down {abs(change):.0f}% on the previous {BASELINE_DAYS}-day pace (z={z:.1f}, beyond normal week-to-week variation)"})
    if stock_state != "healthy":
        signals.append({"type": "STOCK_SHORTAGE", "detail": f"Stock is {stock} (threshold {low_stock_threshold})"})
    if risk in ("critical", "warning", "stocked_out"):
        when = f", expected to run out around {stockout_date.isoformat()}" if stockout_date else ""
        signals.append({"type": "PREDICTED_STOCKOUT", "detail": f"At the recent pace stock lasts {cover:.1f} days{when}" if cover is not None else "Selling while out of stock"})

    return {
        "recent_units": sum(recent),
        "baseline_units": sum(baseline),
        "recent_daily_average": round(recent_avg, 2),
        "baseline_daily_average": round(baseline_avg, 2),
        "burst_daily_average": round(burst_avg, 2),
        "change_pct": None if change is None else round(change, 1),
        "trend": trend,
        "trend_z": None if z is None else round(z, 2),
        "spike": spike,
        "spike_threshold": round(spike_threshold, 2),
        "planning_velocity": round(velocity, 2),
        "stock": stock,
        "stock_state": stock_state,
        "days_of_cover": None if cover is None else round(cover, 1),
        "stockout_risk": risk,
        "predicted_stockout_date": stockout_date.isoformat() if stockout_date else None,
        "restock": restock,
        "signals": signals,
        "comparison": {
            "recent_week_units": sum(recent),
            "previous_week_units": sum(previous_week),
            "change_vs_previous_week_pct": None if sum(previous_week) == 0 else round(pct_change(sum(recent), sum(previous_week)), 1),
            "baseline_weekly_average": round(baseline_avg * RECENT_DAYS, 1),
            "change_vs_baseline_pct": None if change is None else round(change, 1),
        },
    }


def bucket(rows: list[dict], granularity: str) -> list[dict]:
    """Group daily rows ({"day": date, "units", "revenue", "orders"}) into weeks (Monday start) or months."""
    buckets: dict[date, dict] = {}
    for row in rows:
        day = row["day"]
        key = day - timedelta(days=day.weekday()) if granularity == "week" else day.replace(day=1) if granularity == "month" else day
        entry = buckets.setdefault(key, {"period": key, "units": 0, "revenue": 0.0, "orders": 0})
        entry["units"] += row["units"]
        entry["revenue"] += float(row["revenue"])
        entry["orders"] += row["orders"]
    return [buckets[key] for key in sorted(buckets)]
