"""Generates SAMPLE order history so the demand dashboards have something to show.

Run after seed_demo:   python manage.py seed_demo && python manage.py seed_order_history

The history is invented (random but reproducible with --seed). Each product follows a
deliberate pattern so every kind of signal can be seen: one rising, one falling, one
with a sudden spike in the last 3 days, one about to run out, one already low.
Orders, stock movements and browsing events are written with past dates; no live
events are published. The users it creates cannot log in.
"""
import math
import random
import uuid
from collections import defaultdict
from datetime import datetime, time, timedelta, timezone as dt_timezone

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from apps.accounts.models import User
from apps.cart.pricing import calculate_totals
from apps.events.models import Event
from apps.inventory.models import StockMovement
from apps.orders.models import Order, OrderItem
from apps.products.models import Product

SHOPPER_COUNT = 12
NOTE = "Sample order history"   # marks the stock movements this command wrote, so --replace can remove them
ADDRESS = {
    "full_name": "Sample Shopper", "address_line1": "1 Sample Street", "city": "Bengaluru",
    "state": "Karnataka", "postal_code": "560001", "phone": "9999999999",
}
SEARCH_TERMS = ["laptop", "earbuds", "phone", "chair", "gaming", "warranty", "noise cancelling", "budget laptop"]

# product name -> (pattern, final stock). Patterns are functions of (day index, number of days) -> expected units per day.
def steady(rate):
    return lambda t, n: rate


def rising(t, n):  # flat, then climbing over the last 35 days
    ramp = max(0.0, (t - (n - 35)) / 34)
    return 0.4 + 3.4 * ramp


def falling(t, n):  # strong, then fading over the last 35 days
    ramp = max(0.0, (t - (n - 35)) / 34)
    return 1.8 - 1.5 * ramp


def spiking(t, n):  # steady, then a burst in the last 3 days
    return 7.0 if t >= n - 3 else 1.5


PATTERNS = {
    "Nimbus 14 Developer Laptop": (rising, 40),
    "Forge 15 Gaming Laptop": (falling, 30),
    "Pulse ANC Earbuds": (spiking, 60),
    "Pulse Go Earbuds": (steady(3.0), 12),     # about 4 days of stock at this pace
    "Basic Task Chair": (steady(0.2), 5),      # already at its low-stock threshold
    "Orbit Lite Phone": (steady(2.0), 120),
    "Orbit X Phone": (steady(1.2), 70),
    "Slate Air 13 Laptop": (steady(0.9), 50),
    "ErgoMesh Office Chair": (steady(0.6), 40),
}


def poisson(rng: random.Random, expected: float) -> int:
    limit, k, p = math.exp(-expected), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


