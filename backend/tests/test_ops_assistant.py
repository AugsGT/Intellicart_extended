from datetime import datetime, time, timedelta, timezone as dt_timezone

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.ai_assistant import ollama, ops_orchestrator, ops_tools
from apps.ai_assistant.models import Conversation, Message
from apps.cart.models import Cart, CartItem
from apps.demand_intelligence import data
from apps.events.models import DeadLetterEvent, Event, OutboxEvent
from apps.interventions.models import Intervention
from apps.inventory import services as inventory
from apps.inventory.models import Alert, StockMovement
from apps.orders.models import Order, OrderItem
from apps.products.models import Product
from tests.conftest import SHIPPING

pytestmark = pytest.mark.django_db

TEN_QUESTIONS = [
    ("Which products have experienced a sudden demand increase?", "get_demand_trends"),
    ("Which products have declining sales?", "get_demand_trends"),
    ("Which products are likely to run out of stock?", "get_demand_trends"),
    ("Why has inventory decreased?", "get_inventory_statistics"),
    ("Which products need restocking?", "get_demand_trends"),
    ("What are the top-selling products?", "get_product_performance"),
    ("How has demand changed over the last 30 days?", "get_sales_history"),
    ("Which products have unusual sales patterns?", "get_demand_trends"),
    ("What is our current cancellation rate?", "get_order_analytics"),
    ("What operational issues need attention?", "get_stock_alerts"),
]


@pytest.fixture(autouse=True)
def no_real_ollama(monkeypatch):
    def unavailable(*args, **kwargs):
        raise ollama.OllamaUnavailable("no server in tests")

    monkeypatch.setattr(ollama, "chat", unavailable)


@pytest.fixture()
def sell(make_user):
    buyer = make_user()

    def _sell(product, units, days_ago=1, status="CONFIRMED", payment="PAID"):
        day = data.last_complete_day() - timedelta(days=days_ago - 1)
        total = product.price * units
        order = Order.objects.create(user=buyer, status=status, payment_status=payment, payment_method="cod",
                                     subtotal=total, tax=0, shipping=0, total=total, **SHIPPING)
        OrderItem.objects.create(order=order, product=product, name=product.name, unit_price=product.price, quantity=units)
        Order.objects.filter(pk=order.pk).update(created_at=datetime.combine(day, time(12, 0), tzinfo=dt_timezone.utc))
        return order

    return _sell


@pytest.fixture()
def staff(make_user, auth_client):
    user = make_user(role="OPERATIONS")
    api = auth_client(user)
    api.user = user
    api.conversation = api.post("/ops-assistant/conversations/", {}, format="json").json()["id"]
    return api


def ask(api, text, conversation=None):
    response = api.post(f"/ops-assistant/conversations/{conversation or api.conversation}/messages/", {"text": text}, format="json")
    assert response.status_code == 200, response.content
    return response.json()["message"]


def tools_used(message):
    return [t["name"] for t in message["payload"]["tools"]]


# ---------- who may use it ----------

def test_staff_only_everywhere(client, auth_client, make_user):
    for url, method in (("/ops-assistant/conversations/", "get"), ("/ops-assistant/conversations/", "post")):
        assert getattr(client, method)(url).status_code == 401
        assert getattr(auth_client(make_user()), method)(url).status_code == 403
        assert getattr(auth_client(make_user(role="OPERATIONS")), method)(url).status_code in (200, 201)
        assert getattr(auth_client(make_user(role="ADMIN")), method)(url).status_code in (200, 201)


def test_a_customer_cannot_reach_any_conversation_even_by_id(staff, auth_client, make_user):
    customer = auth_client(make_user())
    base = f"/ops-assistant/conversations/{staff.conversation}/"
    assert customer.get(base).status_code == 403
    assert customer.post(base + "messages/", {"text": "What is our current cancellation rate?"}, format="json").status_code == 403
    assert customer.delete(base).status_code == 403


