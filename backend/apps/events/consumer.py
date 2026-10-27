import json
import logging
from datetime import datetime

import pika
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.events import handlers
from apps.events.broker import connect, declare_topology
from apps.events.models import DeadLetterEvent, Event

logger = logging.getLogger("intellicart.events")

PROCESSED = "processed"
DUPLICATE = "duplicate"
RETRY = "retry"
DEAD_LETTERED = "dead_lettered"


def process_message(body: bytes | str, retry_count: int = 0) -> str:
    """Handle one message from the queue. Returns what should happen to it:

    PROCESSED      stored in the event log and handlers ran -> acknowledge
    DUPLICATE      this event_id was already processed -> acknowledge, do nothing
    RETRY          failed, retries left -> send it again with retry_count + 1
    DEAD_LETTERED  failed for good -> recorded in DeadLetterEvent; reject it so
                   RabbitMQ moves it to the dead-letter queue

    Idempotent: the event log's unique event_id means a second delivery of the
    same message is skipped. The log insert and the handlers share one transaction,
    so a failing handler also undoes the log row and the retry starts clean.
    """
    try:
        message = json.loads(body)
        event_id = message["event_id"]
        event_type = message["event_type"]
    except (ValueError, KeyError, TypeError):
        _dead_letter(body, "Message is not valid JSON or lacks event_id / event_type", retry_count)
        return DEAD_LETTERED

    try:
        with transaction.atomic():
            event, created = Event.objects.get_or_create(
                event_id=event_id,
                defaults={
                    "event_type": event_type,
                    "version": message.get("version", 1),
                    "user_id": message.get("user_id"),
                    "session_key": message.get("session_id") or "",
                    "entity_id": message.get("entity_id"),
                    "payload": message.get("payload") or {},
                    "occurred_at": datetime.fromisoformat(message["timestamp"]),
                },
            )
            if not created:
                return DUPLICATE
            handlers.dispatch(event)
    except Exception as error:
        logger.exception("Processing event %s failed (attempt %s)", event_id, retry_count + 1)
        if retry_count + 1 < settings.EVENTS_MAX_RETRIES:
            return RETRY
        _dead_letter(body, str(error), retry_count + 1, event_id=event_id, event_type=event_type)
        return DEAD_LETTERED

    return PROCESSED


def _dead_letter(body, error: str, retries: int, event_id: str = "", event_type: str = "") -> None:
    raw = body.decode("utf-8", errors="replace") if isinstance(body, bytes) else str(body)
    DeadLetterEvent.objects.create(
        event_id=event_id, event_type=event_type, raw_message=raw, error=error[:500], retries=retries
    )


def handle_delivery(ch, method, properties, body) -> str:
    """RabbitMQ callback: process one message, then acknowledge / retry / reject it."""
    retry_count = (properties.headers or {}).get("x-retry-count", 0)
    outcome = process_message(body, retry_count)

    if outcome == RETRY:
        # Publish the retry before acknowledging the original: a crash in
        # between causes a duplicate (harmless), never a lost event.
        ch.basic_publish(
            exchange=settings.EVENTS_EXCHANGE,
            routing_key=method.routing_key,
            body=body,
            properties=pika.BasicProperties(
                content_type="application/json", delivery_mode=2, headers={"x-retry-count": retry_count + 1}
            ),
        )
        ch.basic_ack(delivery_tag=method.delivery_tag)
    elif outcome == DEAD_LETTERED:
        # requeue=False hands the message to the queue's dead-letter exchange.
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
    else:
        ch.basic_ack(delivery_tag=method.delivery_tag)
    logger.info("Event %s -> %s", method.routing_key, outcome)
    return outcome


def run_consumer() -> None:
    """Blocking loop used by `manage.py run_event_consumer`."""
    connection = connect()
    channel = connection.channel()
    declare_topology(channel)
    channel.basic_qos(prefetch_count=10)

    channel.basic_consume(queue=settings.EVENTS_QUEUE, on_message_callback=handle_delivery)
    logger.info("Consumer waiting for events on %s", settings.EVENTS_QUEUE)
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        channel.stop_consuming()
    finally:
        connection.close()


def replay_dead_letters(publisher_factory) -> int:
    """Send unresolved dead-lettered messages through the exchange again.
    Returns how many were replayed. Use after fixing whatever made them fail."""
    publisher = publisher_factory()
    count = 0
    try:
        for dead in DeadLetterEvent.objects.filter(resolved_at__isnull=True).order_by("id"):
            try:
                message = json.loads(dead.raw_message)
                message["event_type"]
            except (ValueError, KeyError, TypeError):
                continue  # not replayable (it was invalid to begin with)
            publisher.publish(message)
            dead.resolved_at = timezone.now()
            dead.save(update_fields=["resolved_at"])
            count += 1
    finally:
        publisher.close()
    return count
