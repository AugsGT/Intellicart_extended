from decimal import Decimal

import pytest

from apps.ai_assistant import advisor, requirements, tools
from tests.advisor_catalogue import catalogue  # noqa: F401  (fixture)

pytestmark = pytest.mark.django_db


def parse(text):
    return requirements.extract(text)


# ---------- understanding the customer (the brief's own examples) ----------

def test_laptop_example_from_the_brief(catalogue):
    update = parse("My budget is ₹60,000. I need a laptop for programming, good battery life and reliable warranty service.")
    assert update.category_name == "Laptops" and update.max_budget == Decimal("60000")
    assert update.usage == ["programming"]
    assert update.priorities == ["battery_life", "warranty", "service"]     # in the order the customer said them


def test_earbuds_example(catalogue):
    update = parse("I need wireless earbuds under ₹3,000 with good noise cancellation.")
    assert (update.category_name, update.max_budget, update.priorities) == ("Audio", Decimal("3000"), ["noise_cancellation"])


def test_chair_example_does_not_mistake_the_product_for_a_usage(catalogue):
    update = parse("Suggest a durable office chair under ₹10,000.")
    assert (update.category_name, update.max_budget, update.priorities, update.usage) == ("Office Chairs", Decimal("10000"), ["durability"], [])


def test_phone_example_flags_what_the_catalogue_cannot_verify(catalogue):
    update = parse("Find a phone with a good camera and at least two days of battery life.")
    assert update.category_name == "Phones" and update.priorities == ["camera", "battery_life"]
    assert len(update.unverifiable) == 1 and "two day(s) of battery life" in update.unverifiable[0]


@pytest.mark.parametrize(
    "text,low,high",
    [
        ("laptop under 60000", None, "60000"),
        ("laptop below ₹1,50,000", None, "150000"),
        ("a laptop under 60k", None, "60000"),
        ("a laptop under 1.5 lakh", None, "150000"),
        ("budget is 45000", None, "45000"),
        ("laptop between 40000 and 60000", "40000", "60000"),
        ("laptop between 60k and 40k", "40000", "60000"),
        ("a laptop for ₹55,000", None, "55000"),
    ],
)
def test_budget_phrasing(catalogue, text, low, high):
    update = parse(text)
    assert (update.min_budget, update.max_budget) == (Decimal(low) if low else None, Decimal(high))


def test_numbers_with_units_are_not_budgets(catalogue):
    update = parse("a laptop with at least 16GB RAM, 512 GB SSD, 2 year warranty and 10 hours battery")
    assert update.max_budget is None and update.min_budget is None
    assert update.min_specs == {"ram_gb": 16, "storage_gb": 512, "warranty_months": 24, "battery_hours": 10}


def test_terabytes_and_brands(catalogue):
    update = parse("a Nimbus laptop with 1 TB storage")
    assert update.brand == "Nimbus" and update.min_specs == {"storage_gb": 1024}


def test_battery_matters_more_than_gaming(catalogue):
    update = parse("Battery life matters more than gaming performance")
    assert update.priorities == ["battery_life"] and set(update.demoted) == {"gaming", "performance"}
    assert update.usage == []


# ---------- remembering across messages ----------

def test_requirements_accumulate_and_new_priorities_come_first(catalogue):
    state = requirements.merge(requirements.empty_requirements(), parse("laptop under 60000 for programming, warranty matters"))
    state = requirements.merge(state, parse("also good battery life"))
    assert state["max_budget"] == 60000 and state["usage"] == ["programming"]
    assert state["priorities"] == ["battery_life", "warranty"]


def test_demoting_removes_the_priority_and_usage(catalogue):
    state = requirements.merge(requirements.empty_requirements(), parse("laptop for programming and gaming, performance matters"))
    state = requirements.merge(state, parse("Battery life matters more than gaming performance"))
    assert state["priorities"][0] == "battery_life" and "performance" not in state["priorities"]
    assert state["usage"] == ["programming"]


def test_changing_category_keeps_the_budget_but_drops_category_specific_requirements(catalogue):
    state = requirements.merge(requirements.empty_requirements(), parse("a Nimbus laptop under 60000 with 16GB RAM"))
    state = requirements.merge(state, parse("actually show me phones"))
    assert state["category_name"] == "Phones" and state["max_budget"] == 60000
    assert state["min_specs"] == {} and state["brand"] is None


def test_reset_and_clearing_the_budget(catalogue):
    state = requirements.merge(requirements.empty_requirements(), parse("laptop under 60000"))
    assert requirements.merge(state, parse("no budget limit"))["max_budget"] is None
    assert requirements.merge(state, parse("start over")) == requirements.empty_requirements()


