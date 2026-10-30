from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.cart.models import Cart
from apps.events.services import emit


def scan_abandoned_carts() -> int:
    """Find carts that have gone idle and emit CART_ABANDONED for each (once).

    Abandonment is the ABSENCE of activity, so it has to be noticed on a timer. A
    cart's own updated_at is not enough (it changes on every cart edit), so idle time
    is measured from its newest item. `abandonment_flagged_at` is set by the scanner
    itself, so a slow or stopped consumer cannot make the same cart be flagged
    again on every pass. Activity after the flag makes the cart eligible again."""
    cutoff = timezone.now() - timedelta(minutes=settings.CART_ABANDONMENT_MINUTES)
    flagged = 0

    idle_carts = (
        Cart.objects.filter(status=Cart.Status.ACTIVE, items__isnull=False)
        .annotate(last_activity=Max("items__updated_at"))
        .filter(last_activity__lt=cutoff)
    )
    for cart in idle_carts:
        if cart.abandonment_flagged_at and cart.abandonment_flagged_at >= cart.last_activity:
            continue
        with transaction.atomic():
            emit(
                "CART_ABANDONED",
                user=cart.user_id,
                session_key=cart.session_key or "",
                entity_id=cart.id,
                payload={"cart_id": cart.id},
            )
            cart.abandonment_flagged_at = timezone.now()
            cart.save(update_fields=["abandonment_flagged_at"])
        flagged += 1
    return flagged
