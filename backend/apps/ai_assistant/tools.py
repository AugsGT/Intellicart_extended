"""The only things the language model may do: READ-ONLY lookups of real data.

* Every tool returns catalogue or account data; none writes anything. There is no
  tool for the cart, orders or payments, so the model cannot change them.
* Tools never take a user id from the model. "My purchase history" always means the
  logged-in customer the server is talking to, so the model cannot read anyone else's.
* Arguments come from the model and are therefore checked before use.
"""
from decimal import Decimal, InvalidOperation

from apps.ai_assistant import advisor, requirements
from apps.customer_intelligence import services as intelligence
from apps.inventory.services import stock_status
from apps.products import services as product_services
from apps.products.models import Product
from apps.recommendations import services as recommendations

SEARCH_LIMIT = 8


def _number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def _active(product_id):
    try:
        return (
            Product.objects.select_related("category")
            .prefetch_related("attributes__definition")
            .filter(pk=int(product_id), status=Product.Status.ACTIVE)
            .first()
        )
    except (TypeError, ValueError):
        return None


def _summary(product: Product) -> dict:
    return {
        "id": product.id,
        "name": product.name,
        "brand": product.brand,
        "category": product.category.name,
        "price": float(product.price),
        "stock": product.stock,
        "status": stock_status(product.stock, product.low_stock_threshold),
    }


def _category_id(name):
    if not name:
        return None
    category = requirements._find_category(str(name).lower())
    return category.id if category else None


def search_products(args: dict, user=None) -> dict:
    params = {"ordering": "price", "q": str(args.get("query") or "")[:100], "in_stock": "true"}
    for key in ("min_price", "max_price"):
        number = _number(args.get(key))
        if number is not None:
            params[key] = number
    category = _category_id(args.get("category"))
    if category:
        params["category"] = category
    return {"results": [_summary(p) for p in product_services.search_products(params)[:SEARCH_LIMIT]]}


def filter_by_budget(args: dict, user=None) -> dict:
    params = {"ordering": "price", "in_stock": "true"}
    for source, target in (("min_budget", "min_price"), ("max_budget", "max_price")):
        number = _number(args.get(source))
        if number is not None:
            params[target] = number
    category = _category_id(args.get("category"))
    if category:
        params["category"] = category
    return {"results": [_summary(p) for p in product_services.search_products(params)[:SEARCH_LIMIT]]}


def get_product_details(args: dict, user=None) -> dict:
    product = _active(args.get("product_id"))
    if product is None:
        return {"error": "No product with that id"}
    return {**_summary(product), "description": product.description, "specifications": advisor.specifications(product)}


def get_product_specifications(args: dict, user=None) -> dict:
    product = _active(args.get("product_id"))
    if product is None:
        return {"error": "No product with that id"}
    return {"product": product.name, "specifications": advisor.specifications(product)}


def get_warranty_information(args: dict, user=None) -> dict:
    product = _active(args.get("product_id"))
    if product is None:
        return {"error": "No product with that id"}
    return {"product": product.name, **advisor.warranty_information(product)}


def check_stock(args: dict, user=None) -> dict:
    product = _active(args.get("product_id"))
    if product is None:
        return {"error": "No product with that id"}
    return {"product": product.name, "stock": product.stock, "status": stock_status(product.stock, product.low_stock_threshold)}


def compare_products(args: dict, user=None) -> dict:
    ids = args.get("product_ids")
    if not isinstance(ids, list) or not 2 <= len(ids) <= 4:
        return {"error": "Give 2 to 4 product ids to compare"}
    products = [p for p in (_active(i) for i in ids) if p is not None]
    if len(products) < 2:
        return {"error": "At least two of those products must exist"}
    comparison = advisor.compare(products)
    return {"products": [c["name"] for c in comparison["products"]], "rows": comparison["rows"], "leaders": comparison["leaders"]}


def get_similar_products(args: dict, user=None) -> dict:
    product = _active(args.get("product_id"))
    if product is None:
        return {"error": "No product with that id"}
    subs = recommendations.substitutes(product)
    if subs:
        return {"results": [_summary(r.product) for r in subs], "reason": "in_stock_substitute"}
    return {"results": [_summary(r.product) for r in recommendations.similar_products(product)]}


def get_personalized_recommendations(args: dict, user=None) -> dict:
    if user is None:
        return {"results": [], "note": "Personalized suggestions need a logged-in customer."}
    recs = recommendations.personalized(user)
    return {"results": [{**_summary(r.product), "reason": r.reason} for r in recs]}


def get_customer_purchase_history(args: dict, user=None) -> dict:
    """The logged-in customer's own purchases (successful orders only). No address or payment data."""
    if user is None:
        return {"orders": [], "note": "Purchase history needs a logged-in customer."}
    history = intelligence.purchase_history(user, order_limit=5)
    stats = history["stats"]
    return {
        "order_count": stats["order_count"],
        "items_purchased": stats["items_purchased"],
        "most_bought": [p["name"] for p in stats["top_products"][:3]],
        "recent_orders": [
            {"order_id": o["order_id"], "items": [f"{i['name']} x{i['quantity']}" for i in o["items"]]} for o in history["orders"]
        ],
    }


TOOL_FUNCTIONS = {
    "search_products": search_products,
    "get_product_details": get_product_details,
    "filter_by_budget": filter_by_budget,
    "compare_products": compare_products,
    "get_product_specifications": get_product_specifications,
    "get_warranty_information": get_warranty_information,
    "check_stock": check_stock,
    "get_similar_products": get_similar_products,
    "get_personalized_recommendations": get_personalized_recommendations,
    "get_customer_purchase_history": get_customer_purchase_history,
}


def _tool(name, description, properties=None, required=None):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties or {}, **({"required": required} if required else {})},
        },
    }


_PRODUCT_ID = {"product_id": {"type": "integer"}}

TOOLS = [
    _tool("search_products", "Search in-stock products by keyword, category name and price range (INR).",
          {"query": {"type": "string"}, "category": {"type": "string", "description": "e.g. laptops, phones"},
           "min_price": {"type": "number"}, "max_price": {"type": "number"}}),
    _tool("get_product_details", "Price, stock, description and specifications of one product.", _PRODUCT_ID, ["product_id"]),
    _tool("filter_by_budget", "In-stock products within a budget, cheapest first.",
          {"max_budget": {"type": "number"}, "min_budget": {"type": "number"}, "category": {"type": "string"}}),
    _tool("compare_products", "Side-by-side comparison of 2 to 4 products by id.",
          {"product_ids": {"type": "array", "items": {"type": "integer"}}}, ["product_ids"]),
    _tool("get_product_specifications", "All catalogue specifications of one product.", _PRODUCT_ID, ["product_id"]),
    _tool("get_warranty_information", "Warranty length, type and service coverage exactly as the catalogue states them.", _PRODUCT_ID, ["product_id"]),
    _tool("check_stock", "Current stock level of one product.", _PRODUCT_ID, ["product_id"]),
    _tool("get_similar_products", "Alternatives to a product; in-stock substitutes if it is low or out of stock.", _PRODUCT_ID, ["product_id"]),
    _tool("get_personalized_recommendations", "Suggestions based on this customer's own history. Takes no arguments."),
    _tool("get_customer_purchase_history", "This customer's own recent purchases. Takes no arguments."),
]


def dispatch(name: str, args, user=None) -> dict:
    function = TOOL_FUNCTIONS.get(name)
    if function is None:
        return {"error": f"Unknown tool '{name}'"}
    return function(args if isinstance(args, dict) else {}, user=user)
