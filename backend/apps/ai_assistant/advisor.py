"""The shopping advisor's engine: find, check, rank and compare real products.

Everything here is computed from catalogue data (product fields and structured
attributes). Nothing is invented:

* A claim like "meets your battery requirement" is only made when the product has
  that attribute. If the catalogue does not say, the answer is "not listed".
* Ranking is NOT a made-up score. Products are ordered by how well they satisfy the
  customer's priorities, strictly in the order the customer gave them (first
  priority first). Ties go to the product with fewer unknowns, then the one the catalogue
  describes best (more attributes), then the lower price. The reasons are shown with each product.
* Numeric priorities ("good battery life") are judged against the other options:
  a product meets the priority if its value is within 80% of the best one found.
  This avoids inventing absolute thresholds the catalogue cannot support.
* Subjective qualities (durability, reliability, gaming suitability) are reported as
  catalogue facts only; the engine never calls a product durable or reliable.
"""
from decimal import Decimal

from apps.ai_assistant.formatting import money
from apps.ai_assistant.requirements import PRIORITY_LABELS
from apps.inventory.services import stock_status
from apps.products import services as product_services
from apps.products.models import Product

RELATIVE_THRESHOLD = Decimal("0.8")

MEETS, DOES_NOT_MEET, UNKNOWN, INFO = "meets", "does_not_meet", "unknown", "info"
# Unknown never beats known: a product the catalogue says nothing about ranks with those that fail the priority.
_RANK = {MEETS: 2, INFO: 1, UNKNOWN: 0, DOES_NOT_MEET: 0}

# Priority -> numeric attribute keys that can be compared (first key a product has wins).
NUMERIC_PRIORITY_KEYS = {
    "battery_life": ["battery_hours", "battery_mah"],
    "camera": ["camera_mp"],
    "warranty": ["warranty_months"],
    "performance": ["ram_gb"],
}
# Attributes where a bigger number is better (used by comparisons).
HIGHER_IS_BETTER = {"ram_gb", "storage_gb", "battery_hours", "battery_mah", "camera_mp", "warranty_months", "weight_capacity_kg"}




# ---- reading attributes ---------------------------------------------------

def attributes_of(product: Product) -> dict:
    """key -> {"label", "unit", "value"} for the product's catalogue attributes."""
    result = {}
    for attribute in product.attributes.all():
        definition = attribute.definition
        value = attribute.value
        if isinstance(value, Decimal):
            # Plain numbers (16, 14.5), not Decimal: these values go into JSON stored with the conversation.
            value = int(value) if value == value.to_integral() else float(value)
        result[definition.key] = {"label": definition.label, "unit": definition.unit, "value": value}
    return result


def _show(attribute: dict) -> str:
    return f"{attribute['value']}{' ' + attribute['unit'] if attribute['unit'] else ''}"


def specifications(product: Product) -> list[dict]:
    return [{"label": a["label"], "value": _show(a)} for a in attributes_of(product).values()]


def warranty_information(product: Product) -> dict:
    """Warranty facts exactly as the catalogue states them; anything missing is reported as missing."""
    attrs = attributes_of(product)
    months = attrs.get("warranty_months", {}).get("value")
    kind = attrs.get("warranty_type", {}).get("value")
    coverage = attrs.get("service_coverage", {}).get("value")
    parts = []
    parts.append(f"Warranty: {months} months" if months is not None else "Warranty length: not available in the catalogue")
    parts.append(f"type: {kind}" if kind else "type: not available")
    parts.append(f"Service coverage: {coverage}" if coverage else "Service coverage: not available")
    return {"months": months, "type": kind, "service_coverage": coverage, "statement": "; ".join(parts)}


# ---- searching ------------------------------------------------------------

def _meets_min_specs(attrs: dict, min_specs: dict) -> str:
    """'yes', 'no' (known and below the minimum) or 'unknown' (the catalogue does not say)."""
    verdict = "yes"
    for key, minimum in min_specs.items():
        if key not in attrs:
            verdict = "unknown" if verdict == "yes" else verdict
            continue
        try:
            if Decimal(str(attrs[key]["value"])) < Decimal(str(minimum)):
                return "no"
        except Exception:
            verdict = "unknown"
    return verdict


