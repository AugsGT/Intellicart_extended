"""The operations assistant: answers staff questions from live data.

Common questions are routed by rules to the read-only tools in ops_tools.py, and the
answer text is written straight from the numbers the tools return. So the typical
answer needs no language model and cannot contain a statistic that is not in the
data. Anything the rules do not recognise goes to the language model, which may
only use the same read-only tools (see llm_answer).
"""
import json
import logging
import re

from django.db import transaction

from apps.ai_assistant import ollama, ops_tools
from apps.ai_assistant.formatting import money
from apps.ai_assistant.models import Conversation, Message
from apps.products.models import Product

logger = logging.getLogger("intellicart.ops_assistant")

MAX_MESSAGES = 200
MAX_TOOL_ROUNDS = 4

SUPPORTED = (
    "Which products have had a sudden demand increase? / Which products have declining sales? / Which products are likely to run out of stock? / "
    "Why has inventory decreased? / Which products need restocking? / What are the top-selling products? / "
    "How has demand changed over the last 30 days? / Which products have unusual sales patterns? / "
    "What is our current cancellation rate? / What operational issues need attention?"
)
FALLBACK = f"I can answer questions about demand, sales, stock, orders, alerts and system health. For example: {SUPPORTED}"
LLM_UNAVAILABLE = "I could not match that to one of my standard questions, and the language model is not available to try. " + FALLBACK

SYSTEM_PROMPT = (
    "You are Intellicart's operations assistant for staff. Money amounts are in Indian Rupees (write them with the ₹ sign, never $).\n"
    "Rules:\n"
    "- Every number you state must come from a tool call in this conversation. Never estimate, extrapolate or guess a figure.\n"
    "- If the data does not answer the question, say so.\n"
    "- Say which period and definition a figure uses. Do not call anything a forecast.\n"
    "- You can only read data. You cannot change orders, stock, prices, users or settings; if asked to, say you cannot and that a person must do it.\n"
    "- Keep answers short and factual."
)


# ---- small helpers -------------------------------------------------------------

def pct(value) -> str:
    return "n/a" if value is None else f"{value:+.1f}%"


def rate(value) -> str:
    return "n/a (no orders in the period)" if value is None else f"{value * 100:.1f}%"


def days_in(text: str, default: int = 30) -> int:
    match = re.search(r"(\d+)\s*(?:-|\s)?(day|days|week|weeks|month|months)\b", text)
    if match:
        number, unit = int(match.group(1)), match.group(2)
        return number * (7 if unit.startswith("week") else 30 if unit.startswith("month") else 1)
    for word, value in (("quarter", 90), ("month", 30), ("week", 7), ("year", 180)):
        if word in text:
            return value
    return default


def find_product(text: str, focus_id=None) -> Product | None:
    lowered = text.lower()
    for product in Product.objects.all():
        name = product.name.lower()
        if name in lowered or (len(" ".join(name.split()[:2])) > 5 and " ".join(name.split()[:2]) in lowered):
            return product
    if focus_id and re.search(r"\b(?:it|that|this|that product|this product)\b", lowered):
        return Product.objects.filter(pk=focus_id).first()
    return None


class Run:
    """Collects which tools an answer used, so staff can see where the numbers came from."""

    def __init__(self, user):
        self.user = user
        self.tools: list[dict] = []

    def call(self, name: str, **args) -> dict:
        result = ops_tools.dispatch(name, args, self.user)
        self.tools.append({"name": name, "arguments": args})
        return result


def answer(content: str, run: Run, columns=None, rows=None, **extra) -> dict:
    payload = {"tools": run.tools, **extra}
    if columns and rows:
        payload["table"] = {"columns": columns, "rows": rows}
    return {"content": content, "payload": payload}


# ---- the standard questions -----------------------------------------------------

