from celery import shared_task

from apps.demand_intelligence.detection import detect_demand_signals


@shared_task(name="apps.demand_intelligence.tasks.detect_demand_signals")
def detect_demand_signals_task() -> dict:
    """Scheduled by Celery beat every 15 minutes (see CELERY_BEAT_SCHEDULE)."""
    return detect_demand_signals()
