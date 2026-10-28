import json
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from django.db import connection, transaction

from apps.cart import services as cart_services
from apps.events import consumer, contracts, handlers
from apps.events.consumer import DEAD_LETTERED, DUPLICATE, PROCESSED, RETRY, process_message, replay_dead_letters
from apps.events.models import DeadLetterEvent, Event, OutboxEvent
from apps.events.relay import relay_pending
from apps.events.services import emit
from apps.inventory import services as inventory
from apps.orders import services as order_services
from tests.conftest import SHIPPING

pytestmark = pytest.mark.django_db


class FakeBroker:
    """Stands in for RabbitMQ: remembers every message it accepted."""

    def __init__(self, fail_after=None):
        self.messages = []
        self.fail_after = fail_after  # accept this many messages, then refuse
        self.lock = threading.Lock()

    def publisher(self):
        return FakePublisher(self)


class FakePublisher:
    def __init__(self, broker):
        self.broker = broker

    def publish(self, message, headers=None):
        with self.broker.lock:
            if self.broker.fail_after is not None and len(self.broker.messages) >= self.broker.fail_after:
                raise ConnectionError("broker refused the message")
            self.broker.messages.append(message)

    def close(self):
        pass


def broker_down():
    raise ConnectionError("broker is down")


def types(user=None):
    return list(OutboxEvent.objects.order_by("id").values_list("event_type", flat=True))


# ---------- contracts ----------

def test_every_required_event_type_is_defined():
    required = """ORDER_CREATED ORDER_CANCELLED ORDER_COMPLETED PAYMENT_SUCCEEDED PAYMENT_FAILED INVENTORY_UPDATED
    STOCK_LOW STOCK_RESTOCKED CART_ITEM_ADDED CART_ITEM_REMOVED CART_ABANDONED PRODUCT_VIEWED PRODUCT_SEARCHED
    RECOMMENDATION_GENERATED RECOMMENDATION_CLICKED RECOMMENDATION_PURCHASED DEMAND_SPIKE_DETECTED""".split()
    assert [name for name in required if name not in contracts.EVENTS] == []


def test_unknown_event_and_missing_payload_are_rejected():
    with pytest.raises(contracts.InvalidEvent):
        emit("MADE_UP_EVENT")
    with pytest.raises(contracts.InvalidEvent, match="order_id"):
        emit("ORDER_COMPLETED", payload={"total": "1"})
    assert OutboxEvent.objects.count() == 0


def test_events_carry_a_version_and_the_old_message_shape():
    event = emit("PRODUCT_VIEWED", session_key="browser-1", entity_id=7, payload={"product_id": 7})
    message = event.to_message()
    assert message["version"] == 1
    assert set(message) == {"event_id", "event_type", "version", "session_id", "user_id", "entity_id", "payload", "timestamp"}
    assert message["session_id"] == "browser-1"


# ---------- outbox: same transaction as the business change ----------

def test_outbox_row_disappears_when_the_business_transaction_rolls_back():
    with pytest.raises(RuntimeError):
        with transaction.atomic():
            emit("PRODUCT_VIEWED", payload={"product_id": 1})
            raise RuntimeError("business change failed")
    assert OutboxEvent.objects.count() == 0


def test_failed_checkout_leaves_no_events(make_user, make_product):
    user, product = make_user(), make_product(stock=2)
    cart_services.add_item(cart_services.get_active_cart(user=user), product.id, 2)
    OutboxEvent.objects.all().delete()
    product.stock = 1
    product.save()

    with pytest.raises(order_services.CheckoutError):
        order_services.checkout(user, dict(SHIPPING), "cod")
    assert OutboxEvent.objects.count() == 0


# ---------- relay ----------

def test_relay_sends_in_order_and_marks_published():
    for number in range(3):
        emit("PRODUCT_VIEWED", entity_id=number, payload={"product_id": number})
    broker = FakeBroker()

    assert relay_pending(broker.publisher) == {"sent": 3, "failed": 0}
    assert [m["entity_id"] for m in broker.messages] == [0, 1, 2]
    assert not OutboxEvent.objects.filter(published_at__isnull=True).exists()

    assert relay_pending(broker.publisher) == {"sent": 0, "failed": 0}  # nothing is sent twice
    assert len(broker.messages) == 3


