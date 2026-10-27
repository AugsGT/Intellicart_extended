from apps.events import contracts
from apps.events.models import OutboxEvent


def emit(event_type: str, *, user=None, session_key: str = "", entity_id=None, payload: dict | None = None) -> OutboxEvent:
    """Record a domain event in the outbox.

    Call this INSIDE the transaction that makes the business change, never after
    it: the event then commits or rolls back together with the change. Nothing is
    sent to RabbitMQ here; the relay task does that after the commit.

    `user` may be a User, an id, or None (anonymous browsing).
    """
    payload = payload or {}
    version = contracts.validate(event_type, payload)
    user_id = getattr(user, "id", user)
    return OutboxEvent.objects.create(
        event_type=event_type,
        version=version,
        payload=payload,
        user_id=user_id,
        session_key=(session_key or "")[:64],
        entity_id=entity_id,
    )


def session_key_from_request(request) -> str:
    """The anonymous browser key (X-Session-Id) of a request, if any."""
    return request.headers.get("X-Session-Id", "").strip()[:64]
