import logging

from django.db import transaction
from django.utils import timezone

from apps.events.models import OutboxEvent

logger = logging.getLogger("intellicart.events")


def relay_pending(publisher_factory=None, batch_size: int = 100) -> dict:
    """Send unpublished outbox rows to RabbitMQ, oldest first.

    - Rows are locked with SKIP LOCKED, so two relays running at once never send
      the same row (they split the work).
    - If the broker is down, rows stay unpublished with attempts/last_error updated
      and are retried on the next run: events survive an outage.
    - It stops at the first failure to keep events in order.
    - If the process dies after RabbitMQ accepted a message but before the row is
      marked, the row is sent again. That is why consumers are idempotent.
    """
    from apps.events.transport import get_publisher

    publisher_factory = publisher_factory or get_publisher
    sent = 0
    failed = 0
    with transaction.atomic():
        rows = list(
            OutboxEvent.objects.select_for_update(skip_locked=True)
            .filter(published_at__isnull=True)
            .order_by("id")[:batch_size]
        )
        if not rows:
            return {"sent": 0, "failed": 0}

        try:
            publisher = publisher_factory()
        except Exception as error:
            logger.warning("Broker unavailable, %s events stay in the outbox: %s", len(rows), error)
            for row in rows:
                row.attempts += 1
                row.last_error = f"{type(error).__name__}: {error}"[:500]
                row.save(update_fields=["attempts", "last_error"])
            return {"sent": 0, "failed": len(rows)}

        try:
            for row in rows:
                try:
                    publisher.publish(row.to_message())
                except Exception as error:
                    logger.warning("Publishing event %s failed: %s", row.event_id, error)
                    row.attempts += 1
                    row.last_error = f"{type(error).__name__}: {error}"[:500]
                    row.save(update_fields=["attempts", "last_error"])
                    failed += 1
                    break
                row.published_at = timezone.now()
                row.last_error = ""
                row.save(update_fields=["published_at", "last_error"])
                sent += 1
        finally:
            publisher.close()

    return {"sent": sent, "failed": failed}