def q_issues(text, run, focus):
    alerts, demand = run.call("get_stock_alerts"), run.call("get_demand_trends")
    health, orders = run.call("get_system_health"), run.call("get_order_analytics", days=7)
    rows = []
    if alerts["open_alerts"]:
        parts = ", ".join(f"{n} {kind.replace('_', ' ').lower()}" for kind, n in alerts["by_type"].items())
        rows.append(["Open alerts", f"{alerts['open_alerts']} open: {parts}"])
    for p in demand["at_risk"]:
        cover = f"{p['days_of_cover']} days of stock left" if p["days_of_cover"] is not None else "out of stock while selling"
        rows.append(["May run out", f"{p['name']}: {cover} ({p['stock']} units)"])
    for p in demand["spikes"]:
        rows.append(["Demand spike", f"{p['name']}: {p['burst_daily_average']}/day over the last 3 days vs usual {p['baseline_daily_average']}/day"])
    for p in demand["decreasing"]:
        rows.append(["Falling demand", f"{p['name']}: {pct(p['change_pct'])} vs the previous 28 days"])
    if health["database"] != "up":
        rows.append(["Database", "The database check failed"])
    if health["outbox_pending"]:
        age = health["outbox_oldest_pending_seconds"]
        rows.append(["Event backlog", f"{health['outbox_pending']} event(s) waiting to be sent" + (f", oldest {age}s" if age is not None else "")])
    if health["dead_letters_unresolved"]:
        rows.append(["Dead letters", f"{health['dead_letters_unresolved']} event(s) failed every retry and need a look"])
    current = orders["current"]
    rows.append(["Orders (7 days)", f"cancellation rate {rate(current['cancellation_rate'])}, payment failure rate {rate(current['payment_failure_rate'])} (for reference)"])

    attention = [r for r in rows if r[0] != "Orders (7 days)"]
    head = f"{len(attention)} item(s) need attention." if attention else "Nothing needs attention right now."
    return answer(f"{head} Details below. Demand figures use the last complete day ({demand['as_of']}).", run, ["Area", "Detail"], rows)


def q_why_inventory(text, run, focus):
    product = find_product(text, focus)
    days = days_in(text)
    stats = run.call("get_inventory_statistics", days=days, **({"product_id": product.id} if product else {}))
    reasons = stats["movements_by_reason"]
    labels = {"ORDER": "sold in orders", "CANCELLATION": "returned from cancelled orders", "RESTOCK": "restocked", "ADJUSTMENT": "manual adjustments", "INITIAL": "initial stock"}
    rows = [[labels.get(reason, reason), f"{info['units']:+d}", info["movements"]] for reason, info in sorted(reasons.items(), key=lambda item: item[1]["units"])]
    if stats["scope"] == "product":
        net = stats["net_change"]
        verb = "fell" if net < 0 else "rose" if net > 0 else "did not change"
        text_out = f"{stats['product']['name']}: stock {verb} from {stats['stock_at_start']} to {stats['stock_now']} over the last {days} days (net {net:+d})."
        breakdown = ", ".join(f"{labels.get(reason, reason)} {info['units']:+d}" for reason, info in sorted(reasons.items(), key=lambda item: item[1]["units"]))
        if breakdown:
            text_out += f" Movements in that period: {breakdown}."
        if not stats["ledger_consistent"]:
            text_out += " Warning: the stock level does not match the stock ledger."
        return answer(text_out, run, ["Reason", "Units", "Movements"], rows, focus_product_id=product.id)

    biggest = ", ".join(f"{p['name']} ({p['net_change']:+d})" for p in stats["biggest_decreases"]) or "none"
    net = stats["net_change"]
    text_out = (f"Across all products, stock changed by {net:+d} units over the last {days} days. "
                f"Biggest decreases: {biggest}. Name a product to see exactly why its stock changed.")
    return answer(text_out, run, ["Reason", "Units", "Movements"], rows)


def q_unusual(text, run, focus):
    demand = run.call("get_demand_trends")
    rows = [["Demand spike", p["name"], f"{p['burst_daily_average']}/day vs usual {p['baseline_daily_average']}/day"] for p in demand["spikes"]]
    rows += [["Falling demand", p["name"], f"{pct(p['change_pct'])} vs the previous 28 days"] for p in demand["decreasing"]]
    rows += [["Rising demand", p["name"], f"{pct(p['change_pct'])} vs the previous 28 days"] for p in demand["increasing"] if not p["spike"]]
    if not rows:
        return answer(f"No unusual sales patterns as of {demand['as_of']}: no spikes and no clear rises or falls. {demand['method']}", run)
    return answer(f"{len(rows)} unusual pattern(s) as of {demand['as_of']}. {demand['method']}", run, ["Pattern", "Product", "Detail"], rows)


