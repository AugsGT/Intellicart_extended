from apps.events.handlers import on
from apps.interventions import rescue


@on("CART_ABANDONED")
def cart_abandoned(event) -> None:
    rescue.handle_cart_abandoned(event)


@on("ORDER_COMPLETED")
def order_completed(event) -> None:
    rescue.record_recovery(event)


@on("STOCK_RESTOCKED")
def stock_restocked(event) -> None:
    rescue.handle_stock_restocked(event)