def find_candidates(requirements: dict) -> tuple[list[Product], dict]:
    """Products that satisfy the hard requirements (category, brand, budget, minimum
    specs, in stock), plus counts of what was left out and why."""
    params = {"category": requirements.get("category_id"), "brand": requirements.get("brand")}
    everything = list(product_services.search_products({k: v for k, v in params.items() if v}))
    max_budget, min_budget = requirements.get("max_budget"), requirements.get("min_budget")

    left_out = {"out_of_stock": 0, "over_budget": 0, "under_budget": 0, "below_requested_specs": 0}
    eligible = []
    for product in everything:
        if product.stock <= 0:
            left_out["out_of_stock"] += 1
        elif max_budget is not None and product.price > Decimal(str(max_budget)):
            left_out["over_budget"] += 1
        elif min_budget is not None and product.price < Decimal(str(min_budget)):
            left_out["under_budget"] += 1
        elif _meets_min_specs(attributes_of(product), requirements.get("min_specs", {})) == "no":
            left_out["below_requested_specs"] += 1
        else:
            eligible.append(product)
    return eligible, left_out


# ---- checking one product against the requirements ------------------------

def _numeric_value(attrs: dict, key: str):
    if key in attrs and isinstance(attrs[key]["value"], (Decimal, int, float)):
        return Decimal(str(attrs[key]["value"]))
    return None


def _evaluate_priority(priority: str, attrs: dict, bests: dict, min_specs: dict) -> tuple[str, str]:
    label = PRIORITY_LABELS[priority]

    if priority in NUMERIC_PRIORITY_KEYS:
        for key in NUMERIC_PRIORITY_KEYS[priority]:
            value = _numeric_value(attrs, key)
            if value is None:
                continue
            shown, best = _show(attrs[key]), bests.get(key)
            minimum = min_specs.get(key)
            if minimum is not None:
                ok = value >= Decimal(str(minimum))
                return (MEETS, f"{attrs[key]['label']}: {shown} (you asked for at least {minimum})") if ok else (
                    DOES_NOT_MEET, f"{attrs[key]['label']}: {shown}, below the {minimum} you asked for")
            if best and value >= RELATIVE_THRESHOLD * best:
                tag = " (the best of these options)" if value == best else ""
                return MEETS, f"{attrs[key]['label']}: {shown}{tag}"
            return DOES_NOT_MEET, f"{attrs[key]['label']}: {shown}, compared with {best:g} for the best of these options"
        return UNKNOWN, f"{label.capitalize()}: not listed in the catalogue"

    if priority == "service":
        coverage = attrs.get("service_coverage")
        if coverage:
            return MEETS, f"Service coverage: {coverage['value']}"
        return UNKNOWN, "After-sales service coverage: not stated in the catalogue"

    if priority == "noise_cancellation":
        value = attrs.get("noise_cancellation")
        if value is None:
            return UNKNOWN, "Noise cancellation: not listed in the catalogue"
        if str(value["value"]).strip().lower() in ("none", "no"):
            return DOES_NOT_MEET, "No noise cancellation"
        return MEETS, f"Noise cancellation: {value['value']}"

    if priority == "durability":
        facts = [f"{attrs[k]['label'].lower()}: {attrs[k]['value']}" for k in ("build_quality", "material", "weight_capacity_kg") if k in attrs]
        if not facts:
            return UNKNOWN, "Durability: no build information in the catalogue"
        return INFO, "Catalogue lists " + ", ".join(facts) + ". There is no durability test data, so durability is not verified"

    if priority == "display":
        if "display" in attrs:
            return INFO, f"Display: {attrs['display']['value']}"
        return UNKNOWN, "Display: not listed in the catalogue"

    # portability and anything else the catalogue has no data for
    return UNKNOWN, f"{label.capitalize()}: the catalogue has no weight or size information"


def _usage_notes(usage: list[str], attrs: dict) -> list[tuple[str, str]]:
    notes = []
    if "programming" in usage:
        facts = [f"{attrs[k]['label']} {_show(attrs[k])}" for k in ("processor", "ram_gb", "storage_gb") if k in attrs]
        if facts:
            notes.append((INFO, "For programming, the catalogue lists: " + ", ".join(facts)))
    if "gaming" in usage:
        notes.append((UNKNOWN, "Gaming: the catalogue has no graphics (GPU) information, so suitability cannot be verified"))
    return notes


