"""What happens when an event is consumed, beyond logging it.

Register a handler with @on("EVENT_TYPE"). Handlers run in the same database
transaction as the event-log insert, so if one raises, the whole thing rolls back
and the message is retried. Handlers must therefore be safe to run again.

Later phases add handlers here: CART_ABANDONED -> rescue engine (Phase 6),
ORDER_COMPLETED -> close the loop on an intervention (Phase 6), and so on.
"""
from collections import defaultdict
from collections.abc import Callable

HANDLERS: dict[str, list[Callable]] = defaultdict(list)


def on(event_type: str):
    def register(function: Callable) -> Callable:
        HANDLERS[event_type].append(function)
        return function

    return register


def dispatch(event) -> None:
    for handler in HANDLERS.get(event.event_type, []):
        handler(event)
