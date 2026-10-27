"""RabbitMQ access (pika). Exchange and queue names are kept from the FastAPI
version: one topic exchange for all events, one queue, and a dead-letter exchange
+ queue for messages that keep failing."""
import json

import pika
from django.conf import settings


def connect() -> pika.BlockingConnection:
    params = pika.URLParameters(settings.RABBITMQ_URL)
    params.socket_timeout = 5
    params.blocked_connection_timeout = 5
    return pika.BlockingConnection(params)


def declare_topology(channel) -> None:
    channel.exchange_declare(exchange=settings.EVENTS_DLX, exchange_type="fanout", durable=True)
    channel.queue_declare(queue=settings.EVENTS_DLQ, durable=True)
    channel.queue_bind(queue=settings.EVENTS_DLQ, exchange=settings.EVENTS_DLX)

    channel.exchange_declare(exchange=settings.EVENTS_EXCHANGE, exchange_type="topic", durable=True)
    channel.queue_declare(
        queue=settings.EVENTS_QUEUE,
        durable=True,
        arguments={"x-dead-letter-exchange": settings.EVENTS_DLX},
    )
    channel.queue_bind(queue=settings.EVENTS_QUEUE, exchange=settings.EVENTS_EXCHANGE, routing_key="#")


class BrokerPublisher:
    """Publishes event messages with publisher confirms: publish() only returns
    once RabbitMQ has accepted the message, and raises if it did not."""

    def __init__(self):
        self.connection = connect()
        self.channel = self.connection.channel()
        declare_topology(self.channel)
        self.channel.confirm_delivery()

    def publish(self, message: dict, headers: dict | None = None) -> None:
        self.channel.basic_publish(
            exchange=settings.EVENTS_EXCHANGE,
            routing_key=message["event_type"],
            body=json.dumps(message),
            properties=pika.BasicProperties(content_type="application/json", delivery_mode=2, headers=headers),
            mandatory=True,
        )

    def close(self) -> None:
        try:
            self.connection.close()
        except Exception:
            pass
