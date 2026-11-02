from datetime import timedelta

import pytest
from django.utils import timezone

from apps.ai_assistant import ollama
from apps.ai_assistant.models import Conversation, Message
from apps.cart.models import CartItem
from apps.events.models import OutboxEvent
from apps.inventory.models import StockMovement
from apps.orders.models import Order
from tests.advisor_catalogue import catalogue  # noqa: F401  (fixture)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def no_real_ollama(monkeypatch):
    def unavailable(*args, **kwargs):
        raise ollama.OllamaUnavailable("no server in tests")

    monkeypatch.setattr(ollama, "chat", unavailable)


@pytest.fixture()
def shopper(make_user, auth_client):
    user = make_user()
    api = auth_client(user)
    api.user = user
    api.conversation = api.post("/assistant/conversations/", {}, format="json").json()["id"]
    return api


def say(api, text, conversation=None):
    response = api.post(f"/assistant/conversations/{conversation or api.conversation}/messages/", {"text": text}, format="json")
    assert response.status_code == 200, response.content
    return response.json()


def reply(api, text):
    return say(api, text)["message"]


def card_names(message):
    return [c["name"] for c in message["payload"].get("cards", [])]


# ---------- the brief's multi-turn example, start to finish ----------

def test_full_conversation_ask_recommend_rerank_compare_and_confirmed_add_to_cart(shopper, catalogue):
    # "My budget is 60,000." -> we still need to know what to shop for.
    message = reply(shopper, "My budget is ₹60,000.")
    assert "What kind of product" in message["content"] and "Laptops" in message["content"]

    # They name the product; the budget is remembered, so we only ask about usage.
    message = reply(shopper, "A laptop please")
    assert "mainly use it for" in message["content"]
    assert "budget" not in message["content"].lower().split("?")[0]            # not asked again

    # Usage given: first recommendations, explained from catalogue data.
    message = reply(shopper, "Programming and occasional gaming")
    assert card_names(message)[0] in {"Alpha 14 Laptop", "Bravo 13 Laptop", "Endurance 15 Laptop", "Plain Laptop"}
    assert "Gamer 17 Laptop" not in card_names(message) and "Ghost 14 Laptop" not in card_names(message)   # over budget / out of stock
    assert "1 over your budget" in message["content"] and "1 out of stock" in message["content"]
    first_order = card_names(message)

    # Priorities change: the order is recomputed, and the customer repeats nothing.
    message = reply(shopper, "Battery life matters more than gaming performance")
    assert message["content"].startswith("Re-ranked")
    assert card_names(message)[0] == "Endurance 15 Laptop"                     # 20 hour battery
    assert "battery life" in message["content"]
    second_order = card_names(message)
    assert second_order != first_order

    # Compare the best two.
    message = reply(shopper, "Compare the best two")
    comparison = message["payload"]["comparison"]
    assert [p["name"] for p in comparison["products"]] == second_order[:2]
    assert "overall winner" in message["content"]                              # we explicitly do not pick one

    # Add the second one: nothing happens until the customer confirms.
    message = reply(shopper, "Add the second one to my cart")
    pending = message["payload"]["pending_action"]
    assert pending["type"] == "add_to_cart" and pending["product_id"] == catalogue_id(second_order[1], catalogue)
    assert "Nothing is added until you confirm" in message["content"]
    assert CartItem.objects.count() == 0

    # Confirm with the button endpoint.
    response = shopper.post(f"/assistant/conversations/{shopper.conversation}/confirm/", {"approve": True}, format="json")
    assert response.status_code == 200 and "is in your cart" in response.json()["message"]["content"]
    item = CartItem.objects.get()
    assert (item.cart.user_id, item.product_id, item.quantity) == (shopper.user.id, pending["product_id"], 1)

    # At no point did the assistant order, pay or touch stock.
    assert Order.objects.count() == 0 and not StockMovement.objects.filter(reason="ORDER").exists()


def catalogue_id(name, catalogue):
    return next(p.id for p in catalogue.values() if p.name == name)


def test_requirements_survive_across_turns_and_are_shown_to_the_customer(shopper, catalogue):
    say(shopper, "a laptop under 60000 for programming, warranty matters")
    detail = shopper.get(f"/assistant/conversations/{shopper.conversation}/").json()
    assert detail["understood"] == {"summary": "laptops up to ₹60,000 for programming", "priorities": ["warranty"],
                                    "budget": {"min": None, "max": 60000.0}, "usage": ["programming"]}
    assert len(detail["messages"]) == 2 and detail["title"].startswith("a laptop under 60000")


