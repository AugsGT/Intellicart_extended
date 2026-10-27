"""The event catalogue: every domain event, its schema version and the payload
keys it must carry. Publishing an unknown event or a payload with missing keys
fails immediately, so consumers can rely on the shape of what they receive.

When a payload changes in a breaking way, add the new version here and bump
`version`; consumers can then handle old and new messages side by side.
"""

# event type -> (version, required payload keys)
EVENTS: dict[str, tuple[int, tuple[str, ...]]] = {
    # orders and payments
    "ORDER_CREATED": (1, ("order_id", "total", "item_count")),
    "ORDER_COMPLETED": (1, ("order_id", "total")),  # order confirmed and paid
    "ORDER_CANCELLED": (1, ("order_id", "total")),
    "PAYMENT_SUCCEEDED": (1, ("order_id", "amount", "method")),
    "PAYMENT_FAILED": (1, ("order_id", "amount", "method", "reason")),
    # inventory
    "INVENTORY_UPDATED": (1, ("product_id", "change", "stock", "reason")),
    "STOCK_LOW": (1, ("product_id", "stock", "threshold")),
    "STOCK_RESTOCKED": (1, ("product_id", "stock")),  # back in stock after being at 0
    # shopping behaviour
    "CART_ITEM_ADDED": (1, ("product_id", "quantity")),
    "CART_ITEM_REMOVED": (1, ("product_id",)),
    "CHECKOUT_STARTED": (1, ()),
    "CART_ABANDONED": (1, ("cart_id",)),  # emitted by the Phase 6 scanner
    "PRODUCT_VIEWED": (1, ("product_id",)),
    "PRODUCT_SEARCHED": (1, ("query",)),
    # recommendations (emitted from Phase 6)
    "RECOMMENDATION_GENERATED": (1, ("kind", "product_ids")),
    "RECOMMENDATION_CLICKED": (1, ("kind", "product_id")),
    "RECOMMENDATION_PURCHASED": (1, ("kind", "product_id", "order_id")),
    # demand intelligence (emitted from Phase 8)
    "DEMAND_SPIKE_DETECTED": (1, ("product_id", "recent_daily_average", "baseline_daily_average")),
}


class InvalidEvent(ValueError):
    pass


def validate(event_type: str, payload: dict) -> int:
    """Check an event against the catalogue and return its schema version."""
    if event_type not in EVENTS:
        raise InvalidEvent(f"Unknown event type '{event_type}'")
    version, required = EVENTS[event_type]
    missing = [key for key in required if key not in payload]
    if missing:
        raise InvalidEvent(f"{event_type} is missing payload keys: {', '.join(missing)}")
    return version