def q_spikes(text, run, focus):
    demand = run.call("get_demand_trends")
    rows = [[p["name"], f"{p['burst_daily_average']}/day", f"{p['baseline_daily_average']}/day", pct(p["change_pct"])] for p in demand["spikes"]]
    rising = [p for p in demand["increasing"] if not p["spike"]]
    rows += [[f"{p['name']} (steady rise)", f"{p['recent_daily_average']}/day", f"{p['baseline_daily_average']}/day", pct(p["change_pct"])] for p in rising]
    if not rows:
        return answer(f"No product has a sudden demand increase as of {demand['as_of']}. A spike means the last 3 days were at least 6 units, double the usual pace and beyond normal variation.", run)
    return answer(
        f"{len(demand['spikes'])} product(s) with a sudden spike and {len(rising)} with a steady rise, as of {demand['as_of']}. "
        "A spike uses the last 3 days; a steady rise compares the last 7 days with the previous 28.",
        run, ["Product", "Recent pace", "Usual pace", "Change"], rows)


def q_decline(text, run, focus):
    demand = run.call("get_demand_trends")
    rows = [[p["name"], f"{p['recent_daily_average']}/day", f"{p['baseline_daily_average']}/day", pct(p["change_pct"])] for p in demand["decreasing"]]
    thin = len(demand["products_without_enough_history"])
    note = f" {thin} product(s) do not have enough sales history to judge." if thin else ""
    if not rows:
        return answer(f"No product shows a clear decline as of {demand['as_of']} (a fall of at least 25% that is beyond normal weekly variation).{note}", run)
    return answer(f"{len(rows)} product(s) with declining sales as of {demand['as_of']}, comparing the last 7 days with the previous 28.{note}", run, ["Product", "Last 7 days", "Usual pace", "Change"], rows)


def q_stockout(text, run, focus):
    demand = run.call("get_demand_trends")
    rows = [[p["name"], p["stock"], p["days_of_cover"] if p["days_of_cover"] is not None else "-", p["predicted_stockout_date"] or "-", p["stockout_risk"].replace("_", " ")] for p in demand["at_risk"]]
    if not rows:
        return answer(f"No product is predicted to run out soon as of {demand['as_of']} (every product has at least 14 days of cover at its recent pace).", run)
    return answer(
        f"{len(rows)} product(s) may run out. Days of cover is stock divided by the faster of the recent and earlier selling pace; it assumes that pace continues and is not a forecast.",
        run, ["Product", "In stock", "Days of cover", "Expected to run out", "Risk"], rows)


def q_restock(text, run, focus):
    demand = run.call("get_demand_trends")
    rows = [[p["name"], p["restock"]["urgency"], p["stock"], p["restock"]["quantity"]] for p in demand["restock"]]
    if not rows:
        return answer(f"Nothing needs reordering at the current pace (as of {demand['as_of']}).", run)
    reasons = " ".join(f"{p['name']}: {p['restock']['reason']}" for p in demand["restock"][:3])
    return answer(f"{len(rows)} product(s) should be reordered. Suggested quantities cover 30 days at the current pace. {reasons}", run, ["Product", "Urgency", "In stock", "Suggested order"], rows)


def q_top(text, run, focus):
    days = days_in(text)
    performance = run.call("get_product_performance", days=days)
    rows = [[p["name"], p["units"], money(p["revenue"]), p["previous_units"], pct(p["change_units_pct"])] for p in performance["top_by_units"]]
    if not rows:
        return answer(f"No completed sales in the last {days} days.", run)
    return answer(f"Top sellers by units over the last {days} days (to {performance['ends_on']}), compared with the {days} days before.", run, ["Product", "Units", "Revenue", "Previous units", "Change"], rows)