class Command(BaseCommand):
    help = "Generate sample order history (invented data) for the demand dashboards."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=90)
        parser.add_argument("--seed", type=int, default=42, help="random seed, so the same data can be regenerated")
        parser.add_argument("--replace", action="store_true", help="remove previously generated sample history first")

    @transaction.atomic
    def handle(self, *args, **options):
        days, rng = options["days"], random.Random(options["seed"])
        if days < 40:
            raise CommandError("--days must be at least 40 so the 7-day and 28-day windows have history")

        shoppers = [
            User.objects.get_or_create(
                email=f"shopper{n:02d}@example.test", defaults={"username": f"sample_shopper_{n:02d}", "role": User.Role.CUSTOMER}
            )[0]
            for n in range(1, SHOPPER_COUNT + 1)
        ]
        for shopper in shoppers:
            if not shopper.has_usable_password():
                continue
            shopper.set_unusable_password()
            shopper.save(update_fields=["password"])
        if Order.objects.filter(user__in=shoppers).exists():
            if not options["replace"]:
                self.stdout.write("Sample order history already exists; use --replace to regenerate it.")
                return
            self._remove_sample_history(shoppers)

        products = list(Product.objects.filter(status=Product.Status.ACTIVE).select_related("category"))
        if not products:
            raise CommandError("No products found. Run `python manage.py seed_demo` first.")

        today = timezone.now().date()
        first_day = today - timedelta(days=days)          # day index 0 ... days-1 (yesterday)

        # 1. How many of each product sell on each day.
        plan: dict[int, dict[int, int]] = defaultdict(dict)   # day index -> product id -> units
        sold = defaultdict(int)
        for product in products:
            pattern, _ = PATTERNS.get(product.name, (steady(0.5), 50))
            for t in range(days):
                units = poisson(rng, pattern(t, days))
                if units:
                    plan[t][product.id] = units
                    sold[product.id] += units

        # 2. Stock history: start high enough that the pattern ends at its target stock.
        final_stock = {p.id: PATTERNS.get(p.name, (None, 50))[1] for p in products}
        running = {p.id: final_stock[p.id] + sold[p.id] for p in products}
        # Stock before the sample history = what the sample sales need; the movement adds only what the ledger lacks.
        movements = [
            StockMovement(product=p, change=running[p.id] - p.stock, reason="INITIAL", resulting_stock=running[p.id], note=NOTE)
            for p in products if running[p.id] != p.stock
        ]
        movement_dates = [datetime.combine(first_day, time(8, 0), tzinfo=dt_timezone.utc)] * len(movements)

        # 3. Orders: units sold on a day are grouped into one order per shopper per day.
        by_id = {p.id: p for p in products}
        orders, order_lines, order_times = [], [], []
        for t in range(days):
            day = first_day + timedelta(days=t)
            lines_by_shopper: dict[int, dict[int, int]] = defaultdict(dict)
            for product_id, units in plan.get(t, {}).items():
                for _ in range(units):
                    shopper = rng.choice(shoppers)
                    lines_by_shopper[shopper.id][product_id] = lines_by_shopper[shopper.id].get(product_id, 0) + 1
            for shopper_id, lines in lines_by_shopper.items():
                when = datetime.combine(day, time(rng.randint(9, 21), rng.randint(0, 59)), tzinfo=dt_timezone.utc)
                subtotal = sum(by_id[pid].price * qty for pid, qty in lines.items())
                totals = calculate_totals(subtotal)
                old_enough = (today - day).days > 7
                orders.append(Order(
                    user_id=shopper_id, status=Order.Status.DELIVERED if old_enough else Order.Status.CONFIRMED,
                    payment_status=Order.PaymentStatus.PAID, payment_method="cod", payment_reference="sample", **ADDRESS, **totals,
                ))
                order_lines.append(lines)
                order_times.append(when)

        # A few cancelled and failed orders, so the dashboards can show they are NOT counted.
        extras = max(4, len(orders) // 25)
        for index in range(extras):
            cancelled = index % 2 == 0
            product = rng.choice(products)
            when = datetime.combine(first_day + timedelta(days=rng.randint(5, days - 2)), time(rng.randint(9, 21), 0), tzinfo=dt_timezone.utc)
            totals = calculate_totals(product.price)
            orders.append(Order(
                user_id=rng.choice(shoppers).id,
                status=Order.Status.CANCELLED if cancelled else Order.Status.FAILED,
                payment_status=Order.PaymentStatus.REFUNDED if cancelled else Order.PaymentStatus.FAILED,
                payment_method="card", payment_reference="sample", **ADDRESS, **totals,
            ))
            order_lines.append({product.id: 3})
            order_times.append(when)

        # The demo catalogue was created today, but this history starts earlier: move the catalogue's own
        # starting stock (and creation date) back to the start of the history so the ledger reads in order.
        start = datetime.combine(first_day, time(8, 0), tzinfo=dt_timezone.utc)
        StockMovement.objects.filter(product__in=products, reason="INITIAL", note="Sample data").update(created_at=start)
        Product.objects.filter(pk__in=[p.pk for p in products]).update(created_at=start)

        Order.objects.bulk_create(orders)
        for order, when in zip(orders, order_times):
            order.created_at = order.updated_at = when
        Order.objects.bulk_update(orders, ["created_at", "updated_at"])
        OrderItem.objects.bulk_create(
            [
                OrderItem(order=order, product=by_id[pid], name=by_id[pid].name, unit_price=by_id[pid].price, quantity=qty)
                for order, lines in zip(orders, order_lines) for pid, qty in lines.items()
            ]
        )

        # 4. Ledger rows, in time order, so every resulting_stock is consistent.
        chronological = sorted(zip(orders, order_lines, order_times), key=lambda item: item[2])
        for order, lines, when in chronological:
            if order.status == Order.Status.FAILED:
                continue
            for pid, qty in lines.items():
                running[pid] -= qty
                movements.append(StockMovement(product=by_id[pid], change=-qty, reason="ORDER", resulting_stock=running[pid], reference=f"order:{order.id}", note=NOTE))
                movement_dates.append(when)
                if order.status == Order.Status.CANCELLED:
                    running[pid] += qty
                    movements.append(StockMovement(product=by_id[pid], change=qty, reason="CANCELLATION", resulting_stock=running[pid], reference=f"order:{order.id}", note=NOTE))
                    movement_dates.append(when + timedelta(hours=1))
        StockMovement.objects.bulk_create(movements)
        for movement, when in zip(movements, movement_dates):
            movement.created_at = when
        StockMovement.objects.bulk_update(movements, ["created_at"])

        for product in products:
            product.stock = running[product.id]
        Product.objects.bulk_update(products, ["stock"])

        # 5. Browsing events (for the Analytics page): many views per sale, some cart adds and searches.
        events = []

        def event(event_type, when, entity=None, payload=None, user=None):
            events.append(Event(event_id=uuid.uuid4(), event_type=event_type, user_id=user, session_key=f"sample-{rng.randint(1, 400)}" if not user else "",
                                entity_id=entity, payload=payload or {}, occurred_at=when))

        for t, per_product in plan.items():
            day = first_day + timedelta(days=t)
            for pid, units in per_product.items():
                for _ in range(units * 6):
                    event("PRODUCT_VIEWED", datetime.combine(day, time(rng.randint(8, 22), rng.randint(0, 59)), tzinfo=dt_timezone.utc), pid, {"product_id": pid},
                          user=rng.choice(shoppers).id if rng.random() < 0.6 else None)   # some viewers are logged in, some are anonymous
                for _ in range(int(units * 1.6) + 1):
                    event("CART_ITEM_ADDED", datetime.combine(day, time(rng.randint(8, 22), rng.randint(0, 59)), tzinfo=dt_timezone.utc), pid, {"product_id": pid, "quantity": 1})
        for _ in range(days * 3):
            when = datetime.combine(first_day + timedelta(days=rng.randrange(days)), time(rng.randint(8, 22), 0), tzinfo=dt_timezone.utc)
            event("PRODUCT_SEARCHED", when, payload={"query": rng.choice(SEARCH_TERMS)})
        for order, when in zip(orders, order_times):
            if order.status in (Order.Status.CONFIRMED, Order.Status.DELIVERED):
                event("CHECKOUT_STARTED", when - timedelta(minutes=5), user=order.user_id)
                event("ORDER_COMPLETED", when, order.id, {"order_id": order.id, "total": str(order.total)}, user=order.user_id)
        for _ in range(len(orders) // 3):   # checkouts that never completed
            event("CHECKOUT_STARTED", datetime.combine(first_day + timedelta(days=rng.randrange(days)), time(rng.randint(9, 21), 30), tzinfo=dt_timezone.utc))
        Event.objects.bulk_create(events, batch_size=1000)

        successful = Order.objects.successful().filter(user__in=shoppers).count()
        self.stdout.write(self.style.SUCCESS(
            f"Created {len(orders)} orders ({successful} successful), {len(movements)} stock movements and {len(events)} events over {days} days."
        ))

    def _remove_sample_history(self, shoppers):
        """Delete what an earlier run created, then make stock match the remaining ledger again."""
        ids = [s.id for s in shoppers]
        Order.objects.filter(user_id__in=ids).delete()                      # their items go with them
        StockMovement.objects.filter(note=NOTE).delete()
        Event.objects.filter(Q(session_key__startswith="sample-") | Q(user_id__in=ids)).delete()
        for product in Product.objects.all():
            product.stock = product.stock_movements.aggregate(total=Sum("change"))["total"] or 0
            product.save(update_fields=["stock"])