def test_a_demoted_staff_member_loses_access_immediately(make_user, login_as):
    user = make_user(role="OPERATIONS")
    api = login_as(user)                                                         # a real login token, as the browser uses
    conversation = api.post("/ops-assistant/conversations/", {}, format="json").json()["id"]
    assert api.get("/ops-assistant/conversations/").status_code == 200

    User.objects.filter(pk=user.pk).update(role="CUSTOMER")                      # the token is unchanged; the role is read from the database
    assert api.get("/ops-assistant/conversations/").status_code == 403
    assert api.post(f"/ops-assistant/conversations/{conversation}/messages/", {"text": "hi"}, format="json").status_code == 403


def test_staff_only_see_their_own_conversations(staff, auth_client, make_user):
    ask(staff, "What is our current cancellation rate?")
    colleague = auth_client(make_user(role="ADMIN"))
    assert colleague.get("/ops-assistant/conversations/").json()["count"] == 0
    assert colleague.get(f"/ops-assistant/conversations/{staff.conversation}/").status_code == 404
    assert colleague.post(f"/ops-assistant/conversations/{staff.conversation}/messages/", {"text": "hi"}, format="json").status_code == 404


def test_shopping_and_operations_conversations_never_mix(staff, auth_client, make_user):
    admin = make_user(role="ADMIN")
    api = auth_client(admin)
    shopping_id = api.post("/assistant/conversations/", {}, format="json").json()["id"]
    ops_id = api.post("/ops-assistant/conversations/", {}, format="json").json()["id"]
    assert api.get(f"/assistant/conversations/{ops_id}/").status_code == 404
    assert api.get(f"/ops-assistant/conversations/{shopping_id}/").status_code == 404
    assert api.get("/assistant/conversations/").json()["count"] == 1 and api.get("/ops-assistant/conversations/").json()["count"] == 1


def test_the_tools_refuse_non_staff_even_if_a_view_forgot_to_check(make_user):
    for who in (None, make_user()):
        with pytest.raises(ops_tools.NotAllowed):
            ops_tools.dispatch("get_order_analytics", {}, who)
    assert "error" in ops_tools.dispatch("delete_everything", {}, make_user(role="ADMIN"))


# ---------- the ten questions from the brief ----------

@pytest.mark.parametrize("question,tool", TEN_QUESTIONS)
def test_each_standard_question_is_answered_from_a_tool_not_the_model(staff, question, tool):
    message = ask(staff, question)                       # no Ollama in these tests: only the rules can answer
    assert tool in tools_used(message)
    assert message["content"] and "language model is not available" not in message["content"]


def test_questions_with_no_data_get_honest_answers_not_errors(staff):
    answers = {q: ask(staff, q)["content"] for q, _ in TEN_QUESTIONS}
    assert "No product has a sudden demand increase" in answers[TEN_QUESTIONS[0][0]]
    assert "No completed sales" in answers["What are the top-selling products?"]
    assert "n/a (no orders in the period)" in answers["What is our current cancellation rate?"]
    assert "No unusual sales patterns" in answers["Which products have unusual sales patterns?"]


# ---------- every figure comes from the data ----------

def test_cancellation_rate_matches_the_database(staff, make_product, sell):
    product = make_product(stock=500)
    for _ in range(8):
        sell(product, 1)
    sell(product, 1, status="CANCELLED", payment="REFUNDED")
    sell(product, 1, status="CANCELLED", payment="REFUNDED")
    sell(product, 1, status="FAILED", payment="FAILED")

    message = ask(staff, "What is our current cancellation rate?")
    # accepted = paid or refunded = 8 + 2 = 10; cancelled = 2 -> 20.0%; failed payments = 1 of 11 attempts -> 9.1%
    assert "cancellation rate is 20.0% (2 cancelled of 10 accepted orders)" in message["content"]
    assert "payment failure rate is 9.1% (1 failed payments)" in message["content"]
    rows = dict((r[0], r[1]) for r in message["payload"]["table"]["rows"])
    assert rows == {"Orders placed": 11, "Accepted (paid)": 10, "Cancelled": 2, "Failed payments": 1}


