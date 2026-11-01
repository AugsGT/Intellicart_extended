"""One conversational turn of the shopping advisor.

Rule-based steps handle what the advisor must get right every time (understanding
requirements, searching, ranking, comparing, confirmed cart actions). The language
model is only a fallback for open-ended questions (see llm.py).

Safety rules enforced here, in code, not in a prompt:
* The advisor never places an order or takes a payment: no code path does.
* Adding to the cart happens only after the customer confirms, by tapping Confirm or
  replying "yes", and is carried out by the normal cart service for THEIR cart.
* All reads and writes are scoped to the logged-in customer's own conversation.
"""
import re
import uuid
from datetime import datetime, timedelta

from django.db import transaction
from django.utils import timezone

from apps.ai_assistant import advisor, llm, requirements
from apps.ai_assistant.models import Conversation, Message
from apps.cart import services as cart_services
from apps.events.services import emit
from apps.products.models import Product

MAX_MESSAGES = 200
PENDING_MINUTES = 10
MAX_QUANTITY = 5

ORDINALS = {"first": 0, "1st": 0, "second": 1, "2nd": 1, "third": 2, "3rd": 2, "fourth": 3, "4th": 3, "last": -1}

YES = re.compile(r"^\W*(?:yes|yep|yeah|yup|confirm|confirmed|ok|okay|sure|go ahead|do it|please do|add it|proceed)\b")
NO = re.compile(r"^\W*(?:no|nope|nah|cancel|don'?t|do not|never ?mind|stop|not now)\b")
# Only clear references to something already shown ("buy the second one"), so that
# "I want to buy a laptop" is understood as a search, not as a cart command.
ADD_TO_CART = re.compile(
    r"\b(?:add|put)\b.*\b(?:cart|basket)\b"
    r"|\b(?:buy|purchase|order)\s+(?:it\b|this\b|that\b|the\s+(?:first|second|third|fourth|last)\b|option\b|number\b)"
)
COMPARE = re.compile(r"\bcompar\w*|\bdifferences?\b|\bversus\b|\bvs\.?\b|\bside by side\b")
# A request for facts, not a new requirement: "I need 2 years warranty" is a requirement,
# "what warranty does it have?" is a question.
DETAILS = re.compile(
    r"\b(?:tell me more|more (?:details|info|information)|details?|specs?|specifications?)\b"
    r"|\b(?:what|how long|which|does|do)\b[^.?]*\bwarrant\w*"
)
BARE_AMOUNT = re.compile(r"^\D*(\d[\d,]*(?:\.\d+)?)\s*(k|lakhs?|thousand)?\D*$")


# ---- helpers ---------------------------------------------------------------

def _shown(conversation: Conversation) -> list[Product]:
    products = Product.objects.select_related("category").prefetch_related("attributes__definition").in_bulk(conversation.last_results)
    return [products[pid] for pid in conversation.last_results if pid in products]


def _find_references(conversation: Conversation, text: str) -> list[Product]:
    """Products from the last results that the text points at (by position or name)."""
    shown = _shown(conversation)
    if not shown:
        return []
    chosen: list[Product] = []

    def add(product):
        if product not in chosen:
            chosen.append(product)

    for word, index in ORDINALS.items():
        if re.search(rf"\b{re.escape(word)}\b", text):
            try:
                add(shown[index])
            except IndexError:
                pass
    for match in re.finditer(r"(?:option|number|no\.?|#|result)\s*(\d)", text):
        index = int(match.group(1)) - 1
        if 0 <= index < len(shown):
            add(shown[index])
    for product in shown:
        name = product.name.lower()
        short = " ".join(name.split()[:2])
        if name in text or (len(short) > 5 and short in text):
            add(product)
    return chosen


def _group_reference(conversation: Conversation, text: str) -> list[Product]:
    shown = _shown(conversation)
    if re.search(r"\b(?:best|top|first)\s+(?:two|2)\b|\bboth\b", text):
        return shown[:2]
    if re.search(r"\b(?:best|top|first)\s+(?:three|3)\b", text):
        return shown[:3]
    if re.search(r"\b(?:all|them|these|everything)\b", text):
        return shown[:4]
    return []


