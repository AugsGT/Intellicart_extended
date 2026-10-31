import json
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.ai_assistant import ollama
from apps.cart import services as cart_services
from apps.cart.models import Cart, CartItem
from apps.customer_intelligence import intent
from apps.customer_intelligence.models import IntentScore
from apps.events.consumer import PROCESSED, process_message
from apps.events.models import OutboxEvent
from apps.interventions import messages, rescue
from apps.interventions.models import Intervention
from apps.interventions.scanner import scan_abandoned_carts
from apps.orders import services as order_services

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def no_real_ollama(monkeypatch):
    """Rescue messages try Ollama first; tests must never reach a real server."""

    def unavailable(*args, **kwargs):
        raise ollama.OllamaUnavailable("no server in tests")

    monkeypatch.setattr(ollama, "chat", unavailable)


def idle(cart, minutes=60):
    """Make a cart look untouched for a while."""
    CartItem.objects.filter(cart=cart).update(updated_at=timezone.now() - timedelta(minutes=minutes))


# ---------- intent score ----------

def test_intent_weights_caps_and_tiers(make_event):
    for _ in range(20):
        make_event("PRODUCT_VIEWED", session="s")           # capped at 10 views = 20 points
    for _ in range(9):
        make_event("PRODUCT_SEARCHED", session="s")         # capped at 5 searches = 5 points
    make_event("CART_ITEM_ADDED", session="s")              # 5
    result = intent.compute_intent(None, "s")
    assert result.score == 30 and result.tier == "MEDIUM"
    assert result.basis["view_count"] == 20 and result.basis["weights"]["view_cap"] == 10

    make_event("CHECKOUT_STARTED", session="s")             # +15
    assert intent.compute_intent(None, "s").tier == "HIGH"
    assert intent.compute_intent(None, "other-browser").tier == "LOW"


def test_intent_follows_the_user_across_sessions_and_counts_only_real_purchases(make_user, make_product, make_event, place_order):
    user, product = make_user(), make_product(stock=5)
    make_event("PRODUCT_VIEWED", user=user, session="phone")
    make_event("PRODUCT_VIEWED", user=user, session="laptop")
    assert intent.compute_intent(user.id, "").basis["view_count"] == 2

    order = place_order(user, (product, 1))
    assert intent.compute_intent(user.id, "").basis["prior_orders"] == 1
    order_services.change_status(order.id, "CANCELLED")
    assert intent.compute_intent(user.id, "").basis["prior_orders"] == 0   # a cancelled order is not a purchase


def test_every_score_is_stored_with_its_basis(make_event):
    make_event("PRODUCT_VIEWED", session="s")
    intent.compute_and_record_intent(None, "s")
    stored = IntentScore.objects.get()
    assert stored.score == 2 and stored.basis["view_count"] == 1


# ---------- scanner ----------

def test_scanner_flags_an_idle_cart_once(make_product):
    cart = cart_services.get_active_cart(session_key="guest")
    cart_services.add_item(cart, make_product().id, 1)
    OutboxEvent.objects.all().delete()

    assert scan_abandoned_carts() == 0                       # just touched: not abandoned
    idle(cart)
    assert scan_abandoned_carts() == 1
    assert scan_abandoned_carts() == 0                       # flagged already: no repeat

    event = OutboxEvent.objects.get(event_type="CART_ABANDONED")
    assert (event.session_key, event.entity_id, event.payload) == ("guest", cart.id, {"cart_id": cart.id})


def test_scanner_flags_again_after_new_activity_and_skips_empty_or_finished_carts(make_user, make_product, place_order):
    product = make_product(stock=10)
    cart = cart_services.get_active_cart(session_key="guest")
    cart_services.add_item(cart, product.id, 1)
    idle(cart)
    scan_abandoned_carts()

    # Time passes: the first flag is now 2 hours old. The shopper comes back and leaves again.
    Cart.objects.filter(pk=cart.pk).update(abandonment_flagged_at=timezone.now() - timedelta(hours=2))
    cart_services.add_item(cart, product.id, 1)
    idle(cart, minutes=60)
    assert scan_abandoned_carts() == 1

    empty = cart_services.get_active_cart(session_key="empty")
    assert scan_abandoned_carts() == 0 and empty.items.count() == 0

    user = make_user()
    place_order(user, (product, 1))                         # checked-out carts are never abandoned
    Cart.objects.filter(user=user).update(updated_at=timezone.now() - timedelta(days=1))
    assert scan_abandoned_carts() == 0


def test_scanner_records_the_user_of_a_user_cart(make_user, make_product):
    user = make_user()
    cart = cart_services.get_active_cart(user=user)
    cart_services.add_item(cart, make_product().id, 1)
    idle(cart)
    scan_abandoned_carts()
    event = OutboxEvent.objects.get(event_type="CART_ABANDONED")
    assert (event.user_id, event.session_key) == (user.id, "")


# ---------- decision rules ----------

def context(**overrides):
    values = dict(cart_value=Decimal("500"), item_names=["A"], stock_ok=True, low_stock_item="", view_count=0,
                  checkout_started=False, prior_abandonment_count=0, intent_tier="LOW")
    return rescue.RescueContext(**{**values, **overrides})