def test_top_sellers_match_hand_totals(staff, make_product, sell):
    big, small = make_product("Big seller", "1000", stock=900), make_product("Small seller", "500", stock=900)
    for days_ago in range(1, 11):
        sell(big, 3, days_ago=days_ago)
    sell(small, 4, days_ago=2)
    sell(big, 100, days_ago=2, status="CANCELLED", payment="REFUNDED")             # must not count

    message = ask(staff, "What are the top-selling products?")
    rows = message["payload"]["table"]["rows"]
    assert rows[0][:3] == ["Big seller", 30, "₹30,000"] and rows[1][:3] == ["Small seller", 4, "₹2,000"]


def test_sales_history_totals_and_comparison(staff, make_product, sell):
    product = make_product("Item", "100", stock=900)
    for days_ago in range(1, 11):                      # current 30 days: 10 units
        sell(product, 1, days_ago=days_ago)
    for days_ago in range(31, 36):                     # previous 30 days: 5 units
        sell(product, 1, days_ago=days_ago)

    message = ask(staff, "How has demand changed over the last 30 days?")
    assert "10 units, ₹1,000 from 10 orders" in message["content"]
    assert "The 30 days before: 5 units, ₹500" in message["content"] and "units +100.0%" in message["content"]
    assert sum(r[1] for r in message["payload"]["table"]["rows"]) == 10


def test_inventory_explanation_for_a_named_product(staff, make_product):
    product = make_product("Pulse Go Earbuds", stock=0)
    inventory.adjust_stock(product.id, 100, "INITIAL")
    StockMovement.objects.filter(product=product).update(created_at=timezone.now() - timedelta(days=60))   # before the 30-day window
    inventory.adjust_stock(product.id, -30, "ORDER", reference="order:1")
    inventory.adjust_stock(product.id, 10, "RESTOCK")
    inventory.adjust_stock(product.id, -5, "ADJUSTMENT", "damaged in storage")

    message = ask(staff, "Why has the stock of Pulse Go Earbuds dropped?")
    assert "stock fell from 100 to 75 over the last 30 days (net -25)" in message["content"]
    assert "Movements in that period: sold in orders -30, manual adjustments -5, restocked +10." in message["content"]
    rows = {r[0]: r[1] for r in message["payload"]["table"]["rows"]}
    assert rows == {"sold in orders": "-30", "manual adjustments": "-5", "restocked": "+10"}


def test_a_follow_up_remembers_which_product_was_meant(staff, make_product):
    product = make_product("Pulse Go Earbuds", stock=50)
    inventory.adjust_stock(product.id, -5, "ADJUSTMENT", "recount")
    ask(staff, "Why did the stock of Pulse Go Earbuds go down?")
    follow_up = ask(staff, "And why is it lower than last week?")
    assert "Pulse Go Earbuds: stock" in follow_up["content"]


def test_demand_questions_use_the_demand_statistics(staff, make_product, sell):
    spiker, slow = make_product("Spiker", stock=500), make_product("Quiet", stock=5)
    for days_ago in range(4, 36):
        sell(spiker, 1, days_ago=days_ago)
        sell(slow, 1, days_ago=days_ago)
    for days_ago in range(1, 4):
        sell(spiker, 5, days_ago=days_ago)

    spikes = ask(staff, "Which products have experienced a sudden demand increase?")
    assert spikes["payload"]["table"]["rows"][0][0] == "Spiker" and spikes["payload"]["table"]["rows"][0][1] == "5.0/day"
    runout = ask(staff, "Which products are likely to run out of stock?")
    assert [r[0] for r in runout["payload"]["table"]["rows"]] == ["Quiet"]
    restock = ask(staff, "Which products need restocking?")
    assert restock["payload"]["table"]["rows"][0][:2] == ["Quiet", "urgent"] and "covers about" in restock["content"]


