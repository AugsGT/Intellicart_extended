from celery import shared_task

from apps.events.relay import relay_pending


@shared_task(name="apps.events.tasks.relay_outbox")
def relay_outbox() -> dict:
    """Scheduled by Celery beat every few seconds (see CELERY_BEAT_SCHEDULE)."""
    return relay_pending()
