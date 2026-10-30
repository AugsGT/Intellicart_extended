"""Purchase-intent scoring: a small rule-based score, not a trained model, because a
stated basis is more honest than an invented confidence number at this scale.
Every score is stored with the exact signal counts and weights that produced it."""
from dataclasses import dataclass

from django.db.models import Q

from apps.customer_intelligence.models import IntentScore
from apps.events.models import Event
from apps.orders.models import Order

# Weights are explicit and capped per signal so no single repeated action
# (such as refreshing a product page) can dominate the score.
VIEW_WEIGHT, VIEW_CAP = 2, 10
SEARCH_WEIGHT, SEARCH_CAP = 1, 5
CART_ADD_WEIGHT = 5
CART_REMOVE_WEIGHT, CART_REMOVE_CAP = 1, 3  # judgement call: removing items still means they are working on the cart
CHECKOUT_STARTED_BONUS = 15
RETURNING_CUSTOMER_BONUS = 10

HIGH_THRESHOLD = 40
MEDIUM_THRESHOLD = 15


@dataclass
class IntentResult:
    score: int
    tier: str
    basis: dict


def _customer_events(user_id, session_key):
    condition = Q(pk__in=[])
    if user_id:
        condition |= Q(user_id=user_id)
    if session_key:
        condition |= Q(session_key=session_key)
    return Event.objects.filter(condition)


def compute_intent(user_id=None, session_key: str = "") -> IntentResult:
    events = _customer_events(user_id, session_key)

    def count(event_type):
        return events.filter(event_type=event_type).count()

    views, searches = count("PRODUCT_VIEWED"), count("PRODUCT_SEARCHED")
    cart_adds, cart_removes = count("CART_ITEM_ADDED"), count("CART_ITEM_REMOVED")
    checkout_started = count("CHECKOUT_STARTED") > 0
    prior_orders = Order.objects.successful().filter(user_id=user_id).count() if user_id else 0

    score = (
        min(views, VIEW_CAP) * VIEW_WEIGHT
        + min(searches, SEARCH_CAP) * SEARCH_WEIGHT
        + cart_adds * CART_ADD_WEIGHT
        + min(cart_removes, CART_REMOVE_CAP) * CART_REMOVE_WEIGHT
        + (CHECKOUT_STARTED_BONUS if checkout_started else 0)
        + (RETURNING_CUSTOMER_BONUS if prior_orders > 0 else 0)
    )
    tier = "HIGH" if score >= HIGH_THRESHOLD else "MEDIUM" if score >= MEDIUM_THRESHOLD else "LOW"

    basis = {
        "view_count": views,
        "search_count": searches,
        "cart_add_count": cart_adds,
        "cart_remove_count": cart_removes,
        "checkout_started": checkout_started,
        "prior_orders": prior_orders,
        "weights": {
            "view": VIEW_WEIGHT, "view_cap": VIEW_CAP,
            "search": SEARCH_WEIGHT, "search_cap": SEARCH_CAP,
            "cart_add": CART_ADD_WEIGHT,
            "cart_remove": CART_REMOVE_WEIGHT, "cart_remove_cap": CART_REMOVE_CAP,
            "checkout_started_bonus": CHECKOUT_STARTED_BONUS,
            "returning_customer_bonus": RETURNING_CUSTOMER_BONUS,
        },
    }
    return IntentResult(score=score, tier=tier, basis=basis)


def compute_and_record_intent(user_id=None, session_key: str = "") -> IntentResult:
    result = compute_intent(user_id, session_key)
    IntentScore.objects.create(
        user_id=user_id, session_key=session_key, score=result.score, tier=result.tier, basis=result.basis
    )
    return result


def latest_scores(tiers: list[str], limit: int = 100) -> list[IntentScore]:
    """Most recent scoring run per customer, limited to the given tiers."""
    seen = set()
    chosen = []
    for row in IntentScore.objects.order_by("-id")[:500]:
        key = ("user", row.user_id) if row.user_id else ("session", row.session_key)
        if key in seen:
            continue
        seen.add(key)
        if row.tier in tiers:
            chosen.append(row)
        if len(chosen) >= limit:
            break
    return chosen