def _focus(conversation: Conversation) -> Product | None:
    focus_id = (conversation.requirements or {}).get("focus_product_id")
    if focus_id:
        return Product.objects.select_related("category").filter(pk=focus_id, status=Product.Status.ACTIVE).first()
    return None


def _reply(content: str, **payload) -> dict:
    return {"content": content, **{k: v for k, v in payload.items() if v}}


def _ask_which(shown: list[Product], verb: str) -> dict:
    options = "; ".join(f"{i + 1}. {p.name}" for i, p in enumerate(shown))
    return _reply(f"Which one should I {verb}? {options}")


# ---- turn handlers -----------------------------------------------------------

def _pending_is_live(conversation: Conversation) -> bool:
    pending = conversation.pending_action
    if not pending:
        return False
    return timezone.now() - datetime.fromisoformat(pending["created_at"]) < timedelta(minutes=PENDING_MINUTES)


def _propose_add_to_cart(conversation: Conversation, product: Product, quantity: int) -> dict:
    if product.stock <= 0:
        return _reply(f"Sorry, {product.name} is out of stock right now, so I can't add it to your cart.", cards=[advisor.product_card(product)])
    quantity = min(quantity, product.stock, MAX_QUANTITY)
    conversation.pending_action = {
        "id": uuid.uuid4().hex,
        "type": "add_to_cart",
        "product_id": product.id,
        "quantity": quantity,
        "created_at": timezone.now().isoformat(),
        "summary": f"Add {quantity} x {product.name} ({advisor.money(product.price * quantity)}) to your cart",
    }
    return _reply(
        f"I can add {quantity} x {product.name} ({advisor.money(product.price * quantity)}) to your cart. Shall I go ahead? "
        "Nothing is added until you confirm, and I never place orders or take payment.",
        cards=[advisor.product_card(product)],
        pending_action=conversation.pending_action,
    )


def execute_pending(conversation: Conversation, approve: bool) -> dict:
    """The customer's answer to a pending action. Only here does the cart change."""
    pending = conversation.pending_action
    if not pending or not _pending_is_live(conversation):
        conversation.pending_action = None
        return _reply("There is nothing waiting for your confirmation (it may have expired).")

    conversation.pending_action = None
    if not approve:
        return _reply("Okay, I have not added anything to your cart.")

    product = Product.objects.filter(pk=pending["product_id"]).first()
    cart = cart_services.get_active_cart(user=conversation.user)
    try:
        cart_services.add_item(cart, pending["product_id"], pending["quantity"])
    except cart_services.CartError as error:
        return _reply(f"I could not add that to your cart: {error.message}")

    cart_view = cart_services.cart_view(cart)
    name = product.name if product else "The item"
    return _reply(
        f"Done: {name} is in your cart. Your cart total is now {advisor.money(cart_view['total'])}. "
        "You can review your cart and check out whenever you are ready; I can't place the order for you.",
        cart={"item_count": sum(i["quantity"] for i in cart_view["items"]), "total": str(cart_view["total"]), "link": "/cart"},
    )


def _handle_add_to_cart(conversation: Conversation, text: str) -> dict:
    shown = _shown(conversation)
    refs = _find_references(conversation, text)
    if len(refs) == 1:
        target = refs[0]
    elif len(refs) > 1:
        return _ask_which(refs, "add to your cart")
    elif re.search(r"\b(?:it|this|that)\b", text) and _focus(conversation):
        target = _focus(conversation)
    elif len(shown) == 1:
        target = shown[0]
    elif shown:
        return _ask_which(shown, "add to your cart")
    else:
        return _reply("I have not shown you any products yet. Tell me what you are looking for and I will find some options.")

    quantity = 1
    match = re.search(r"\b(?:add|put)\s+(\d)\b(?!\s*(?:st|nd|rd|th))", text)
    if match:
        quantity = max(1, int(match.group(1)))
    return _propose_add_to_cart(conversation, target, quantity)


