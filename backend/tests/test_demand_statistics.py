"""Pure arithmetic: no database. Daily lists end on the last complete day (2026-03-31 here)."""
from datetime import date

import pytest

from apps.demand_intelligence import statistics as st

LAST_DAY = date(2026, 3, 31)


def series(baseline, recent):
    """28 baseline days then 7 recent days. Each argument is a list or one number repeated."""
    base = baseline if isinstance(baseline, list) else [baseline] * 28
    rec = recent if isinstance(recent, list) else [recent] * 7
    return base + rec


def analyze(daily, stock=100, threshold=5):
    return st.analyze(daily, stock, threshold, LAST_DAY)


# ---------- building blocks ----------

def test_moving_average_is_a_trailing_average():
    assert st.moving_average([1, 2, 3, 4, 5, 6, 7, 8], window=7) == [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0]


def test_percentage_change():
    assert st.pct_change(15, 10) == 50.0
    assert st.pct_change(5, 10) == -50.0
    assert st.pct_change(5, 0) is None          # nothing to compare with: no percentage is invented


def test_bucketing_into_weeks_and_months():
    rows = [
        {"day": date(2026, 3, 29), "units": 2, "revenue": 20, "orders": 1},   # Sunday: belongs to the week of Monday 23 March
        {"day": date(2026, 3, 30), "units": 3, "revenue": 30, "orders": 2},   # Monday: starts a new week
        {"day": date(2026, 3, 31), "units": 1, "revenue": 10, "orders": 1},
        {"day": date(2026, 4, 1), "units": 4, "revenue": 40, "orders": 1},
    ]
    weeks = st.bucket(rows, "week")
    assert [(w["period"], w["units"]) for w in weeks] == [(date(2026, 3, 23), 2), (date(2026, 3, 30), 8)]
    months = st.bucket(rows, "month")
    assert [(m["period"], m["units"], m["revenue"], m["orders"]) for m in months] == [
        (date(2026, 3, 1), 6, 60.0, 4), (date(2026, 4, 1), 4, 40.0, 1)]
    assert sum(b["units"] for b in st.bucket(rows, "day")) == sum(r["units"] for r in rows)


# ---------- velocity and comparison with history ----------

def test_velocity_and_percentage_change_against_the_baseline():
    result = analyze(series(2, 5))
    assert result["recent_daily_average"] == 5.0 and result["baseline_daily_average"] == 2.0
    assert result["change_pct"] == 150.0
    assert result["comparison"] == {
        "recent_week_units": 35, "previous_week_units": 14, "change_vs_previous_week_pct": 150.0,
        "baseline_weekly_average": 14.0, "change_vs_baseline_pct": 150.0,
    }


def test_a_new_product_with_a_short_history_is_padded_with_zeros_not_guessed():
    result = analyze([3, 3, 3])                       # only 3 days of sales exist
    assert result["baseline_units"] == 0 and result["trend"] == st.TREND_UNKNOWN and result["change_pct"] is None


# ---------- trends ----------

def test_increasing_trend_needs_a_big_and_statistically_meaningful_rise():
    result = analyze(series(2, [3, 3, 4, 4, 4, 3, 4]))          # +79%, well beyond chance, but no sudden burst
    assert result["trend"] == st.TREND_INCREASING and result["trend_z"] > st.TREND_MIN_Z
    assert [s["type"] for s in result["signals"]] == ["DEMAND_INCREASING"]


def test_a_sudden_step_up_is_both_an_increase_and_a_spike():
    result = analyze(series(2, 5))
    assert result["trend"] == st.TREND_INCREASING and result["spike"] is True


def test_decreasing_trend():
    result = analyze(series(3, [1, 0, 0, 1, 0, 1, 0]))
    assert result["trend"] == st.TREND_DECREASING and result["change_pct"] < -25


def test_a_small_change_is_stable():
    assert analyze(series(2, [2, 3, 2, 3, 2, 3, 2]))["trend"] == st.TREND_STABLE     # +21%: under the 25% bar


def test_ordinary_randomness_at_low_volume_is_not_called_a_trend():
    # 1 sale a day, then 10 in a week: +43%, but only z = 1.1 above what chance alone produces.
    result = analyze(series(1, [2, 1, 2, 1, 2, 1, 1]))
    assert result["change_pct"] == pytest.approx(42.9, abs=0.1) and result["trend_z"] < st.TREND_MIN_Z
    assert result["trend"] == st.TREND_STABLE


def test_too_little_history_gives_no_verdict():
    result = analyze(series([1, 0, 0, 0, 0, 1, 0, 0, 0, 0] + [0] * 18, 6))
    assert result["baseline_units"] < st.MIN_BASELINE_UNITS and result["trend"] == st.TREND_UNKNOWN


# ---------- spikes ----------

def test_a_sudden_burst_is_a_spike():
    result = analyze(series(1, [1, 1, 1, 1, 3, 3, 3]))
    assert result["spike"] is True
    assert any(s["type"] == "DEMAND_SPIKE" and "9 units in the last 3 days" in s["detail"] for s in result["signals"])