def q_cancellation(text, run, focus):
    days = days_in(text)
    orders = run.call("get_order_analytics", days=days)
    now, before = orders["current"], orders["previous_period"]
    content = (
        f"Over the last {days} days the cancellation rate is {rate(now['cancellation_rate'])} ({now['cancelled_orders']} cancelled of {now['accepted_orders']} accepted orders); "
        f"the payment failure rate is {rate(now['payment_failure_rate'])} ({now['failed_payments']} failed payments). "
        f"The previous {days} days: cancellation {rate(before['cancellation_rate'])}, payment failures {rate(before['payment_failure_rate'])}. "
        f"Cancellation rate = {orders['definitions']['cancellation_rate']}."
    )
    rows = [["Orders placed", now["orders_placed"], before["orders_placed"]], ["Accepted (paid)", now["accepted_orders"], before["accepted_orders"]],
            ["Cancelled", now["cancelled_orders"], before["cancelled_orders"]], ["Failed payments", now["failed_payments"], before["failed_payments"]]]
    return answer(content, run, ["Measure", f"Last {days} days", f"Previous {days} days"], rows)


def q_history(text, run, focus):
    days = days_in(text)
    history = run.call("get_sales_history", days=days)
    previous = history["previous_period"]
    content = (
        f"Over the last {days} days (to {history['ends_on']}): {history['units']} units, {money(history['revenue'])} from {history['orders']} orders. "
        f"The {days} days before: {previous['units']} units, {money(previous['revenue'])}. "
        f"Change: units {pct(history['change_units_pct'])}, revenue {pct(history['change_revenue_pct'])}. {history['note']}"
    )
    rows = [[s["period"], s["units"], money(s["revenue"])] for s in history["series"]]
    return answer(content, run, [f"{history['granularity'].title()} starting", "Units", "Revenue"], rows)


def q_system(text, run, focus):
    health = run.call("get_system_health")
    content = (
        f"Database {health['database']}. Event outbox: {health['outbox_pending']} waiting"
        + (f" (oldest {health['outbox_oldest_pending_seconds']}s)" if health["outbox_oldest_pending_seconds"] is not None else "")
        + f", {health['outbox_failing']} failing to send. {health['events_last_hour']} events processed in the last hour. "
        f"{health['dead_letters_unresolved']} unresolved dead letter(s). Last event processed: {health['last_event_processed_at'] or 'never'}."
    )
    return answer(content, run)


def q_events(text, run, focus):
    hours = 24 * days_in(text, 1) if re.search(r"\bday|week", text) else 24
    stats = run.call("get_event_statistics", hours=min(hours, 24 * 14))
    rows = [[kind, n] for kind, n in list(stats["by_type"].items())[:15]]
    return answer(f"{stats['events_processed']} events processed in the last {stats['period_hours']} hours; {stats['payment_failures']} payment failure(s); {stats['dead_letters_unresolved']} unresolved dead letter(s).", run, ["Event", "Count"], rows)


# Order matters: the first rule that matches wins.
RULES = [
    (re.compile(r"operational issues|need(?:s)? (?:my |our )?attention|what(?:'s| is) wrong|any (?:issues|problems)|anything (?:wrong|urgent)|status report|health check|priorit"), q_issues),
    (re.compile(r"\bwhy\b.*(?:inventory|stock)|(?:inventory|stock).*(?:decreas|drop|fall|fell|gone down|reduc|declin|lower)"), q_why_inventory),
    (re.compile(r"unusual|anomal|abnormal|strange|\bodd\b"), q_unusual),
    (re.compile(r"sudden|spike|surge|jump"), q_spikes),
    (re.compile(r"restock|re-?order|replenish"), q_restock),
    (re.compile(r"run(?:ning)? out|stock-?outs?|sell out|selling out"), q_stockout),
    (re.compile(r"declin|falling|decreas|dropping|drop in|slowing|going down|losing"), q_decline),
    (re.compile(r"top[- ]?sell|best[- ]?sell|most sold|top products|selling the most|best[- ]perform|top[- ]perform"), q_top),
    (re.compile(r"cancel|payment.*fail|failed payment"), q_cancellation),
    (re.compile(r"system health|worker|queue|outbox|dead.?letter|pipeline|broker|database"), q_system),
    (re.compile(r"how many events|events? (?:processed|count|statistic)|event statistics"), q_events),
    (re.compile(r"(?:last|past)\s+\d+\s+(?:days?|weeks?|months?)|demand.*chang|chang.*demand|sales.*(?:chang|trend|history)|how has|this month|last month|over time|sales trend"), q_history),
]


