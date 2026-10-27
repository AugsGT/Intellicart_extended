import uuid

from django.db import models


class OutboxEvent(models.Model):
    """An event waiting to be sent to RabbitMQ.

    It is written in the SAME database transaction as the business change that
    caused it (an order, a stock change...). If that transaction rolls back, the
    event disappears with it; if it commits, the event is guaranteed to exist and
    the relay will deliver it (at least once, even after a broker outage).
    """

    event_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    event_type = models.CharField(max_length=50)
    version = models.PositiveSmallIntegerField(default=1)
    payload = models.JSONField(default=dict)
    user_id = models.PositiveIntegerField(null=True, blank=True)
    session_key = models.CharField(max_length=64, blank=True)
    entity_id = models.PositiveIntegerField(null=True, blank=True)
    occurred_at = models.DateTimeField(auto_now_add=True)
    published_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["id"]
        indexes = [models.Index(fields=["published_at", "id"])]

    def to_message(self) -> dict:
        """The JSON message sent over RabbitMQ (same field names as the FastAPI version, plus version)."""
        return {
            "event_id": str(self.event_id),
            "event_type": self.event_type,
            "version": self.version,
            "session_id": self.session_key or None,
            "user_id": self.user_id,
            "entity_id": self.entity_id,
            "payload": self.payload,
            "timestamp": self.occurred_at.isoformat(),
        }


class Event(models.Model):
    """The event log: one row per event the consumer has processed.

    The unique event_id is what makes consumers idempotent: if a message is
    delivered twice, the second insert fails and the message is skipped.
    """

    event_id = models.UUIDField(unique=True)
    event_type = models.CharField(max_length=50, db_index=True)
    version = models.PositiveSmallIntegerField(default=1)
    user_id = models.PositiveIntegerField(null=True, blank=True, db_index=True)
    session_key = models.CharField(max_length=64, blank=True, db_index=True)
    entity_id = models.PositiveIntegerField(null=True, blank=True)
    payload = models.JSONField(default=dict)
    occurred_at = models.DateTimeField()
    processed_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["event_type", "occurred_at"]),   # activity per event type over time
            models.Index(fields=["event_type", "entity_id"]),     # per-product views, cart adds, restocks
        ]


class DeadLetterEvent(models.Model):
    """A message that failed every retry. It is also in the RabbitMQ dead-letter
    queue; this row makes it visible and replayable from the operations console."""

    event_id = models.CharField(max_length=36, db_index=True)
    event_type = models.CharField(max_length=50, blank=True)
    raw_message = models.TextField()
    error = models.CharField(max_length=500, blank=True)
    retries = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-id"]
