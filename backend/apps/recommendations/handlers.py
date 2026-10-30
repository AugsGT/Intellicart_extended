"""Links purchases back to recommendations that were clicked.

When an order completes, any product in it that the same customer clicked as a
recommendation in the last 7 days produces RECOMMENDATION_PURCHASED (with the kind
that was clicked). This is attribution by click, not proof the recommendation caused the sale."""
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from apps.events.handlers import on
from apps.events.models import Event
from apps.events.services import emit
from apps.orders.models import OrderItem

ATTRIBUTION_DAYS = 7


@on("ORDER_COMPLETED")
def attribute_purchases_to_recommendations(event) -> None:
    identity = Q(pk__in=[])
    if event.user_id:
        identity |= Q(user_id=event.user_id)
    if event.session_key:
        identity |= Q(session_key=event.session_key)

    order_id = event.payload["order_id"]
    bought = set(OrderItem.objects.filter(order_id=order_id).values_list("product_id", flat=True))
    since = timezone.now() - timedelta(days=ATTRIBUTION_DAYS)
    clicks = Event.objects.filter(identity, event_type="RECOMMENDATION_CLICKED", occurred_at__gte=since).order_by("-occurred_at")

    done = set()
    for click in clicks:
        product_id = click.payload.get("product_id")
        if product_id in bought and product_id not in done:
            done.add(product_id)
            emit(
                "RECOMMENDATION_PURCHASED",
                user=event.user_id,
                session_key=event.session_key,
                entity_id=product_id,
                payload={"kind": click.payload.get("kind", ""), "product_id": product_id, "order_id": order_id},
            )
