"""Numbers for the System Health page, read from the database (and, if
configured, the RabbitMQ management API for queue depth)."""
import base64
import json
import urllib.request
from datetime import timedelta

from django.conf import settings
from django.db.models import Max
from django.utils import timezone

from apps.events.models import DeadLetterEvent, Event, OutboxEvent


def _queue_depth(queue: str) -> dict | None:
    if not settings.RABBITMQ_MANAGEMENT_URL:
        return None
    try:
        request = urllib.request.Request(f"{settings.RABBITMQ_MANAGEMENT_URL.rstrip('/')}/api/queues/%2F/{queue}")
        credentials = f"{settings.RABBITMQ_MANAGEMENT_USER}:{settings.RABBITMQ_MANAGEMENT_PASSWORD}"
        request.add_header("Authorization", "Basic " + base64.b64encode(credentials.encode()).decode())
        with urllib.request.urlopen(request, timeout=2) as response:
            data = json.loads(response.read())
        return {
            "messages_ready": data.get("messages_ready", 0),
            "messages_unacked": data.get("messages_unacknowledged", 0),
            "consumers": data.get("consumers", 0),
        }
    except Exception:
        return None


def system_health() -> dict:
    now = timezone.now()
    pending = OutboxEvent.objects.filter(published_at__isnull=True)
    oldest = pending.order_by("id").values_list("occurred_at", flat=True).first()
    last_processed = Event.objects.aggregate(latest=Max("processed_at"))["latest"]

    return {
        "outbox_pending": pending.count(),
        "outbox_oldest_pending_seconds": int((now - oldest).total_seconds()) if oldest else None,
        "outbox_failing": pending.filter(attempts__gt=0).count(),
        "events_last_hour": Event.objects.filter(processed_at__gte=now - timedelta(hours=1)).count(),
        "last_event_processed_at": last_processed,
        "dead_letters_unresolved": DeadLetterEvent.objects.filter(resolved_at__isnull=True).count(),
        "queue": _queue_depth(settings.EVENTS_QUEUE),
        "dead_letter_queue": _queue_depth(settings.EVENTS_DLQ),
    }