def test_the_four_example_requests_each_return_grounded_recommendations(shopper, catalogue, make_user, auth_client):
    expectations = {
        "My budget is ₹60,000. I need a laptop for programming, good battery life and reliable warranty service.": "Endurance 15 Laptop",
        "I need wireless earbuds under ₹3,000 with good noise cancellation.": "Pulse ANC Earbuds",
        # Durability itself cannot be verified, so it cannot separate the chairs; the tie goes to the better-documented one.
        "Suggest a durable office chair under ₹10,000.": "ErgoMesh Office Chair",
        "Find a phone with a good camera and at least two days of battery life.": "Cam X Phone",
    }
    real_names = {p.name for p in catalogue.values()}
    for text, top in expectations.items():
        api = auth_client(shopper.user)
        conversation = api.post("/assistant/conversations/", {}, format="json").json()["id"]
        # Phones/chairs/earbuds have no budget: say so, as a customer would.
        message = say(api, text, conversation)["message"]
        if not message["payload"].get("cards"):
            message = say(api, "no limit", conversation)["message"]
        if not message["payload"].get("cards"):
            message = say(api, "just show me", conversation)["message"]
        assert card_names(message)[0] == top, (text, message["content"])
        assert set(card_names(message)) <= real_names                          # every product shown exists in the catalogue


def test_unverifiable_requests_are_stated_honestly(shopper, catalogue):
    reply(shopper, "Find a phone with a good camera and at least two days of battery life.")
    message = reply(shopper, "no limit")
    assert "I can't verify from the catalogue" in message["content"] and "two day(s) of battery life" in message["content"]


def test_cards_carry_the_full_explanation(shopper, catalogue):
    message = reply(shopper, "a laptop under 60000 for programming with good battery life and warranty")
    explanation = message["payload"]["cards"][0]["explanation"]
    assert set(explanation) >= {"fits_budget", "budget_note", "meets", "does_not_meet", "unknown", "advantages", "limitations", "warranty", "match_summary"}
    assert explanation["match_summary"].startswith("Meets ")


def test_unavailable_results_are_explained_not_invented(shopper, catalogue):
    message = reply(shopper, "a laptop under 10000 for office work")
    assert not message["payload"].get("cards")
    assert "could not find" in message["content"] and "over your budget" in message["content"]


# ---------- cart safety ----------

def test_wanting_to_buy_something_is_a_search_not_a_cart_action(shopper, catalogue):
    message = reply(shopper, "I want to buy a laptop under 60000")
    assert "pending_action" not in message["payload"] and CartItem.objects.count() == 0


def test_cancelling_a_pending_action_adds_nothing(shopper, catalogue):
    reply(shopper, "a laptop under 60000 for programming")
    reply(shopper, "add the first one to my cart")
    message = reply(shopper, "no thanks, cancel")
    assert "have not added anything" in message["content"] and CartItem.objects.count() == 0
    assert shopper.get(f"/assistant/conversations/{shopper.conversation}/").json()["pending_action"] is None


def test_replying_yes_confirms_in_text(shopper, catalogue):
    reply(shopper, "a laptop under 60000 for programming")
    reply(shopper, "put the second one in my cart")
    message = reply(shopper, "yes")
    assert "is in your cart" in message["content"] and CartItem.objects.count() == 1


def test_a_pending_action_expires(shopper, catalogue):
    reply(shopper, "a laptop under 60000 for programming")
    reply(shopper, "add the first one to my cart")
    conversation = Conversation.objects.get(pk=shopper.conversation)
    conversation.pending_action = {**conversation.pending_action, "created_at": (timezone.now() - timedelta(minutes=30)).isoformat()}
    conversation.save()

    message = reply(shopper, "yes")
    assert CartItem.objects.count() == 0
    assert "I can help best when I know" in message["content"]      # "yes" with nothing live to confirm is just a message


def test_confirm_without_anything_pending_is_harmless(shopper):
    response = shopper.post(f"/assistant/conversations/{shopper.conversation}/confirm/", {"approve": True}, format="json")
    assert response.status_code == 200 and "nothing waiting" in response.json()["message"]["content"]
    assert CartItem.objects.count() == 0


def test_out_of_stock_products_are_not_added(shopper, catalogue):
    conversation = Conversation.objects.get(pk=shopper.conversation)
    conversation.last_results = [catalogue["ghost"].id]
    conversation.save()
    message = reply(shopper, "add it to my cart")
    assert "out of stock" in message["content"] and "pending_action" not in message["payload"]


def test_ambiguous_references_ask_which_one(shopper, catalogue):
    reply(shopper, "a laptop under 60000 for programming")
    message = reply(shopper, "add it to my cart")
    assert message["content"].startswith("Which one") and CartItem.objects.count() == 0


def test_details_and_warranty_come_from_the_catalogue(shopper, catalogue):
    reply(shopper, "a laptop under 60000 for programming")
    message = reply(shopper, "what warranty does the first one have?")
    text = message["content"]
    assert "Alpha 14 Laptop" in text and "Warranty: 24 months; type: On-site" in text
    assert message["payload"]["cards"]