def _handle_compare(conversation: Conversation, text: str) -> dict:
    shown = _shown(conversation)
    if not shown:
        return _reply("I have not shown you any products to compare yet. Tell me what you are looking for first.")

    refs = _group_reference(conversation, text) or _find_references(conversation, text)
    if len(refs) < 2:
        if len(shown) == 1:
            return _reply("There is only one product on screen, so there is nothing to compare it with yet.")
        return _ask_which(shown, "compare (name at least two, for example 'compare the first and second')")

    comparison = advisor.compare(refs[:4])
    leaders = "; ".join(f"{l['label']}: {', '.join(l['products'])}" for l in comparison["leaders"])
    names = " and ".join(p["name"] for p in comparison["products"])
    return _reply(
        f"Here is a side-by-side comparison of {names}. Leaders by attribute: {leaders}. "
        "I do not pick an overall winner; it depends on which of these matters most to you.",
        comparison=comparison,
    )


def _handle_details(conversation: Conversation, text: str) -> dict | None:
    refs = _find_references(conversation, text)
    shown = _shown(conversation)
    if not refs and re.search(r"\bwarrant\w*\b", text) and shown:
        refs = shown
    elif not refs:
        focus = _focus(conversation)
        refs = [focus] if focus else []
    if not refs:
        return None

    cards = [advisor.product_card(p) for p in refs[:4]]
    lines = []
    for product in refs[:4]:
        specs = ", ".join(f"{s['label']}: {s['value']}" for s in advisor.specifications(product)) or "no specifications listed"
        lines.append(f"{product.name} - {specs}. {advisor.warranty_information(product)['statement']}.")
    conversation.requirements = {**conversation.requirements, "focus_product_id": refs[0].id}
    return _reply("\n".join(lines), cards=cards)


def _ask_category(state: dict) -> dict:
    names = list(
        Product.objects.filter(status=Product.Status.ACTIVE).values_list("category__name", flat=True).distinct().order_by("category__name")
    )
    state["awaiting"] = "category"
    return _reply("What kind of product are you looking for? I can help with: " + ", ".join(names) + ".")


def _recommend(conversation: Conversation, state: dict, rerank: bool) -> dict:
    result = advisor.recommend(state)
    conversation.last_results = result["ids"]
    state["focus_product_id"] = None

    summary = requirements.describe(state)
    if not result["cards"]:
        left = result["left_out"]
        reasons = [f"{n} {why}" for n, why in ((left["over_budget"], "over your budget"), (left["out_of_stock"], "out of stock"),
                                                (left["below_requested_specs"], "below the specs you asked for"),
                                                (left["under_budget"], "under your minimum budget")) if n]
        detail = f" ({', '.join(reasons)})" if reasons else ""
        return _reply(f"I could not find any {summary} that match everything{detail}. Would you like to raise the budget or relax a requirement?")

    intro = "Re-ranked with your updated priorities. " if rerank else ""
    lines = [f"{intro}Here are {len(result['cards'])} option(s) for {summary}, chosen from {result['considered']} that fit."]
    labels = requirements.priority_labels(state)
    if labels:
        lines.append("They are ordered by how well each meets your priorities, in this order: " + ", ".join(labels) + " (ties go to the lower price).")
    left = result["left_out"]
    skipped = [f"{n} {why}" for n, why in ((left["over_budget"], "over your budget"), (left["out_of_stock"], "out of stock"),
                                           (left["below_requested_specs"], "below your requested specs")) if n]
    if skipped:
        lines.append("Left out: " + ", ".join(skipped) + ".")
    if state.get("unverifiable"):
        lines.append("I can't verify from the catalogue: " + "; ".join(state["unverifiable"]) + ".")
    lines.append("Ask me to compare any of them, show details, or add one to your cart.")
    return _reply(" ".join(lines), cards=result["cards"])