@pytest.mark.parametrize(
    "overrides,action,rule",
    [
        ({"cart_value": Decimal("5")}, "NO_ACTION", "cart_too_small"),
        ({"checkout_started": True, "stock_ok": False, "low_stock_item": "A"}, "STOCK_ALTERNATIVE", "low_stock_at_checkout"),
        ({"checkout_started": True, "intent_tier": "HIGH"}, "CHECKOUT_REMINDER", "high_intent_checkout_abandon"),
        ({"checkout_started": True, "prior_abandonment_count": 1}, "CHECKOUT_REMINDER", "repeat_abandon_at_checkout"),
        ({"view_count": 3}, "REMINDER", "first_abandonment_engaged"),
        ({"view_count": 3, "prior_abandonment_count": 2}, "REMINDER", "default_reminder"),
        ({}, "REMINDER", "default_reminder"),
    ],
)
def test_rule_table_first_match_wins_and_names_its_rule(overrides, action, rule):
    assert rescue.decide_action(context(**overrides)) == (action, rule)


def test_no_action_can_promise_a_discount_or_reservation():
    assert not any(a for a in Intervention.Action.values if "DISCOUNT" in a or "OFFER" in a)
    for text in messages.TEMPLATES.values():
        assert messages.is_acceptable(text), text


# ---------- message writing ----------

def stub_model(monkeypatch, text):
    monkeypatch.setattr(ollama, "chat", lambda *a, **k: {"message": {"content": text}})


def test_model_message_is_used_when_it_passes_the_checks(monkeypatch):
    stub_model(monkeypatch, "Your Nimbus laptop is still waiting in your cart.")
    assert messages.craft_message("REMINDER", {"items_in_cart": ["Nimbus"]}) == ("Your Nimbus laptop is still waiting in your cart.", "llm")


@pytest.mark.parametrize(
    "bad",
    ["Get 10% off your cart today!", "Here is a discount code for you", "Hurry, your cart expires soon", "It is reserved for 2 hours",
     "Free shipping if you check out now", "", "x" * 300, "Two\nlines"],
)
def test_unsuitable_model_messages_fall_back_to_the_template(monkeypatch, bad):
    stub_model(monkeypatch, bad)
    assert messages.craft_message("REMINDER", {}) == (messages.TEMPLATES["REMINDER"], "template")


def test_template_is_used_when_ollama_is_down_or_llm_is_off(monkeypatch, settings):
    assert messages.craft_message("CHECKOUT_REMINDER", {}) == (messages.TEMPLATES["CHECKOUT_REMINDER"], "template")
    stub_model(monkeypatch, "A perfectly fine sentence.")
    settings.RESCUE_USE_LLM = False
    assert messages.craft_message("REMINDER", {})[1] == "template"


# ---------- the handler, end to end through the consumer ----------

def abandoned_event(cart, user=None, session=""):
    return json.dumps({
        "event_id": "11111111-0000-4000-8000-%012d" % cart.id, "event_type": "CART_ABANDONED",
        "user_id": getattr(user, "id", None), "session_id": session or None, "entity_id": cart.id,
        "payload": {"cart_id": cart.id}, "timestamp": timezone.now().isoformat(),
    })


def test_abandoned_cart_produces_one_explained_intervention(make_product, make_event):
    cart = cart_services.get_active_cart(session_key="guest")
    cart_services.add_item(cart, make_product("Lamp", "500").id, 1)
    for _ in range(3):
        make_event("PRODUCT_VIEWED", session="guest")

    assert process_message(abandoned_event(cart, session="guest")) == PROCESSED
    intervention = Intervention.objects.get()
    assert (intervention.action, intervention.rule, intervention.status) == ("REMINDER", "first_abandonment_engaged", "SENT")
    assert intervention.signals["view_count"] == 3 and intervention.cart_value == Decimal("500")
    assert intervention.message == messages.TEMPLATES["REMINDER"] and intervention.message_source == "template"
    assert IntentScore.objects.filter(session_key="guest").exists()

    process_message(abandoned_event(cart, session="guest"))   # delivered twice: still one decision
    assert Intervention.objects.count() == 1


def test_small_or_emptied_carts_are_handled_quietly(make_product):
    small = cart_services.get_active_cart(session_key="small")
    cart_services.add_item(small, make_product("Pencil", "2").id, 1)
    process_message(abandoned_event(small, session="small"))
    logged = Intervention.objects.get()
    assert (logged.action, logged.status, logged.message) == ("NO_ACTION", "LOGGED", "")   # recorded, never shown

    emptied = cart_services.get_active_cart(session_key="emptied")
    cart_services.add_item(emptied, make_product("Mug", "100").id, 1)
    emptied.items.all().delete()
    process_message(abandoned_event(emptied, session="emptied"))
    assert Intervention.objects.count() == 1                 # nothing new: the cart was emptied meanwhile


