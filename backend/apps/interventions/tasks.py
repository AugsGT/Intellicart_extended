from celery import shared_task

from apps.interventions.scanner import scan_abandoned_carts


@shared_task(name="apps.interventions.tasks.scan_abandoned_carts")
def scan_abandoned_carts_task() -> int:
    """Scheduled by Celery beat once a minute (see CELERY_BEAT_SCHEDULE)."""
    return scan_abandoned_carts()