def test_the_issues_summary_collects_alerts_backlog_and_dead_letters(staff, make_product):
    product = make_product("Scarce", stock=3, threshold=5)
    inventory.adjust_stock(product.id, -1, "ADJUSTMENT", "recount")                    # raises a low-stock alert
    OutboxEvent.objects.create(event_type="PRODUCT_VIEWED", payload={"product_id": 1})
    DeadLetterEvent.objects.create(event_id="x", raw_message="{}", error="boom")

    message = ask(staff, "What operational issues need attention?")
    areas = {r[0]: r[1] for r in message["payload"]["table"]["rows"]}
    assert "1 open: 1 stock low" in areas["Open alerts"]
    waiting = OutboxEvent.objects.filter(published_at__isnull=True).count()
    assert f"{waiting} event(s) waiting" in areas["Event backlog"] and "1 event(s)" in areas["Dead letters"]
    assert "need attention" in message["content"]
    assert sorted(tools_used(message)) == ["get_demand_trends", "get_order_analytics", "get_stock_alerts", "get_system_health"]


def test_system_health_and_event_statistics_questions(staff, make_event):
    make_event("PRODUCT_VIEWED", session="a")
    make_event("PAYMENT_FAILED", payload={"order_id": 1, "amount": "1", "method": "card", "reason": "card_declined"})
    health = ask(staff, "How is the system health?")
    assert "Database up" in health["content"] and "2 events processed in the last hour" in health["content"]
    events = ask(staff, "How many events were processed today?")
    assert "2 events processed in the last 24 hours; 1 payment failure(s)" in events["content"]


@pytest.mark.parametrize(
    "text,days",
    [("sales over the last 7 days", 7), ("past 2 weeks", 14), ("last 3 months", 90), ("this week", 7), ("this month", 30), ("what happened", 30), ("last 400 days", 400)],
)
def test_period_wording(text, days):
    assert ops_orchestrator.days_in(text) == days
    assert ops_tools._days(400) == 180                                   # the tools clamp whatever the text asked for


# ---------- read-only, and tool audit ----------

def snapshot():
    return {model.__name__: model.objects.count() for model in (Order, OrderItem, Product, StockMovement, Alert, OutboxEvent, Event, DeadLetterEvent,
                                                                 CartItem, Cart, Intervention, User)} | {
        "stock": sum(Product.objects.values_list("stock", flat=True))}


def test_asking_questions_changes_nothing_but_the_conversation(staff, make_product, sell):
    product = make_product(stock=50, threshold=60)
    sell(product, 3)
    inventory.adjust_stock(product.id, -1, "ADJUSTMENT", "recount")
    before = snapshot()

    for question, _ in TEN_QUESTIONS:
        ask(staff, question)
    assert snapshot() == before
    assert Message.objects.count() == 2 * len(TEN_QUESTIONS)


@pytest.mark.parametrize(
    "request_text",
    ["Please set the stock of Widget to 500", "Cancel order 1 and refund it", "can you restock the earbuds?", "Delete all alerts", "mark order 3 as shipped",
     "Resolve the stock alert", "Add 50 units to the Nimbus laptop", "Send an email to every customer"],
)
def test_requests_to_change_something_are_refused_plainly_and_change_nothing(staff, make_product, sell, request_text):
    product = make_product("Widget", stock=40)
    order = sell(product, 2)
    before = snapshot()

    message = ask(staff, request_text)
    assert "I can only read data" in message["content"] and message["payload"]["tools"] == []
    assert snapshot() == before and Order.objects.get(pk=order.pk).status == "CONFIRMED"


def test_questions_that_merely_mention_those_words_are_still_answered(staff):
    assert "cancellation rate" in ask(staff, "What is our current cancellation rate?")["content"]
    assert "reordered" in ask(staff, "Which products need restocking?")["content"] or "reorder" in ask(staff, "Which products need restocking?")["content"].lower()


def test_the_assistant_has_no_tool_that_can_write():
    names = set(ops_tools.TOOL_FUNCTIONS)
    assert names == {t["function"]["name"] for t in ops_tools.TOOLS} == {
        "get_order_analytics", "get_inventory_statistics", "get_demand_trends", "get_product_performance",
        "get_stock_alerts", "get_sales_history", "get_system_health", "get_event_statistics"}
    assert not any(word in name for name in names for word in ("set", "update", "delete", "cancel", "create", "restock_product", "send", "add"))