# A command to DO something ("cancel order 1", "please set the stock to 500", "can you restock X"), as opposed to a question.
ACTION_REQUEST = re.compile(
    r"^\W*(?:(?:please|kindly)\s+|(?:can|could|would|will) you (?:please )?)?"
    r"(?:set|change|update|edit|delete|remove|cancel|refund|restock|re-?order|add|create|ship|mark|resolve|close|send|email|notify|disable|enable|reset|adjust|increase|decrease|fix|approve)\b"
)
REFUSAL = (
    "I can only read data, so I can't make that change. A person with access can do it in the console: Orders for order status, "
    "Inventory for stock, Alerts to resolve alerts. I can tell you what the data says first, for example what is selling, what is running low, or why stock changed."
)


def route(text: str):
    lowered = text.lower()
    for pattern, handler in RULES:
        if pattern.search(lowered):
            return handler
    return None


# ---- language-model fallback ------------------------------------------------------------

def llm_answer(user, conversation: Conversation, text: str, run: Run) -> str | None:
    """Open-ended questions: the model may call the read-only tools and must report what they return."""
    previous = list(conversation.messages.order_by("-id")[:10])[::-1]
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages += [{"role": m.role, "content": m.content} for m in previous if m.content]
    messages.append({"role": "user", "content": text})

    for _ in range(MAX_TOOL_ROUNDS):
        try:
            response = ollama.chat(messages, tools=ops_tools.TOOLS)
        except ollama.OllamaUnavailable:
            return None
        reply = response.get("message", {})
        calls = reply.get("tool_calls") or []
        if not calls:
            return (reply.get("content") or "").strip() or None
        messages.append(reply)
        for call in calls:
            function = call.get("function", {})
            name, args = function.get("name"), function.get("arguments") or {}
            try:
                result = run.call(name, **(args if isinstance(args, dict) else {}))
            except ops_tools.NotAllowed:
                result = {"error": "Not allowed"}
            messages.append({"role": "tool", "content": json.dumps(result, default=str), "tool_call_id": call.get("id", name)})
    return None


# ---- entry point -----------------------------------------------------------------------------

def handle_question(conversation: Conversation, text: str) -> Message:
    """Answer a staff question and save both messages. The conversation's owner must be staff."""
    if conversation.messages.count() >= MAX_MESSAGES:
        raise ValueError("This conversation is full. Please start a new one.")

    user = conversation.user
    run = Run(user)
    focus = (conversation.requirements or {}).get("focus_product_id")
    handler = route(text)
    if ACTION_REQUEST.match(text.lower()):
        handler = lambda *_: answer(REFUSAL, run)  # noqa: E731  (nothing to look up: say what the assistant can and cannot do)
    # A follow-up about the product just discussed ("why is it lower?") has no stock keyword to match.
    if handler is None and focus and re.search(r"\b(?:why|explain|what happened)\b", text.lower()) and re.search(r"\b(?:it|that|this|its)\b", text.lower()):
        handler = q_why_inventory

    if handler is not None:
        outcome = handler(text.lower(), run, focus)
    else:
        reply = llm_answer(user, conversation, text, run)
        outcome = answer(reply or LLM_UNAVAILABLE, run)

    focus_id = outcome["payload"].pop("focus_product_id", None)
    with transaction.atomic():
        if focus_id:
            conversation.requirements = {**(conversation.requirements or {}), "focus_product_id": focus_id}
        if not conversation.title:
            conversation.title = text.strip()[:60]
        conversation.save()
        Message.objects.create(conversation=conversation, role=Message.Role.USER, content=text.strip())
        return Message.objects.create(conversation=conversation, role=Message.Role.ASSISTANT, content=outcome["content"], payload=outcome["payload"])