def test_a_gradual_rise_is_not_a_spike():
    assert analyze(series(2, [2, 2, 2, 2, 2, 3, 3]))["spike"] is False             # 8 units, but only 1.3x the usual pace


def test_a_spike_needs_enough_units_not_just_a_high_ratio():
    assert analyze(series([0] * 28, [0, 0, 0, 0, 1, 2, 2]))["spike"] is False   # 5 units: too few to trust
    assert analyze(series([0] * 28, [0, 0, 0, 0, 2, 2, 2]))["spike"] is True                       # 6 units from nothing: new demand


def test_noisy_products_need_a_bigger_burst_to_count_as_a_spike():
    noisy = [0, 6, 0, 5, 0, 6, 0, 5, 0, 6, 0, 5, 0, 6, 0, 5, 0, 6, 0, 5, 0, 6, 0, 5, 0, 6, 0, 5]   # mean 2.75, large variation
    assert analyze(series(noisy, [0, 0, 0, 0, 4, 4, 4]))["spike"] is False
    assert analyze(series(noisy, [0, 0, 0, 0, 12, 12, 12]))["spike"] is True


# ---------- stock cover, stockout prediction and restocking ----------

@pytest.mark.parametrize(
    "stock,risk,cover",
    [(10, "critical", 5.0), (13, "critical", 6.5), (14, "warning", 7.0), (27, "warning", 13.5), (28, "ok", 14.0), (100, "ok", 50.0)],
)
def test_days_of_cover_and_risk_bands_at_two_units_a_day(stock, risk, cover):
    result = analyze(series(2, 2), stock=stock)
    assert (result["stockout_risk"], result["days_of_cover"]) == (risk, cover)


def test_stocked_out_and_no_sales_are_distinct_cases():
    assert analyze(series(2, 2), stock=0)["stockout_risk"] == "stocked_out"
    assert analyze(series(0, 0), stock=50)["stockout_risk"] == "no_recent_sales"
    assert analyze(series(0, 0), stock=50)["days_of_cover"] is None


def test_predicted_stockout_date_is_after_the_last_day_by_the_cover():
    result = analyze(series(2, 2), stock=10)                  # 5 days of cover
    assert result["predicted_stockout_date"] == "2026-04-06"  # 31 March + 1 + 5 days
    assert analyze(series(2, 2), stock=100)["predicted_stockout_date"] is None   # no prediction when stock is comfortable


def test_cover_uses_the_cautious_faster_pace():
    falling = analyze(series(4, 1), stock=40)                  # baseline 4/day, recent 1/day: plan for the faster 4/day
    assert falling["planning_velocity"] == 4.0 and falling["days_of_cover"] == 10.0
    spiking = analyze(series(1, [1, 1, 1, 1, 6, 6, 6]), stock=40)
    assert spiking["spike"] and spiking["planning_velocity"] == 6.0            # during a spike, plan for the spike pace


def test_restock_suggestion_covers_thirty_days_and_explains_itself():
    urgent = analyze(series(2, 2), stock=10)["restock"]
    assert urgent["quantity"] == 50 and urgent["urgency"] == "urgent"          # ceil(2 * 30) - 10
    assert "2.0 units per day" in urgent["reason"] and "10 in stock covers about 5.0 days" in urgent["reason"] and "order" in urgent["reason"].lower()
    assert analyze(series(2, 2), stock=20)["restock"]["urgency"] == "soon"     # 10 days of cover
    assert analyze(series(2, 2), stock=100)["restock"] is None                 # plenty: nothing to order


def test_a_stocked_out_product_that_sells_gets_an_urgent_restock():
    restock = analyze(series(2, 2), stock=0)["restock"]
    assert restock["quantity"] == 60 and restock["urgency"] == "urgent"


# ---------- spikes, declines, shortages and predicted stockouts are different things ----------

def types(result):
    return {s["type"] for s in result["signals"]}


def test_low_stock_without_sales_is_a_shortage_not_a_predicted_stockout():
    result = analyze(series(0, 0), stock=3, threshold=5)
    assert types(result) == {"STOCK_SHORTAGE"} and result["stockout_risk"] == "no_recent_sales"


def test_healthy_stock_that_will_run_out_soon_is_a_predicted_stockout_not_a_shortage():
    result = analyze(series(10, 10), stock=50, threshold=5)    # 50 units, 10 a day: 5 days of cover
    assert types(result) == {"PREDICTED_STOCKOUT"} and result["stock_state"] == "healthy"


def test_a_spike_alone_is_just_a_spike():
    result = analyze(series(1, [1, 1, 1, 1, 3, 3, 3]), stock=500)
    assert "DEMAND_SPIKE" in types(result) and "STOCK_SHORTAGE" not in types(result) and "PREDICTED_STOCKOUT" not in types(result)


def test_a_decline_is_never_reported_as_a_stock_problem():
    result = analyze(series(3, [1, 0, 0, 1, 0, 1, 0]), stock=500)
    assert types(result) == {"DEMAND_DECREASING"}