# ---------- finding and ranking real products ----------

def recommend(**overrides):
    base = {"category_id": None, "max_budget": None, "min_budget": None, "usage": [], "priorities": [], "brand": None, "min_specs": {}}
    return advisor.recommend({**base, **overrides}, limit=10)


def names(result):
    return [card["name"] for card in result["cards"]]


def test_only_real_in_stock_products_within_budget_are_recommended(catalogue):
    laptops = catalogue["alpha"].category_id
    result = recommend(category_id=laptops, max_budget=60000)
    assert set(names(result)) == {"Alpha 14 Laptop", "Bravo 13 Laptop", "Endurance 15 Laptop", "Plain Laptop"}
    assert result["left_out"] == {"out_of_stock": 1, "over_budget": 1, "under_budget": 0, "below_requested_specs": 0}
    assert all(card["id"] in {p.id for p in catalogue.values()} for card in result["cards"])


def test_priorities_are_applied_in_the_order_given(catalogue):
    cid = catalogue["alpha"].category_id
    battery_first = recommend(category_id=cid, max_budget=60000, priorities=["battery_life", "warranty"])
    warranty_first = recommend(category_id=cid, max_budget=60000, priorities=["warranty", "battery_life"])
    assert names(battery_first)[0] == "Endurance 15 Laptop"      # 20 h battery, but only 12 months warranty
    assert names(warranty_first)[0] == "Alpha 14 Laptop"         # 24 months warranty, 14 h battery
    assert names(battery_first) != names(warranty_first)         # re-ranking really changes the order


def test_a_product_with_no_data_never_outranks_one_that_has_data(catalogue):
    result = recommend(category_id=catalogue["alpha"].category_id, max_budget=60000, priorities=["battery_life"])
    assert names(result)[-1] == "Plain Laptop"                   # cheaper, but the catalogue says nothing about it


def test_explanations_only_state_what_the_catalogue_says(catalogue):
    result = recommend(category_id=catalogue["alpha"].category_id, max_budget=60000, priorities=["battery_life", "service", "durability"])
    cards = {c["name"]: c["explanation"] for c in result["cards"]}

    alpha = cards["Alpha 14 Laptop"]
    assert alpha["fits_budget"] and "within your ₹60,000 budget" in alpha["budget_note"]
    assert any("Pan-India" in text for text in alpha["meets"])
    assert any("not verified" in text for text in alpha["info"])               # durability is reported as fact, never as a verdict
    assert alpha["warranty"]["statement"] == "Warranty: 24 months; type: On-site; Service coverage: Pan-India service centres"

    bravo = cards["Bravo 13 Laptop"]
    assert bravo["warranty"]["service_coverage"] is None
    assert "Service coverage: not available" in bravo["warranty"]["statement"]
    assert any("not stated in the catalogue" in text for text in bravo["unknown"])

    plain = cards["Plain Laptop"]
    assert plain["warranty"]["months"] is None and "not available in the catalogue" in plain["warranty"]["statement"]
    assert plain["meets"] == []                                                # nothing is claimed without data


def test_numeric_priorities_are_judged_against_the_other_options(catalogue):
    result = recommend(category_id=catalogue["alpha"].category_id, max_budget=60000, priorities=["battery_life"])
    cards = {c["name"]: c["explanation"] for c in result["cards"]}
    assert any("(the best of these options)" in t for t in cards["Endurance 15 Laptop"]["meets"])
    assert any("compared with 20 for the best" in t for t in cards["Bravo 13 Laptop"]["does_not_meet"])
    assert any("below" not in t for t in cards["Bravo 13 Laptop"]["limitations"])


def test_explicit_spec_minimums_exclude_known_failures_but_flag_unknowns(catalogue):
    result = recommend(category_id=catalogue["alpha"].category_id, max_budget=60000, min_specs={"ram_gb": 16})
    assert names(result) == ["Alpha 14 Laptop", "Plain Laptop"]                # 8 GB laptops are out; no-data laptop stays, flagged
    plain = [c for c in result["cards"] if c["name"] == "Plain Laptop"][0]["explanation"]
    assert any("does not list it" in text for text in plain["unknown"])
    assert result["left_out"]["below_requested_specs"] == 2


def test_subjective_and_unverifiable_requests_are_reported_not_decided(catalogue):
    result = recommend(category_id=catalogue["alpha"].category_id, max_budget=60000, usage=["gaming"])
    assert all(any("no graphics" in t for t in c["explanation"]["unknown"]) for c in result["cards"])


