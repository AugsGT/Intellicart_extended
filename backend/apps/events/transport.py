"""Chooses how outbox events are delivered, via the EVENT_TRANSPORT setting:

rabbitmq  (default, for deployment) send to RabbitMQ; a separate consumer process
          (`manage.py run_event_consumer`) logs the events and runs handlers.
local     (for development without RabbitMQ) the relay hands each event straight
          to the same consumer logic in-process. Same outbox, same idempotent
          processing, same retries and dead-letter records - just no broker.
"""
import json

from django.conf import settings

from apps.events.broker import BrokerPublisher
from apps.events.consumer import DEAD_LETTERED, PROCESSED, RETRY, process_message


class LocalPublisher:
    def publish(self, message: dict, headers: dict | None = None) -> None:
        body = json.dumps(message)
        retry_count = 0
        while process_message(body, retry_count) == RETRY:
            retry_count += 1  # process_message dead-letters once retries run out

    def close(self) -> None:
        pass


def get_publisher():
    """Publisher for the configured transport (called by the relay on every pass)."""
    if settings.EVENT_TRANSPORT == "local":
        return LocalPublisher()
    return BrokerPublisher()


__all__ = ["LocalPublisher", "get_publisher", "PROCESSED", "DEAD_LETTERED"]