def test_events_survive_a_broker_outage():
    emit("PRODUCT_VIEWED", payload={"product_id": 1})
    emit("PRODUCT_VIEWED", payload={"product_id": 2})

    assert relay_pending(broker_down) == {"sent": 0, "failed": 2}   # broker is down
    pending = OutboxEvent.objects.filter(published_at__isnull=True)
    assert pending.count() == 2
    assert all(row.attempts == 1 and "down" in row.last_error for row in pending)

    broker = FakeBroker()                                            # broker comes back
    assert relay_pending(broker.publisher) == {"sent": 2, "failed": 0}
    assert len(broker.messages) == 2
    assert OutboxEvent.objects.filter(last_error="").count() == 2


def test_relay_stops_at_first_failure_to_keep_order():
    for number in range(4):
        emit("PRODUCT_VIEWED", entity_id=number, payload={"product_id": number})
    broker = FakeBroker(fail_after=2)

    assert relay_pending(broker.publisher) == {"sent": 2, "failed": 1}
    assert [m["entity_id"] for m in broker.messages] == [0, 1]
    assert list(OutboxEvent.objects.filter(published_at__isnull=True).values_list("entity_id", flat=True)) == [2, 3]

    broker.fail_after = None
    relay_pending(broker.publisher)
    assert [m["entity_id"] for m in broker.messages] == [0, 1, 2, 3]


@pytest.mark.django_db(transaction=True)
def test_two_relays_running_together_never_send_the_same_event_twice():
    for number in range(30):
        emit("PRODUCT_VIEWED", entity_id=number, payload={"product_id": number})
    broker = FakeBroker()
    start = threading.Barrier(2)

    def run_relay(_):
        try:
            start.wait(timeout=10)
            return relay_pending(broker.publisher, batch_size=10)
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(run_relay, range(2)))
    relay_pending(broker.publisher)  # sweep whatever the two passes left

    sent = [m["event_id"] for m in broker.messages]
    assert len(sent) == len(set(sent)) == 30


# ---------- consumer: idempotent, retries, dead letters ----------

def message_for(event):
    return json.dumps(event.to_message())


def test_consumer_stores_the_event_once_even_if_delivered_twice():
    body = message_for(emit("PRODUCT_VIEWED", user=None, session_key="s", entity_id=3, payload={"product_id": 3}))
    seen = []
    handlers.HANDLERS["PRODUCT_VIEWED"].append(lambda event: seen.append(event.event_id))
    try:
        assert process_message(body) == PROCESSED
        assert process_message(body) == DUPLICATE
    finally:
        handlers.HANDLERS["PRODUCT_VIEWED"].clear()

    assert Event.objects.count() == 1 and len(seen) == 1     # the handler ran once
    stored = Event.objects.get()
    assert (stored.event_type, stored.entity_id, stored.session_key) == ("PRODUCT_VIEWED", 3, "s")


def test_failing_handler_rolls_back_and_retries_then_succeeds():
    body = message_for(emit("PRODUCT_VIEWED", payload={"product_id": 1}))
    calls = {"count": 0}

    def flaky(event):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("temporary failure")

    handlers.HANDLERS["PRODUCT_VIEWED"].append(flaky)
    try:
        assert process_message(body, retry_count=0) == RETRY
        assert Event.objects.count() == 0                      # the failed attempt left no log row
        assert process_message(body, retry_count=1) == PROCESSED
    finally:
        handlers.HANDLERS["PRODUCT_VIEWED"].clear()
    assert Event.objects.count() == 1 and calls["count"] == 2


