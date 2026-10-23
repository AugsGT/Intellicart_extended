"""MOCK payment gateway - sandbox only. No real payment is processed or stored.

Every charge succeeds except card number 4000000000000002, which simulates a
decline so the failure path can be exercised. Replace this module with a real
provider (and real card handling that never stores card numbers) before taking
real money.
"""
import uuid
from dataclasses import dataclass

DECLINE_CARD_NUMBER = "4000000000000002"


@dataclass
class PaymentResult:
    success: bool
    reference: str
    reason: str = ""


def charge(amount, method: str, card_number: str = "") -> PaymentResult:
    reference = f"mock_{uuid.uuid4().hex[:16]}"
    if method == "card" and card_number.replace(" ", "") == DECLINE_CARD_NUMBER:
        return PaymentResult(False, reference, "card_declined")
    return PaymentResult(True, reference)
