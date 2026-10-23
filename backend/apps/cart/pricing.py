"""Tax and shipping rules, shared by the cart view and checkout.

Amounts are rounded to 2 decimals (half up) - the FastAPI version did not round.
"""
from decimal import ROUND_HALF_UP, Decimal

TAX_RATE = Decimal("0.18")
SHIPPING_FEE = Decimal("49")
FREE_SHIPPING_THRESHOLD = Decimal("999")
CENT = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def calculate_totals(subtotal: Decimal) -> dict:
    subtotal = money(subtotal)
    tax = money(subtotal * TAX_RATE)
    shipping = Decimal("0") if subtotal == 0 or subtotal >= FREE_SHIPPING_THRESHOLD else SHIPPING_FEE
    shipping = money(shipping)
    return {"subtotal": subtotal, "tax": tax, "shipping": shipping, "total": subtotal + tax + shipping}