def evaluate(products: list[Product], requirements: dict) -> list[dict]:
    """Check every candidate against the requirements, then rank them (see module docstring)."""
    priorities = [p for p in requirements.get("priorities", []) if p in PRIORITY_LABELS]
    min_specs = requirements.get("min_specs", {})
    all_attrs = {p.id: attributes_of(p) for p in products}

    bests: dict[str, Decimal] = {}
    for attrs in all_attrs.values():
        for key in {k for keys in NUMERIC_PRIORITY_KEYS.values() for k in keys}:
            value = _numeric_value(attrs, key)
            if value is not None and value > bests.get(key, Decimal(0)):
                bests[key] = value

    max_budget = requirements.get("max_budget")
    evaluated = []
    for product in products:
        attrs = all_attrs[product.id]
        groups = {MEETS: [], DOES_NOT_MEET: [], UNKNOWN: [], INFO: []}
        vector = []
        for priority in priorities:
            status, text = _evaluate_priority(priority, attrs, bests, min_specs)
            groups[status].append(text)
            vector.append(_RANK[status])
        for status, text in _usage_notes(requirements.get("usage", []), attrs):
            groups[status].append(text)

        unverified_specs = [k for k in min_specs if k not in attrs]
        for key in unverified_specs:
            groups[UNKNOWN].append(f"You asked for {key.replace('_', ' ')} of at least {min_specs[key]}, but the catalogue does not list it")

        limitations = list(groups[DOES_NOT_MEET])
        if product.stock <= product.low_stock_threshold:
            limitations.append(f"Low stock: only {product.stock} left")

        if max_budget is not None:
            gap = Decimal(str(max_budget)) - product.price
            budget_note = f"{money(product.price)} is within your {money(max_budget)} budget ({money(gap)} to spare)"
        else:
            budget_note = f"{money(product.price)} (no budget given)"

        evaluated.append(
            {
                "product": product,
                "vector": vector,
                "attribute_count": len(attrs),
                "explanation": {
                    "fits_budget": max_budget is None or product.price <= Decimal(str(max_budget)),
                    "budget_note": budget_note,
                    "meets": groups[MEETS],
                    "does_not_meet": groups[DOES_NOT_MEET],
                    "unknown": groups[UNKNOWN],
                    "info": groups[INFO],
                    "advantages": list(groups[MEETS]),
                    "limitations": limitations,
                    "warranty": warranty_information(product),
                    "match_summary": (
                        f"Meets {len(groups[MEETS])} of your {len(priorities)} priorities"
                        if priorities else "Matches your category and budget"
                    ),
                },
            }
        )

    # Ties: fewer unknowns, then the product the catalogue describes best, then the lower price.
    evaluated.sort(
        key=lambda e: ([-v for v in e["vector"]], len(e["explanation"]["unknown"]), -e["attribute_count"], e["product"].price, e["product"].id)
    )
    return evaluated


# ---- presenting -----------------------------------------------------------

def product_card(product: Product, explanation: dict | None = None) -> dict:
    card = {
        "id": product.id,
        "name": product.name,
        "brand": product.brand,
        "category": product.category.name,
        "price": str(product.price),
        "image": product.image,
        "stock": product.stock,
        "stock_status": stock_status(product.stock, product.low_stock_threshold),
    }
    if explanation is not None:
        card["explanation"] = explanation
    return card


def recommend(requirements: dict, limit: int = 3) -> dict:
    """Top matches for the requirements, with explanations and what was left out."""
    candidates, left_out = find_candidates(requirements)
    ranked = evaluate(candidates, requirements)[:limit]
    return {
        "cards": [product_card(e["product"], e["explanation"]) for e in ranked],
        "ids": [e["product"].id for e in ranked],
        "considered": len(candidates),
        "left_out": left_out,
    }


# ---- comparing ------------------------------------------------------------

def compare(products: list[Product]) -> dict:
    """Side-by-side facts. Names the leader per attribute, never an overall winner."""
    all_attrs = {p.id: attributes_of(p) for p in products}
    rows = [{"label": "Price", "values": {p.id: money(p.price) for p in products}}]
    leaders = []

    cheapest = min(products, key=lambda p: p.price)
    leaders.append({"label": "Lowest price", "products": [p.name for p in products if p.price == cheapest.price]})

    keys = []
    for p in products:
        for key in all_attrs[p.id]:
            if key not in keys:
                keys.append(key)

    for key in keys:
        label = next(all_attrs[p.id][key]["label"] for p in products if key in all_attrs[p.id])
        rows.append({"label": label, "values": {p.id: _show(all_attrs[p.id][key]) if key in all_attrs[p.id] else "not listed" for p in products}})
        if key in HIGHER_IS_BETTER:
            numbers = {p.id: _numeric_value(all_attrs[p.id], key) for p in products}
            known = {pid: v for pid, v in numbers.items() if v is not None}
            if len(known) >= 2 and len(set(known.values())) > 1:
                top = max(known.values())
                leaders.append({"label": f"Highest {label.lower()}", "products": [p.name for p in products if known.get(p.id) == top]})

    rows.append({"label": "Stock", "values": {p.id: f"{p.stock} available" for p in products}})
    return {"products": [product_card(p) for p in products], "rows": rows, "leaders": leaders}
