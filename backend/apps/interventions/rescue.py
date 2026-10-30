"""The customer rescue engine: context -> decision -> message -> audit row.

Ported from the FastAPI version with one deliberate change: the old rules could
promise "10% off" and "your cart is reserved for 2 hours", but Intellicart has no
discount or reservation feature. Those actions are gone; every action here is
something the platform really does (the cart is saved, stock is checked,
alternatives exist).
"""
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, F, Max, Q
from django.utils import timezone

from apps.cart.models import Cart
from apps.customer_intelligence.intent import compute_and_record_intent
from apps.events.models import Event
from apps.interventions.messages import craft_message
from apps.interventions.models import Intervention
from apps.orders.models import OrderItem

MIN_CART_VALUE = Decimal("10")

# Back-in-stock: look back this far for interest, and notify at most this many
# customers per restock so one popular product cannot flood the database.
BACK_IN_STOCK_INTEREST_DAYS = 14
BACK_IN_STOCK_MAX_NOTIFIED = 50


@dataclass
class RescueContext:
    cart_value: Decimal
    item_names: list[str]
    stock_ok: bool
    low_stock_item: str
    view_count: int
    checkout_started: bool
    prior_abandonment_count: int
    intent_tier: str


def _identity(user_id, session_key) -> Q:
    condition = Q(pk__in=[])
    if user_id:
        condition |= Q(user_id=user_id)
    if session_key:
        condition |= Q(session_key=session_key)
    return condition


def build_context(cart: Cart, event) -> RescueContext | None:
    items = list(cart.items.select_related("product"))
    if cart.status != Cart.Status.ACTIVE or not items:
        return None  # emptied or checked out between the trigger and now

    cart_value = sum((i.product.price * i.quantity for i in items), Decimal("0"))
    low = [i.product for i in items if i.product.stock <= i.product.low_stock_threshold]

    identity = _identity(event.user_id, event.session_key)
    events = Event.objects.filter(identity)
    intent = compute_and_record_intent(event.user_id, event.session_key)

    return RescueContext(
        cart_value=cart_value,
        item_names=[i.product.name for i in items][:3],
        stock_ok=not low,
        low_stock_item=low[0].name if low else "",
        view_count=events.filter(event_type="PRODUCT_VIEWED").count(),
        checkout_started=events.filter(event_type="CHECKOUT_STARTED").exists(),
        prior_abandonment_count=events.filter(event_type="CART_ABANDONED").exclude(event_id=event.event_id).count(),
        intent_tier=intent.tier,
    )


def decide_action(context: RescueContext) -> tuple[str, str]:
    """Ordered rule table, first match wins. Returns (action, rule) so every
    decision names the exact rule that fired."""
    if context.cart_value < MIN_CART_VALUE:
        return Intervention.Action.NO_ACTION, "cart_too_small"
    if context.checkout_started and not context.stock_ok:
        return Intervention.Action.STOCK_ALTERNATIVE, "low_stock_at_checkout"
    if context.intent_tier == "HIGH" and context.checkout_started:
        # A high-intent customer who abandons at checkout gets priority even on a
        # first abandonment: waiting for a second one would be too slow.
        return Intervention.Action.CHECKOUT_REMINDER, "high_intent_checkout_abandon"
    if context.checkout_started and context.prior_abandonment_count >= 1:
        return Intervention.Action.CHECKOUT_REMINDER, "repeat_abandon_at_checkout"
    if context.prior_abandonment_count == 0 and context.view_count >= 3:
        return Intervention.Action.REMINDER, "first_abandonment_engaged"
    return Intervention.Action.REMINDER, "default_reminder"


def handle_cart_abandoned(event) -> Intervention | None:
    """Event handler: build context, decide, write one audit row (action or no-op)."""
    cart = Cart.objects.filter(pk=event.payload["cart_id"]).first()
    if cart is None:
        return None
    context = build_context(cart, event)
    if context is None:
        return None

    action, rule = decide_action(context)
    facts = {"items_in_cart": context.item_names, "low_stock_item": context.low_stock_item}
    message, source = ("", "template") if action == Intervention.Action.NO_ACTION else craft_message(action, facts)

    return Intervention.objects.create(
        user_id=event.user_id,
        session_key=event.session_key,
        trigger_event_type="CART_ABANDONED",
        trigger_event_id=str(event.event_id),
        cart_value=context.cart_value,
        action=action,
        rule=rule,
        signals={
            "cart_value": str(context.cart_value),
            "stock_ok": context.stock_ok,
            "view_count": context.view_count,
            "checkout_started": context.checkout_started,
            "prior_abandonment_count": context.prior_abandonment_count,
            "intent_tier": context.intent_tier,
        },
        message=message,
        message_source=source,
        status=Intervention.Status.LOGGED if action == Intervention.Action.NO_ACTION else Intervention.Status.SENT,
    )


def handle_stock_restocked(event) -> list[Intervention]:
    """A sold-out product is back: tell customers who recently showed interest in it."""
    from apps.products.models import Product

    product_id = event.payload["product_id"]
    product = Product.objects.filter(pk=product_id, status=Product.Status.ACTIVE).first()
    if product is None:
        return []

    since = timezone.now() - timedelta(days=BACK_IN_STOCK_INTEREST_DAYS)
    interested = (
        Event.objects.filter(event_type="PRODUCT_VIEWED", entity_id=product_id, occurred_at__gte=since)
        .exclude(user_id__isnull=True, session_key="")
        .values("user_id", "session_key")
        .annotate(last=Max("occurred_at"))
        .order_by("-last")[:BACK_IN_STOCK_MAX_NOTIFIED]
    )

    created = []
    for row in interested:
        already = Intervention.objects.filter(
            _identity(row["user_id"], row["session_key"]),
            action=Intervention.Action.BACK_IN_STOCK_ALERT,
            signals__product_id=product_id,
            outcome="",
        ).exists()
        if already:
            continue
        created.append(
            Intervention.objects.create(
                user_id=row["user_id"],
                session_key=row["session_key"],
                trigger_event_type="STOCK_RESTOCKED",
                trigger_event_id=str(event.event_id),
                action=Intervention.Action.BACK_IN_STOCK_ALERT,
                rule="viewed_while_interested",
                signals={"product_id": product_id, "product_name": product.name},
                message=f"Good news - {product.name} is back in stock!",
                status=Intervention.Status.SENT,
            )
        )
    return created


def record_recovery(event) -> int:
    """An order completed: close the loop on interventions that led to it.
    Cart reminders count as recovered by any completed order; a back-in-stock
    alert counts only if that product was in the order. Returns how many closed."""
    open_interventions = Intervention.objects.filter(
        _identity(event.user_id, event.session_key), status=Intervention.Status.SENT, outcome=""
    )
    bought = set(OrderItem.objects.filter(order_id=event.payload["order_id"]).values_list("product_id", flat=True))

    closed = 0
    for intervention in open_interventions:
        if intervention.action == Intervention.Action.BACK_IN_STOCK_ALERT and intervention.signals.get("product_id") not in bought:
            continue
        intervention.outcome = "RECOVERED"
        intervention.outcome_at = timezone.now()
        intervention.save(update_fields=["outcome", "outcome_at"])
        closed += 1
    return closed
