"""Turns a customer's sentence into structured shopping requirements, and merges
what they say across messages.

This is plain rule-based parsing (regular expressions and keyword lists matched
against the real category and brand names in the catalogue). It is deterministic,
testable and never invents anything. The language model may add to it when it is
available (see orchestrator), but nothing depends on the model being up.

Requirements shape (stored in Conversation.requirements):
    category_id, category_name   the product category, or None
    min_budget, max_budget       INR numbers, or None
    usage                        e.g. ["programming", "gaming"]
    priorities                   most important first, e.g. ["battery_life", "warranty"]
    brand                        a brand present in the catalogue, or None
    min_specs                    hard minimums, e.g. {"ram_gb": 16, "warranty_months": 24}
    unverifiable                 requests the catalogue cannot check (reported honestly)
    asked                        questions already asked, so we never ask twice
"""
import re
from dataclasses import dataclass, field
from decimal import Decimal

from apps.ai_assistant.formatting import money
from apps.categories.models import Category
from apps.products.models import Product

# ---- vocabulary -----------------------------------------------------------

# Everyday words -> category slug (the slug must exist in the catalogue to be used).
CATEGORY_SYNONYMS = {
    "laptop": "laptops", "laptops": "laptops", "notebook": "laptops", "notebooks": "laptops",
    "phone": "phones", "phones": "phones", "smartphone": "phones", "smartphones": "phones", "mobile": "phones",
    "earbuds": "audio", "earbud": "audio", "earphones": "audio", "earphone": "audio", "headphones": "audio",
    "headphone": "audio", "headset": "audio", "audio": "audio",
    "chair": "office-chairs", "chairs": "office-chairs", "office chair": "office-chairs", "office chairs": "office-chairs",
}

USAGE_WORDS = {
    "programming": r"\bprogramm\w*|\bcoding\b|\bdevelop(?:er|ment)\b|\bsoftware\b",
    "gaming": r"\bgam(?:e|es|ing|er)\b",
    "office": r"\boffice\b|\bwork\b|\bbusiness\b",
    "study": r"\bstud(?:y|ent|ents|ies)\b|\bcollege\b|\bschool\b",
    "travel": r"\btravel\w*",
    "video_editing": r"\bvideo edit\w*|\bediting\b",
    "photography": r"\bphotograph\w*",
    "music": r"\bmusic\b|\bsongs?\b",
    "calls": r"\bcalls?\b|\bmeetings?\b",
}

PRIORITY_WORDS = {
    "battery_life": r"\bbattery\b",
    "durability": r"\bdurab\w*|\bsturdy\b|\bbuild quality\b|\brugged\b|\blong[- ]lasting\b|\bwell[- ]built\b",
    "warranty": r"\bwarrant\w*|\bguarantee\b",
    "service": r"\bafter[- ]?sales?\b|\bservice\b|\brepair\w*|\bsupport\b",
    "noise_cancellation": r"\bnoise[- ]cancel\w*|\banc\b",
    "camera": r"\bcamera\b|\bphoto quality\b",
    "performance": r"\bperformance\b|\bpowerful\b|\bfast\b|\bspeed\b",
    "portability": r"\bportab\w*|\blight[- ]?weight\b|\bslim\b|\bcompact\b",
    "display": r"\bdisplay\b|\bscreen\b",
}

PRIORITY_LABELS = {
    "battery_life": "battery life", "durability": "durability", "warranty": "warranty", "service": "after-sales service",
    "noise_cancellation": "noise cancellation", "camera": "camera", "performance": "performance",
    "portability": "portability", "display": "display",
}

NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7}

NUM = r"(\d[\d,]*(?:\.\d+)?)"
UNIT_AFTER = r"(?!\s*(?:gb|tb|mah|mp|hours?|hrs?|months?|years?|yrs?|kg|days?|inch|inches|%))"
CURRENCY = r"(?:rs\.?|inr|₹|rupees?)"
AMOUNT = rf"(?:{CURRENCY}\s*)?{NUM}\s*(k|lakhs?|thousand)?{UNIT_AFTER}(?:\s*{CURRENCY})?"
MAX_WORDS = (
    r"(?:under|below|less than|within|up to|upto|max(?:imum)?(?: of)?|not more than|no more than|"
    r"at most|cheaper than|budget(?: is| of| around| max| limit)?|around|about)"
)
MIN_WORDS = r"(?:above|over|more than|minimum of|min(?:imum)?)"


@dataclass
class Update:
    """What one message says. Merged into the conversation's requirements."""

    category_id: int | None = None
    category_name: str = ""
    min_budget: Decimal | None = None
    max_budget: Decimal | None = None
    clear_budget: bool = False
    usage: list[str] = field(default_factory=list)
    priorities: list[str] = field(default_factory=list)   # in the order they were mentioned
    demoted: list[str] = field(default_factory=list)      # "X matters more than Y": the Y's
    brand: str | None = None
    min_specs: dict = field(default_factory=dict)
    unverifiable: list[str] = field(default_factory=list)
    reset: bool = False

    def is_empty(self) -> bool:
        return not any([
            self.category_id, self.min_budget is not None, self.max_budget is not None, self.clear_budget,
            self.usage, self.priorities, self.demoted, self.brand, self.min_specs, self.unverifiable, self.reset,
        ])