def test_message_that_keeps_failing_is_dead_lettered_and_can_be_replayed():
    body = message_for(emit("PRODUCT_VIEWED", payload={"product_id": 9}))

    def always_fails(event):
        raise RuntimeError("bug in handler")

    handlers.HANDLERS["PRODUCT_VIEWED"].append(always_fails)
    try:
        assert process_message(body, retry_count=0) == RETRY
        assert process_message(body, retry_count=1) == RETRY
        assert process_message(body, retry_count=2) == DEAD_LETTERED   # EVENTS_MAX_RETRIES = 3
    finally:
        handlers.HANDLERS["PRODUCT_VIEWED"].clear()

    dead = DeadLetterEvent.objects.get()
    assert dead.event_type == "PRODUCT_VIEWED" and "bug in handler" in dead.error and dead.retries == 3
    assert Event.objects.count() == 0

    broker = FakeBroker()                                    # after the bug is fixed
    assert replay_dead_letters(broker.publisher) == 1
    assert broker.messages[0]["payload"] == {"product_id": 9}
    assert process_message(json.dumps(broker.messages[0])) == PROCESSED
    assert DeadLetterEvent.objects.get().resolved_at is not None
    assert replay_dead_letters(broker.publisher) == 0         # already resolved


@pytest.mark.parametrize("body", ["not json", "{}", '{"event_id": "x"}'])
def test_garbage_messages_are_dead_lettered_immediately(body):
    assert process_message(body) == DEAD_LETTERED
    assert DeadLetterEvent.objects.count() == 1


# ---------- the whole path: business change -> outbox -> broker -> consumer ----------

def test_outage_then_recovery_then_duplicate_delivery_is_processed_once(make_user, make_product, place_order):
    user, product = make_user(), make_product(stock=5)
    place_order(user, (product, 1))
    expected = OutboxEvent.objects.count()
    assert expected >= 5

    relay_pending(broker_down)                              # outage: nothing is lost
    assert OutboxEvent.objects.filter(published_at__isnull=True).count() == expected

    broker = FakeBroker()
    relay_pending(broker.publisher)                         # recovery
    assert len(broker.messages) == expected

    for message in broker.messages + broker.messages:       # the broker delivers everything twice
        process_message(json.dumps(message))
    assert Event.objects.count() == expected                # each event is stored exactly once


# ---------- events emitted by the commerce code ----------

def test_checkout_emits_order_and_payment_events(make_user, make_product, place_order):
    user, product = make_user(), make_product(stock=5)
    order = place_order(user, (product, 2))

    emitted = types()
    for name in ("ORDER_CREATED", "PAYMENT_SUCCEEDED", "ORDER_COMPLETED", "INVENTORY_UPDATED", "CART_ITEM_ADDED"):
        assert name in emitted
    assert "PAYMENT_FAILED" not in emitted
    completed = OutboxEvent.objects.get(event_type="ORDER_COMPLETED")
    assert completed.user_id == user.id and completed.entity_id == order.id
    assert completed.payload["total"] == str(order.total)


def test_declined_payment_emits_failure_but_not_completion(make_user, make_product):
    user, product = make_user(), make_product(stock=5)
    cart_services.add_item(cart_services.get_active_cart(user=user), product.id, 1)
    with pytest.raises(order_services.PaymentDeclined):
        order_services.checkout(user, dict(SHIPPING), "card", "4000000000000002")

    emitted = types()
    assert "PAYMENT_FAILED" in emitted and "ORDER_CREATED" in emitted
    assert "ORDER_COMPLETED" not in emitted and "PAYMENT_SUCCEEDED" not in emitted
    assert OutboxEvent.objects.get(event_type="PAYMENT_FAILED").payload["reason"] == "card_declined"


def test_cancelling_emits_cancelled_and_stock_events(make_user, make_product, place_order):
    user, product = make_user(), make_product(stock=5)
    order = place_order(user, (product, 1))
    OutboxEvent.objects.all().delete()

    order_services.change_status(order.id, "CANCELLED")
    emitted = types()
    assert "ORDER_CANCELLED" in emitted and "INVENTORY_UPDATED" in emitted


def test_stock_low_fires_once_per_crossing_not_on_every_sale(make_product):
    product = make_product(stock=10, threshold=3)
    OutboxEvent.objects.all().delete()

    inventory.adjust_stock(product.id, -6, "ADJUSTMENT", "sale")   # 4 left: still above threshold
    assert "STOCK_LOW" not in types()
    inventory.adjust_stock(product.id, -1, "ADJUSTMENT", "sale")   # 3 left: crossed
    inventory.adjust_stock(product.id, -1, "ADJUSTMENT", "sale")   # 2 left: already low, no repeat
    assert types().count("STOCK_LOW") == 1
    inventory.adjust_stock(product.id, -2, "ADJUSTMENT", "sale")   # 0 left: out of stock, one more
    assert types().count("STOCK_LOW") == 2