def _handle_requirements(conversation: Conversation, text: str, state: dict, awaiting: str | None) -> dict | None:
    update = requirements.extract(text)

    # A bare "60000" is a good answer to "what is your budget?".
    if awaiting == "budget" and update.max_budget is None and not update.clear_budget:
        bare = BARE_AMOUNT.match(text.lower())
        if bare:
            update.max_budget = requirements._amount(bare.group(1), bare.group(2))
    if awaiting == "budget" and re.search(r"\b(?:no limit|any|none|no budget|doesn'?t matter|flexible)\b", text.lower()):
        update.clear_budget = True

    if update.reset:
        conversation.requirements = requirements.empty_requirements()
        conversation.last_results = []
        conversation.pending_action = None
        return _reply("Okay, starting over. What are you looking for?")

    had_results = bool(conversation.last_results)
    new_state = requirements.merge(state, update)
    if awaiting in ("budget", "usage") and awaiting not in new_state["asked"]:
        new_state["asked"].append(awaiting)   # they have answered, in whatever words
    new_state.pop("awaiting", None)
    answered_only = awaiting in ("budget", "usage")

    if update.is_empty() and not answered_only:
        return None   # nothing about requirements in this message

    if new_state["category_id"] is None:
        conversation.requirements = new_state
        return _ask_category(conversation.requirements)

    if new_state["max_budget"] is None and new_state["min_budget"] is None and "budget" not in new_state["asked"]:
        new_state["asked"].append("budget")
        new_state["awaiting"] = "budget"
        conversation.requirements = new_state
        return _reply(f"What is your budget for {new_state['category_name'].lower()}? You can say something like 'under 60000', or 'no limit'.")

    if not new_state["usage"] and not new_state["priorities"] and "usage" not in new_state["asked"]:
        new_state["asked"].append("usage")
        new_state["awaiting"] = "usage"
        conversation.requirements = new_state
        return _reply("What will you mainly use it for, and what matters most to you (for example battery life, warranty, durability)?")

    conversation.requirements = new_state
    rerank = had_results and bool(update.priorities or update.demoted)
    return _recommend(conversation, new_state, rerank)


# ---- public entry point -------------------------------------------------------

def handle_message(conversation: Conversation, text: str) -> Message:
    """Process the customer's message and return the saved assistant Message."""
    if conversation.messages.count() >= MAX_MESSAGES:
        raise ValueError("This conversation is full. Please start a new one.")

    lowered = text.strip().lower()
    state = dict(conversation.requirements or requirements.empty_requirements())
    awaiting = state.get("awaiting")
    outcome: dict | None = None

    if _pending_is_live(conversation) and YES.match(lowered):
        outcome = execute_pending(conversation, approve=True)
    elif conversation.pending_action and NO.match(lowered):
        outcome = execute_pending(conversation, approve=False)
    elif re.search(r"\b(?:start over|start again|reset|new search)\b", lowered):
        outcome = _handle_requirements(conversation, text, state, awaiting)
    elif ADD_TO_CART.search(lowered) and (conversation.last_results or _focus(conversation)):
        outcome = _handle_add_to_cart(conversation, lowered)
    elif COMPARE.search(lowered) and conversation.last_results:
        outcome = _handle_compare(conversation, lowered)
    elif DETAILS.search(lowered) and conversation.last_results:
        outcome = _handle_details(conversation, lowered)

    if outcome is None:
        outcome = _handle_requirements(conversation, text, state, awaiting)

    if outcome is None:
        answer = llm.answer(conversation.user, conversation, text)
        outcome = _reply(
            answer or "I can help best when I know the product type, your budget and what matters most. "
            "For example: 'a laptop for programming under 60000 with good battery life'."
        )

    with transaction.atomic():
        if not conversation.title:
            conversation.title = text.strip()[:60]
        conversation.save()
        Message.objects.create(conversation=conversation, role=Message.Role.USER, content=text.strip())
        message = Message.objects.create(
            conversation=conversation,
            role=Message.Role.ASSISTANT,
            content=outcome["content"],
            payload={k: v for k, v in outcome.items() if k != "content"},
        )
        if outcome.get("cards") and any("explanation" in c for c in outcome["cards"]):
            emit(
                "RECOMMENDATION_GENERATED",
                user=conversation.user,
                payload={"kind": "advisor", "product_ids": [c["id"] for c in outcome["cards"]]},
            )
    return message


def respond_to_pending(conversation: Conversation, approve: bool) -> Message:
    """The customer tapped Confirm or Cancel on a pending action."""
    outcome = execute_pending(conversation, approve)
    with transaction.atomic():
        conversation.save()
        return Message.objects.create(
            conversation=conversation,
            role=Message.Role.ASSISTANT,
            content=outcome["content"],
            payload={k: v for k, v in outcome.items() if k != "content"},
        )