def test_each_answer_records_which_tools_and_arguments_it_used(staff):
    message = ask(staff, "What is our current cancellation rate over the last 14 days?")
    assert message["payload"]["tools"] == [{"name": "get_order_analytics", "arguments": {"days": 14}}]


# ---------- language-model fallback ----------

def scripted(monkeypatch, *replies):
    calls = []

    def chat(messages, tools=None, timeout=None):
        calls.append({"messages": messages, "tools": tools})
        return replies[len(calls) - 1]

    monkeypatch.setattr(ollama, "chat", chat)
    return calls


def call(name, **arguments):
    return {"message": {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": name, "arguments": arguments}}]}}


def test_open_questions_use_the_model_with_read_only_tools_and_real_results(staff, make_product, sell, monkeypatch):
    product = make_product(stock=500)
    sell(product, 2)
    calls = scripted(monkeypatch, call("get_order_analytics", days=7),
                     {"message": {"role": "assistant", "content": "There was 1 successful order in the last 7 days."}})

    message = ask(staff, "Is the checkout behaving normally this week?")
    assert message["content"] == "There was 1 successful order in the last 7 days."
    assert "Every number you state must come from a tool call" in calls[0]["messages"][0]["content"]
    assert {t["function"]["name"] for t in calls[0]["tools"]} == set(ops_tools.TOOL_FUNCTIONS)
    tool_message = [m for m in calls[1]["messages"] if m["role"] == "tool"][0]
    assert '"successful_orders": 1' in tool_message["content"]
    assert tools_used(message) == ["get_order_analytics"]


def test_the_model_cannot_use_tools_that_do_not_exist_or_bad_arguments(staff, monkeypatch):
    calls = scripted(monkeypatch, call("update_stock", product_id=1, quantity=500), call("get_order_analytics", days="abc"),
                     call("get_sales_history", days=-5), {"message": {"role": "assistant", "content": "Done reading."}})
    message = ask(staff, "Can you look at the warehouse situation?")
    results = [m["content"] for call_ in calls[1:] for m in call_["messages"] if m["role"] == "tool"]
    assert any("Unknown tool 'update_stock'" in r for r in results)
    assert message["content"] == "Done reading."


def test_without_the_model_unknown_questions_list_what_can_be_asked(staff):
    message = ask(staff, "Tell me a joke about printers")
    assert "language model is not available" in message["content"]
    assert "What is our current cancellation rate?" in message["content"] and message["payload"]["tools"] == []


# ---------- API rules ----------

@pytest.mark.parametrize("payload", [{}, {"text": ""}, {"text": "   "}, {"text": "x" * 1001}])
def test_questions_are_validated(staff, payload):
    assert staff.post(f"/ops-assistant/conversations/{staff.conversation}/messages/", payload, format="json").status_code == 400


def test_conversations_have_a_size_limit(staff):
    conversation = Conversation.objects.get(pk=staff.conversation)
    Message.objects.bulk_create([Message(conversation=conversation, role="user", content="x") for _ in range(ops_orchestrator.MAX_MESSAGES)])
    response = staff.post(f"/ops-assistant/conversations/{staff.conversation}/messages/", {"text": "hi"}, format="json")
    assert response.status_code == 400 and "full" in response.json()["detail"]


def test_the_assistant_is_rate_limited(staff):
    codes = [staff.post(f"/ops-assistant/conversations/{staff.conversation}/messages/", {"text": "What is our current cancellation rate?"}, format="json").status_code
             for _ in range(32)]
    assert codes[:30] == [200] * 30 and 429 in codes[30:]


def test_staff_can_review_and_delete_their_history(staff):
    ask(staff, "What is our current cancellation rate?")
    detail = staff.get(f"/ops-assistant/conversations/{staff.conversation}/").json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"] and detail["title"].startswith("What is our current")
    assert staff.delete(f"/ops-assistant/conversations/{staff.conversation}/").status_code == 204


def test_indian_money_formatting():
    from apps.ai_assistant.formatting import money

    assert [money(v) for v in (999, 60000, 150000, 10943371, -4500)] == ["₹999", "₹60,000", "₹1,50,000", "₹1,09,43,371", "-₹4,500"]
