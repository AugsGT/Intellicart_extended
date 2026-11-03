from django.db import transaction
from django.utils import timezone

from apps.demand_intelligence import services
from apps.events.services import emit
from apps.inventory.models import Alert


def _open_alert(product_id: int, alert_type: str):
    return Alert.objects.filter(product_id=product_id, type=alert_type, resolved=False)


def detect_demand_signals() -> dict:
    """Look at every product's demand and keep alerts in step with what is true now.

    * A sudden spike creates ONE alert and ONE DEMAND_SPIKE_DETECTED event; while the
      alert stays open the same spike is not reported again. The alert closes by itself
      when the spike is over.
    * A predicted stockout (stock covering less than the restock lead time at the recent
      pace) creates a STOCKOUT_RISK alert that closes when cover recovers.
    These are separate from the low-stock alert (stock already at its threshold)."""
    spikes_flagged = risks_flagged = 0

    for item in services.analyze_all():
        product_id = item["product_id"]
        with transaction.atomic():
            # --- demand spike ---
            spike_alert = _open_alert(product_id, Alert.Type.DEMAND_SPIKE)
            if item["spike"] and not spike_alert.exists():
                signal = next(s for s in item["signals"] if s["type"] == "DEMAND_SPIKE")
                Alert.objects.create(
                    type=Alert.Type.DEMAND_SPIKE, severity="medium", product_id=product_id,
                    message=f"Sudden demand spike for {item['name']}: {signal['detail']}",
                )
                emit(
                    "DEMAND_SPIKE_DETECTED",
                    entity_id=product_id,
                    payload={
                        "product_id": product_id,
                        "recent_daily_average": item["burst_daily_average"],     # the last 3 days
                        "baseline_daily_average": item["baseline_daily_average"],
                        "threshold_daily_average": item["spike_threshold"],
                    },
                )
                spikes_flagged += 1
            elif not item["spike"] and spike_alert.exists():
                spike_alert.update(resolved=True, resolved_at=timezone.now())

            # --- predicted stockout ---
            risk_alert = _open_alert(product_id, Alert.Type.STOCKOUT_RISK)
            at_risk = item["stockout_risk"] in ("critical", "stocked_out")
            if at_risk and not risk_alert.exists():
                signal = next(s for s in item["signals"] if s["type"] == "PREDICTED_STOCKOUT")
                Alert.objects.create(
                    type=Alert.Type.STOCKOUT_RISK, severity="high", product_id=product_id,
                    message=f"{item['name']} may run out soon: {signal['detail']}",
                )
                risks_flagged += 1
            elif not at_risk and risk_alert.exists():
                risk_alert.update(resolved=True, resolved_at=timezone.now())

    return {"spikes_flagged": spikes_flagged, "stockout_risks_flagged": risks_flagged}