def test_stating_a_warranty_requirement_is_not_mistaken_for_a_question(shopper, catalogue):
    reply(shopper, "a laptop under 60000 for programming")
    message = reply(shopper, "I need at least 2 years warranty")
    names = [c["name"] for c in message["payload"]["cards"]]
    assert names[0] == "Alpha 14 Laptop"                                       # the only laptop known to have 24 months
    plain = [c for c in message["payload"]["cards"] if c["name"] == "Plain Laptop"]
    assert all(any("does not list it" in t for t in c["explanation"]["unknown"]) for c in plain)   # no data: flagged, never assumed
    assert "Bravo 13 Laptop" not in names and "Endurance 15 Laptop" not in names   # 12 months: below what was asked


# ---------- language model fallback ----------

def test_open_questions_fall_back_to_the_model_and_use_only_tools(shopper, catalogue, monkeypatch):
    seen = {}

    def scripted(messages, tools=None, timeout=None):
        seen.setdefault("calls", []).append(messages)
        if len(seen["calls"]) == 1:
            return {"message": {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "check_stock", "arguments": {"product_id": catalogue["alpha"].id}}}]}}
        return {"message": {"role": "assistant", "content": "Alpha has 10 in stock."}}

    monkeypatch.setattr(ollama, "chat", scripted)
    reply(shopper, "a laptop under 60000 for programming")
    message = reply(shopper, "is there enough stock of the first one for my team?")
    assert message["content"] == "Alpha has 10 in stock."
    system = seen["calls"][0][0]["content"]
    assert "laptops up to ₹60,000" in system and "ONLY if it came back from a tool" in system
    tool_message = [m for m in seen["calls"][1] if m["role"] == "tool"][0]
    assert '"stock": 10' in tool_message["content"]


def test_without_the_model_open_questions_get_helpful_guidance(shopper, catalogue):
    message = reply(shopper, "tell me a joke about printers")
    assert "product type, your budget and what matters most" in message["content"]


# ---------- ownership, validation, limits, tracking ----------

def test_conversations_require_login(client):
    assert client.get("/assistant/conversations/").status_code == 401
    assert client.post("/assistant/conversations/", {}, format="json").status_code == 401


def test_customers_cannot_see_or_use_each_others_conversations(shopper, catalogue, make_user, auth_client):
    say(shopper, "a laptop under 60000 for programming")
    stranger = auth_client(make_user())
    base = f"/assistant/conversations/{shopper.conversation}/"
    assert stranger.get(base).status_code == 404
    assert stranger.post(base + "messages/", {"text": "hello"}, format="json").status_code == 404
    assert stranger.post(base + "confirm/", {"approve": True}, format="json").status_code == 404
    assert stranger.delete(base).status_code == 404
    assert stranger.get("/assistant/conversations/").json()["count"] == 0
    assert shopper.get("/assistant/conversations/").json()["count"] == 1


def test_a_customer_can_delete_their_conversation(shopper):
    assert shopper.delete(f"/assistant/conversations/{shopper.conversation}/").status_code == 204
    assert not Conversation.objects.exists()


@pytest.mark.parametrize("payload", [{}, {"text": ""}, {"text": "   "}, {"text": "x" * 1001}])
def test_messages_are_validated(shopper, payload):
    assert shopper.post(f"/assistant/conversations/{shopper.conversation}/messages/", payload, format="json").status_code == 400


def test_a_conversation_has_a_size_limit(shopper):
    from apps.ai_assistant import orchestrator

    conversation = Conversation.objects.get(pk=shopper.conversation)
    Message.objects.bulk_create([Message(conversation=conversation, role="user", content="x") for _ in range(orchestrator.MAX_MESSAGES)])
    response = shopper.post(f"/assistant/conversations/{shopper.conversation}/messages/", {"text": "hi"}, format="json")
    assert response.status_code == 400 and "full" in response.json()["detail"]


def test_the_advisor_is_rate_limited(shopper):
    codes = [shopper.post(f"/assistant/conversations/{shopper.conversation}/messages/", {"text": "hello"}, format="json").status_code for _ in range(32)]
    assert codes[:30] == [200] * 30 and 429 in codes[30:]


def test_showing_recommendations_is_tracked_as_an_advisor_event(shopper, catalogue):
    OutboxEvent.objects.all().delete()
    reply(shopper, "a laptop under 60000 for programming")
    event = OutboxEvent.objects.get(event_type="RECOMMENDATION_GENERATED")
    assert event.user_id == shopper.user.id and event.payload["kind"] == "advisor" and event.payload["product_ids"]


def test_advisor_clicks_use_the_existing_click_tracking(shopper, catalogue):
    response = shopper.post("/recommendations/click/", {"kind": "advisor", "product_id": catalogue["alpha"].id}, format="json")
    assert response.status_code == 202