def test_noise_cancellation_and_budget_for_earbuds(catalogue):
    result = recommend(category_id=catalogue["anc"].category_id, max_budget=3000, priorities=["noise_cancellation"])
    assert names(result) == ["Pulse ANC Earbuds", "Pulse Go Earbuds"]        # the 5000 rupee headphones are over budget
    cards = {c["name"]: c["explanation"] for c in result["cards"]}
    assert cards["Pulse Go Earbuds"]["does_not_meet"] == ["No noise cancellation"]


def test_phone_camera_priority_and_brand_filter(catalogue):
    result = recommend(category_id=catalogue["camx"].category_id, priorities=["camera"], brand="Orbit")
    assert names(result)[0] == "Cam X Phone"


def test_nothing_matching_returns_no_cards_but_counts_why(catalogue):
    result = recommend(category_id=catalogue["alpha"].category_id, max_budget=10000)
    assert result["cards"] == [] and result["left_out"]["over_budget"] == 5


# ---------- comparison ----------

def test_comparison_lists_facts_and_leaders_without_naming_a_winner(catalogue):
    comparison = advisor.compare([catalogue["alpha"], catalogue["endurance"]])
    rows = {r["label"]: r["values"] for r in comparison["rows"]}
    assert rows["Price"] == {catalogue["alpha"].id: "₹55,000", catalogue["endurance"].id: "₹58,000"}
    assert rows["RAM"][catalogue["alpha"].id] == "16 GB"
    leaders = {l["label"]: l["products"] for l in comparison["leaders"]}
    assert leaders["Lowest price"] == ["Alpha 14 Laptop"]
    assert leaders["Highest battery life (claimed)"] == ["Endurance 15 Laptop"]
    assert leaders["Highest warranty duration"] == ["Alpha 14 Laptop"]
    assert "winner" not in str(comparison).lower() and "best overall" not in str(comparison).lower()


def test_comparison_marks_missing_data(catalogue):
    comparison = advisor.compare([catalogue["alpha"], catalogue["plain"]])
    row = {r["label"]: r["values"] for r in comparison["rows"]}["RAM"]
    assert row[catalogue["plain"].id] == "not listed"


# ---------- the read-only tools ----------

def test_every_tool_the_brief_asks_for_exists_and_none_can_write():
    expected = {"search_products", "get_product_details", "filter_by_budget", "compare_products", "get_product_specifications",
                "get_warranty_information", "check_stock", "get_similar_products", "get_personalized_recommendations",
                "get_customer_purchase_history"}
    assert expected == set(tools.TOOL_FUNCTIONS) == {t["function"]["name"] for t in tools.TOOLS}
    assert not any(word in name for name in expected for word in ("add", "remove", "order", "pay", "checkout", "delete", "update"))


def test_tools_return_real_data_and_say_when_it_is_missing(catalogue):
    alpha, plain = catalogue["alpha"], catalogue["plain"]
    assert tools.dispatch("get_warranty_information", {"product_id": alpha.id})["months"] == 24
    assert tools.dispatch("get_warranty_information", {"product_id": plain.id})["months"] is None
    assert tools.dispatch("check_stock", {"product_id": catalogue["ghost"].id})["status"] == "out_of_stock"
    assert tools.dispatch("filter_by_budget", {"max_budget": 3000, "category": "earbuds"})["results"][0]["name"] == "Pulse Go Earbuds"
    assert tools.dispatch("compare_products", {"product_ids": [alpha.id, catalogue["bravo"].id]})["leaders"]
    assert "error" in tools.dispatch("compare_products", {"product_ids": [alpha.id]})
    assert "error" in tools.dispatch("get_product_details", {"product_id": 99999})


@pytest.mark.parametrize("name,args", [("nope", {}), ("search_products", "text"), ("search_products", {"max_price": "lots", "query": 5}),
                                       ("check_stock", {"product_id": "abc"}), ("compare_products", {"product_ids": "1,2"})])
def test_bad_tool_calls_never_crash(catalogue, name, args):
    assert isinstance(tools.dispatch(name, args), dict)


def test_purchase_history_tool_is_scoped_to_the_logged_in_customer(catalogue, make_user, place_order):
    alice, bob = make_user(), make_user()
    place_order(alice, (catalogue["anc"], 1))
    place_order(bob, (catalogue["ergo"], 1))

    mine = tools.dispatch("get_customer_purchase_history", {"user_id": bob.id}, user=alice)   # the model tries to read Bob's
    assert mine["most_bought"] == ["Pulse ANC Earbuds"]
    assert "address" not in str(mine).lower() and "phone" not in str(mine).lower()
    assert tools.dispatch("get_customer_purchase_history", {}, user=None)["orders"] == []
    assert tools.dispatch("get_personalized_recommendations", {}, user=None)["results"] == []