def test_a_completed_order_marks_the_intervention_recovered(make_user, make_product, place_order):
    user, product = make_user(), make_product(stock=5)
    cart = cart_services.get_active_cart(user=user)
    cart_services.add_item(cart, product.id, 1)
    process_message(abandoned_event(cart, user=user))
    assert Intervention.objects.get().outcome == ""

    order = order_services.checkout(user, {"full_name": "A", "address_line1": "B", "city": "C", "state": "D", "postal_code": "560001", "phone": "9999999999"}, "cod")
    completed = OutboxEvent.objects.get(event_type="ORDER_COMPLETED", entity_id=order.id)
    assert process_message(json.dumps(completed.to_message())) == PROCESSED
    recovered = Intervention.objects.get()
    assert recovered.outcome == "RECOVERED" and recovered.outcome_at is not None


def test_back_in_stock_notifies_interested_customers_once(make_user, make_product, make_event):
    product = make_product("Sneaker", stock=0)
    fan, bystander = make_user(), make_user()
    make_event("PRODUCT_VIEWED", user=fan, session="s1", entity=product.id)
    make_event("PRODUCT_VIEWED", session="old", entity=product.id, when=timezone.now() - timedelta(days=30))
    make_event("PRODUCT_VIEWED", user=bystander, entity=make_product("Other").id)

    restocked = {"event_id": "22222222-0000-4000-8000-000000000001", "event_type": "STOCK_RESTOCKED", "user_id": None,
                 "session_id": None, "entity_id": product.id, "payload": {"product_id": product.id, "stock": 5},
                 "timestamp": timezone.now().isoformat()}
    process_message(json.dumps(restocked))
    alert = Intervention.objects.get()
    assert (alert.user_id, alert.action, alert.message) == (fan.id, "BACK_IN_STOCK_ALERT", "Good news - Sneaker is back in stock!")

    restocked["event_id"] = "22222222-0000-4000-8000-000000000002"   # restocked again before they react
    process_message(json.dumps(restocked))
    assert Intervention.objects.count() == 1


# ---------- customer API ----------

def test_active_intervention_is_shown_dismissed_and_isolated_between_customers(client, auth_client, make_user):
    mine = Intervention.objects.create(session_key="me", trigger_event_type="CART_ABANDONED", trigger_event_id="x",
                                       action="REMINDER", rule="default_reminder", message="Hello", status="SENT")
    theirs = Intervention.objects.create(session_key="them", trigger_event_type="CART_ABANDONED", trigger_event_id="y",
                                         action="REMINDER", rule="default_reminder", message="Secret", status="SENT")
    client.credentials(HTTP_X_SESSION_ID="me")

    assert client.get("/interventions/active/").json()["message"] == "Hello"
    assert client.post(f"/interventions/{theirs.id}/dismiss/").status_code == 404     # not mine
    assert client.post(f"/interventions/{theirs.id}/click/").status_code == 404

    assert client.post(f"/interventions/{mine.id}/click/").status_code == 200
    mine.refresh_from_db()
    assert mine.clicked_at is not None
    assert client.post(f"/interventions/{mine.id}/dismiss/").status_code == 200
    assert client.get("/interventions/active/").json() is None


def test_stale_and_logged_interventions_are_not_shown(client):
    old = Intervention.objects.create(session_key="s", trigger_event_type="CART_ABANDONED", trigger_event_id="a",
                                      action="REMINDER", rule="r", message="Old", status="SENT")
    Intervention.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=8))
    Intervention.objects.create(session_key="s", trigger_event_type="CART_ABANDONED", trigger_event_id="b",
                                action="NO_ACTION", rule="cart_too_small", status="LOGGED")
    client.credentials(HTTP_X_SESSION_ID="s")
    assert client.get("/interventions/active/").json() is None


def test_a_logged_in_user_sees_their_account_interventions_from_any_browser(auth_client, make_user):
    user = make_user()
    Intervention.objects.create(user_id=user.id, trigger_event_type="CART_ABANDONED", trigger_event_id="u",
                                action="REMINDER", rule="r", message="For you", status="SENT")
    assert auth_client(user).get("/interventions/active/").json()["message"] == "For you"
    assert auth_client(make_user()).get("/interventions/active/").json() is None


def test_staff_can_list_decisions_and_the_high_intent_view(client, auth_client, make_user, make_event):
    Intervention.objects.create(session_key="s", trigger_event_type="CART_ABANDONED", trigger_event_id="z",
                                action="REMINDER", rule="default_reminder", message="m", status="SENT")
    for _ in range(10):
        make_event("PRODUCT_VIEWED", session="keen")
        make_event("CART_ITEM_ADDED", session="keen")
    intent.compute_and_record_intent(None, "keen")

    for url in ("/interventions/", "/customer-intelligence/high-intent/"):
        assert client.get(url).status_code == 401
        assert auth_client(make_user()).get(url).status_code == 403
    ops = auth_client(make_user(role="OPERATIONS"))
    assert ops.get("/interventions/").json()["count"] == 1
    high = ops.get("/customer-intelligence/high-intent/").json()
    assert high[0]["session_id"] == "keen" and high[0]["tier"] == "HIGH" and high[0]["basis"]["view_count"] == 10
