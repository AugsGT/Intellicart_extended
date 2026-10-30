"""Customer-facing text for an intervention.

The message is written by Ollama from verified facts (item names, stock), then
checked: if it is empty, too long, or mentions discounts, offers, prices or
deadlines, it is thrown away and a fixed template is used instead. Intellicart has
no discount or reservation feature, so no message may promise one.
"""
import logging
import re

from django.conf import settings

from apps.ai_assistant import ollama

logger = logging.getLogger("intellicart.interventions")

TEMPLATES = {
    "REMINDER": "You left something in your cart - it is saved for when you are ready.",
    "CHECKOUT_REMINDER": "You were close to finishing your order - your cart is saved whenever you want to finish.",
    "STOCK_ALTERNATIVE": "An item in your cart is running low on stock. Here is a similar option that is available now.",
}

# Anything that sounds like an offer we cannot honour.
FORBIDDEN = re.compile(
    r"discount|coupon|promo|voucher|\boffer|\bdeal\b|\bsale\b|\bfree\b|\bsave\b|cheaper|\boff\b|reserv|expire|hurry|last chance"
    r"|limited time|[%$₹]|\bhours?\b|\bminutes?\b",
    re.IGNORECASE,
)
MAX_LENGTH = 200

GOALS = {
    "REMINDER": "gently remind the customer that the items in their cart are saved",
    "CHECKOUT_REMINDER": "remind the customer they were close to finishing checkout and that their cart is saved",
    "STOCK_ALTERNATIVE": "tell the customer an item in their cart is running low on stock and a similar item is available",
}


def is_acceptable(text: str) -> bool:
    text = text.strip()
    return bool(text) and len(text) <= MAX_LENGTH and not FORBIDDEN.search(text) and "\n" not in text


def craft_message(action: str, facts: dict) -> tuple[str, str]:
    """Returns (message, source) where source is "llm" or "template"."""
    template = TEMPLATES.get(action, "")
    if action not in GOALS or not settings.RESCUE_USE_LLM:
        return template, "template"

    prompt = (
        f"Write ONE short, friendly sentence (under 25 words) to {GOALS[action]}. "
        "Use only these facts and invent nothing else. "
        "Never mention discounts, offers, prices, deadlines, reservations or urgency.\n"
        f"Facts: {facts}"
    )
    try:
        response = ollama.chat(
            [{"role": "user", "content": prompt}], timeout=settings.OLLAMA_MESSAGE_TIMEOUT_SECONDS
        )
        text = (response.get("message", {}).get("content") or "").strip().strip('"')
    except ollama.OllamaUnavailable:
        return template, "template"
    except Exception:  # never let message writing break event processing
        logger.exception("Unexpected error while writing an intervention message")
        return template, "template"

    if is_acceptable(text):
        return text, "llm"
    logger.info("Discarded an unsuitable model message: %r", text[:80])
    return template, "template"