def _amount(number: str, suffix: str | None) -> Decimal:
    value = Decimal(number.replace(",", ""))
    suffix = (suffix or "").lower()
    if suffix == "k" or suffix == "thousand":
        value *= 1000
    elif suffix.startswith("lakh"):
        value *= 100000
    return value


def _keywords_in_order(text: str, table: dict[str, str]) -> list[str]:
    found = []
    for key, pattern in table.items():
        match = re.search(pattern, text)
        if match:
            found.append((match.start(), key))
    return [key for _, key in sorted(found)]


def _find_category(text: str):
    """The category the text refers to, using everyday synonyms first, then real category names."""
    categories = {c.slug: c for c in Category.objects.all()}
    best = None
    for word, slug in CATEGORY_SYNONYMS.items():
        match = re.search(rf"\b{re.escape(word)}\b", text)
        if match and slug in categories and (best is None or match.start() < best[0]):
            best = (match.start(), categories[slug])
    if best:
        return best[1]
    for category in categories.values():
        if re.search(rf"\b{re.escape(category.name.lower())}\b", text):
            return category
    return None


def _find_brand(text: str) -> str | None:
    brands = {b for b in Product.objects.exclude(brand="").values_list("brand", flat=True).distinct()}
    for brand in sorted(brands, key=len, reverse=True):
        if re.search(rf"\b{re.escape(brand.lower())}\b", text):
            return brand
    return None


def _parse_budget(text: str, update: Update) -> None:
    between = re.search(rf"between\s+{AMOUNT}\s*(?:and|to|-)\s*{AMOUNT}", text)
    if between:
        low = _amount(between.group(1), between.group(2))
        high = _amount(between.group(3), between.group(4))
        update.min_budget, update.max_budget = min(low, high), max(low, high)
        return

    if re.search(r"\b(?:no budget|any budget|budget (?:does(?: not|n't) matter|is flexible)|no limit|unlimited budget|remove the budget)\b", text):
        update.clear_budget = True
        return

    maximum = re.search(rf"{MAX_WORDS}\s*(?:is|of|:)?\s*{AMOUNT}", text)
    if maximum:
        update.max_budget = _amount(maximum.group(1), maximum.group(2))
    minimum = re.search(rf"{MIN_WORDS}\s+{AMOUNT}", text)
    if minimum and _amount(minimum.group(1), minimum.group(2)) >= 100:
        update.min_budget = _amount(minimum.group(1), minimum.group(2))
    if update.max_budget is None and update.min_budget is None:
        # A bare amount with a currency marker ("₹60,000", "rs 5000") is read as the budget.
        bare = re.search(rf"{CURRENCY}\s*{NUM}\s*(k|lakhs?|thousand)?{UNIT_AFTER}|{NUM}\s*(k|lakhs?|thousand)?\s*{CURRENCY}", text)
        if bare:
            groups = bare.groups()
            number, suffix = (groups[0], groups[1]) if groups[0] else (groups[2], groups[3])
            update.max_budget = _amount(number, suffix)


def _to_gb(number: str, unit: str) -> int:
    return int(number) * (1024 if unit.lower() == "tb" else 1)


def _parse_specs(text: str, update: Update) -> None:
    ram = re.search(rf"(\d+)\s*gb\s*(?:of\s*)?ram|ram\s*(?:of\s*)?(\d+)\s*gb", text)
    if ram:
        update.min_specs["ram_gb"] = int(ram.group(1) or ram.group(2))

    storage = re.search(r"(\d+)\s*(gb|tb)\s*(?:of\s*)?(?:ssd|storage|hdd|disk)|(?:storage|ssd)\s*(?:of\s*)?(\d+)\s*(gb|tb)", text)
    if storage:
        number, unit = (storage.group(1), storage.group(2)) if storage.group(1) else (storage.group(3), storage.group(4))
        update.min_specs["storage_gb"] = _to_gb(number, unit)

    warranty = re.search(r"(\d+)\s*(year|yr|month)s?\s*(?:of\s*)?warranty|warranty\s*(?:of\s*)?(\d+)\s*(year|yr|month)s?", text)
    if warranty:
        number, unit = (warranty.group(1), warranty.group(2)) if warranty.group(1) else (warranty.group(3), warranty.group(4))
        update.min_specs["warranty_months"] = int(number) * (12 if unit in ("year", "yr") else 1)

    hours = re.search(r"(\d+)\s*(?:hours?|hrs?)\s*(?:of\s*)?battery|battery\s*(?:life\s*)?(?:of\s*)?(\d+)\s*(?:hours?|hrs?)", text)
    if hours:
        update.min_specs["battery_hours"] = int(hours.group(1) or hours.group(2))

    days = re.search(r"(\d+|" + "|".join(NUMBER_WORDS) + r")\s*days?\s*(?:of\s*)?(?:battery|battery life)", text)
    if days:
        update.unverifiable.append(
            f"{days.group(1)} day(s) of battery life (the catalogue lists battery capacity or claimed hours, not days of use)"
        )