def test_restocked_fires_after_sold_out_but_not_for_new_products(make_product):
    new_product = make_product(stock=5)
    assert "STOCK_RESTOCKED" not in types()                         # initial stock is not a restock

    inventory.adjust_stock(new_product.id, -5, "ADJUSTMENT", "all sold")
    inventory.adjust_stock(new_product.id, 10, "RESTOCK")
    assert types().count("STOCK_RESTOCKED") == 1


def test_cart_events_identify_the_user_or_the_anonymous_session(make_user, make_product):
    product = make_product()
    user = make_user()
    cart_services.add_item(cart_services.get_active_cart(user=user), product.id, 2)
    guest_cart = cart_services.get_active_cart(session_key="guest-1")
    cart_services.add_item(guest_cart, product.id, 1)
    cart_services.remove_item(guest_cart, guest_cart.items.get().id)

    added = list(OutboxEvent.objects.filter(event_type="CART_ITEM_ADDED").order_by("id"))
    assert (added[0].user_id, added[0].session_key, added[0].payload["quantity"]) == (user.id, "", 2)
    assert (added[1].user_id, added[1].session_key) == (None, "guest-1")
    removed = OutboxEvent.objects.get(event_type="CART_ITEM_REMOVED")
    assert removed.session_key == "guest-1" and removed.payload == {"product_id": product.id}


def test_product_view_and_search_are_recorded(client, make_product):
    product = make_product("Blue Lamp")
    OutboxEvent.objects.all().delete()   # ignore the product's own initial-stock event
    client.credentials(HTTP_X_SESSION_ID="browser-9")
    client.get(f"/products/{product.id}/")
    client.get("/products/?q=lamp")
    client.get("/products/")                                         # no search text: no event
    client.get("/products/99999/")                                   # not found: no event

    viewed = OutboxEvent.objects.get(event_type="PRODUCT_VIEWED")
    assert (viewed.entity_id, viewed.session_key) == (product.id, "browser-9")
    assert OutboxEvent.objects.get(event_type="PRODUCT_SEARCHED").payload == {"query": "lamp"}
    assert OutboxEvent.objects.count() == 2


def test_checkout_started_endpoint(client, auth_client, make_user):
    assert client.post("/events/checkout-started/").status_code == 202
    user = make_user()
    assert auth_client(user).post("/events/checkout-started/").status_code == 202
    events = list(OutboxEvent.objects.filter(event_type="CHECKOUT_STARTED").order_by("id"))
    assert [e.user_id for e in events] == [None, user.id]


# ---------- operations API ----------

def test_event_log_and_system_health_are_staff_only(client, auth_client, make_user):
    for url in ("/events/", "/events/dead-letters/", "/analytics/system/"):
        assert client.get(url).status_code == 401
        assert auth_client(make_user()).get(url).status_code == 403
        assert auth_client(make_user(role="OPERATIONS")).get(url).status_code == 200


def test_event_log_filters_by_type(auth_client, make_user):
    for event_type, payload in (("PRODUCT_VIEWED", {"product_id": 1}), ("PRODUCT_SEARCHED", {"query": "x"})):
        process_message(json.dumps(emit(event_type, payload=payload).to_message()))
    ops = auth_client(make_user(role="OPERATIONS"))
    assert ops.get("/events/").json()["count"] == 2
    filtered = ops.get("/events/?event_type=PRODUCT_SEARCHED").json()
    assert filtered["count"] == 1 and filtered["results"][0]["payload"] == {"query": "x"}


def test_system_health_reports_outbox_and_dead_letters(auth_client, make_user):
    emit("PRODUCT_VIEWED", payload={"product_id": 1})
    relay_pending(broker_down)
    DeadLetterEvent.objects.create(event_id="x", raw_message="{}", error="boom")

    data = auth_client(make_user(role="ADMIN")).get("/analytics/system/").json()
    assert data["outbox_pending"] == 1 and data["outbox_failing"] == 1
    assert data["dead_letters_unresolved"] == 1
    assert data["queue"] is None   # management API not configured
