import json
from types import SimpleNamespace

import pytest

from apps.events import broker, handlers
from apps.events.consumer import DEAD_LETTERED, DUPLICATE, PROCESSED, RETRY, handle_delivery
from apps.events.models import DeadLetterEvent, Event, OutboxEvent
from apps.events.relay import relay_pending
from apps.events.services import emit
from apps.events.transport import LocalPublisher, get_publisher

pytestmark = pytest.mark.django_db


class FakeChannel:
    """Records what the consumer does with a delivery."""

    def __init__(self):
        self.calls = []

    def basic_ack(self, delivery_tag):
        self.calls.append(("ack", delivery_tag))

    def basic_nack(self, delivery_tag, requeue):
        self.calls.append(("nack", delivery_tag, requeue))

    def basic_publish(self, exchange, routing_key, body, properties):
        self.calls.append(("publish", exchange, routing_key, properties.headers))

    def exchange_declare(self, **kwargs):
        self.calls.append(("exchange_declare", kwargs["exchange"], kwargs["exchange_type"]))

    def queue_declare(self, **kwargs):
        self.calls.append(("queue_declare", kwargs["queue"], kwargs.get("arguments")))

    def queue_bind(self, **kwargs):
        self.calls.append(("queue_bind", kwargs["queue"], kwargs["exchange"], kwargs.get("routing_key")))


def delivery(body, retry_count=None):
    method = SimpleNamespace(delivery_tag=7, routing_key="PRODUCT_VIEWED")
    headers = {"x-retry-count": retry_count} if retry_count is not None else None
    return method, SimpleNamespace(headers=headers), body


def run(channel, body, retry_count=None):
    method, properties, body = delivery(body, retry_count)
    return handle_delivery(channel, method, properties, body)


def view_message():
    return json.dumps(emit("PRODUCT_VIEWED", payload={"product_id": 1}).to_message())


# ---------- RabbitMQ delivery callback ----------

def test_processed_message_is_acknowledged():
    channel = FakeChannel()
    assert run(channel, view_message()) == PROCESSED
    assert channel.calls == [("ack", 7)]


def test_duplicate_delivery_is_acknowledged_without_reprocessing():
    channel, body = FakeChannel(), view_message()
    run(channel, body)
    assert run(channel, body) == DUPLICATE
    assert channel.calls == [("ack", 7), ("ack", 7)]
    assert Event.objects.count() == 1


def failing_handler():
    def boom(event):
        raise RuntimeError("handler bug")

    handlers.HANDLERS["PRODUCT_VIEWED"].append(boom)


def test_failed_message_is_republished_with_a_higher_retry_count_then_acknowledged():
    failing_handler()
    channel = FakeChannel()
    try:
        assert run(channel, view_message(), retry_count=1) == RETRY
    finally:
        handlers.HANDLERS["PRODUCT_VIEWED"].clear()
    # republish first, acknowledge second: a crash in between can only cause a duplicate
    assert channel.calls == [("publish", "intellicart.events", "PRODUCT_VIEWED", {"x-retry-count": 2}), ("ack", 7)]


def test_message_out_of_retries_is_rejected_into_the_dead_letter_queue():
    failing_handler()
    channel = FakeChannel()
    try:
        assert run(channel, view_message(), retry_count=2) == DEAD_LETTERED
    finally:
        handlers.HANDLERS["PRODUCT_VIEWED"].clear()
    assert channel.calls == [("nack", 7, False)]        # requeue=False -> RabbitMQ dead-letters it
    assert DeadLetterEvent.objects.get().error == "handler bug"


def test_topology_uses_the_original_names_and_a_dead_letter_exchange():
    channel = FakeChannel()
    broker.declare_topology(channel)
    assert ("exchange_declare", "intellicart.events", "topic") in channel.calls
    assert ("exchange_declare", "intellicart.events.dlx", "fanout") in channel.calls
    assert ("queue_declare", "intellicart.events.queue", {"x-dead-letter-exchange": "intellicart.events.dlx"}) in channel.calls
    assert ("queue_bind", "intellicart.events.queue.dlq", "intellicart.events.dlx", None) in channel.calls


# ---------- local transport (development without RabbitMQ) ----------

def test_transport_setting_selects_the_publisher(settings, monkeypatch):
    class StubBrokerPublisher:  # the real one would open a connection to RabbitMQ
        pass

    monkeypatch.setattr("apps.events.transport.BrokerPublisher", StubBrokerPublisher)
    settings.EVENT_TRANSPORT = "local"
    assert isinstance(get_publisher(), LocalPublisher)
    settings.EVENT_TRANSPORT = "rabbitmq"
    assert isinstance(get_publisher(), StubBrokerPublisher)


def test_local_transport_delivers_outbox_events_through_the_consumer(settings):
    settings.EVENT_TRANSPORT = "local"
    emit("PRODUCT_VIEWED", entity_id=5, payload={"product_id": 5})
    emit("PRODUCT_SEARCHED", payload={"query": "lamp"})

    assert relay_pending() == {"sent": 2, "failed": 0}
    assert list(Event.objects.order_by("id").values_list("event_type", flat=True)) == ["PRODUCT_VIEWED", "PRODUCT_SEARCHED"]
    assert not OutboxEvent.objects.filter(published_at__isnull=True).exists()
    assert relay_pending() == {"sent": 0, "failed": 0}


def test_local_transport_retries_then_dead_letters_a_failing_handler(settings):
    settings.EVENT_TRANSPORT = "local"
    failing_handler()
    emit("PRODUCT_VIEWED", payload={"product_id": 1})
    try:
        relay_pending()
    finally:
        handlers.HANDLERS["PRODUCT_VIEWED"].clear()

    assert Event.objects.count() == 0
    assert DeadLetterEvent.objects.get().retries == 3      # tried EVENTS_MAX_RETRIES times
    assert not OutboxEvent.objects.filter(published_at__isnull=True).exists()  # handed over; failure is in the dead letters