def _parse_more_important(text: str, update: Update) -> None:
    """'Battery life matters more than gaming performance' -> battery first, gaming demoted."""
    match = re.search(r"(.+?)\b(?:matters?|is|are)\s+(?:much\s+)?more(?:\s+important)?\s+than\b(.+)", text)
    if not match:
        return
    left, right = match.group(1), match.group(2)
    front = _keywords_in_order(left, PRIORITY_WORDS)
    if front:
        update.priorities = front
    update.demoted = _keywords_in_order(right, PRIORITY_WORDS) + _keywords_in_order(right, USAGE_WORDS)


def extract(text: str) -> Update:
    """Parse one customer message."""
    text = text.lower()
    update = Update()

    if re.search(r"\b(?:start over|start again|reset|new search|forget (?:everything|all that))\b", text):
        update.reset = True

    category = _find_category(text)
    if category:
        update.category_id, update.category_name = category.id, category.name

    _parse_budget(text, update)
    _parse_specs(text, update)
    update.brand = _find_brand(text)
    # Category words are not usage words ("office chair" is a product, not "for the office").
    usage_text = text
    for word in sorted(CATEGORY_SYNONYMS, key=len, reverse=True):
        usage_text = re.sub(rf"\b{re.escape(word)}\b", " ", usage_text)
    update.usage = _keywords_in_order(usage_text, USAGE_WORDS)
    update.priorities = _keywords_in_order(text, PRIORITY_WORDS)
    _parse_more_important(text, update)
    update.usage = [u for u in update.usage if u not in update.demoted]
    return update


# ---- merging across messages ---------------------------------------------

def empty_requirements() -> dict:
    return {
        "category_id": None, "category_name": "", "min_budget": None, "max_budget": None,
        "usage": [], "priorities": [], "brand": None, "min_specs": {}, "unverifiable": [], "asked": [],
    }


def merge(current: dict, update: Update) -> dict:
    """Combine what was already known with a new message. New information wins;
    nothing the customer said earlier is forgotten unless they change it."""
    if update.reset:
        return empty_requirements()

    state = {**empty_requirements(), **current}
    state["usage"] = list(state["usage"])
    state["priorities"] = list(state["priorities"])
    state["min_specs"] = dict(state["min_specs"])
    state["unverifiable"] = list(state["unverifiable"])
    state["asked"] = list(state["asked"])

    if update.category_id and update.category_id != state["category_id"]:
        if state["category_id"] is not None:
            state["min_specs"] = {}  # specs belong to a category (RAM means nothing for chairs)
            state["brand"] = None
        state["category_id"], state["category_name"] = update.category_id, update.category_name

    if update.clear_budget:
        state["min_budget"] = state["max_budget"] = None
        if "budget" not in state["asked"]:
            state["asked"].append("budget")
    if update.max_budget is not None:
        state["max_budget"] = float(update.max_budget)
    if update.min_budget is not None:
        state["min_budget"] = float(update.min_budget)

    for item in update.usage:
        if item not in state["usage"]:
            state["usage"].append(item)

    demoted = set(update.demoted)
    state["priorities"] = [p for p in state["priorities"] if p not in demoted]
    state["usage"] = [u for u in state["usage"] if u not in demoted or u in update.usage]
    # Priorities named in this message come first, in the order they were said.
    state["priorities"] = update.priorities + [p for p in state["priorities"] if p not in update.priorities and p not in demoted]

    if update.brand:
        state["brand"] = update.brand
    state["min_specs"].update(update.min_specs)
    for item in update.unverifiable:
        if item not in state["unverifiable"]:
            state["unverifiable"].append(item)
    return state


def describe(state: dict) -> str:
    """The requirements as a short phrase for replies, e.g. 'laptops up to ₹60,000 for programming'."""
    parts = [state.get("category_name", "").lower() or "products"]
    if state.get("min_budget") and state.get("max_budget"):
        parts.append(f"between {money(state['min_budget'])} and {money(state['max_budget'])}")
    elif state.get("max_budget"):
        parts.append(f"up to {money(state['max_budget'])}")
    elif state.get("min_budget"):
        parts.append(f"from {money(state['min_budget'])}")
    if state.get("brand"):
        parts.append(f"from {state['brand']}")
    if state.get("usage"):
        parts.append("for " + " and ".join(u.replace("_", " ") for u in state["usage"]))
    return " ".join(parts)


def priority_labels(state: dict) -> list[str]:
    return [PRIORITY_LABELS[p] for p in state.get("priorities", []) if p in PRIORITY_LABELS]
