from django.urls import path

from apps.inventory.views import (
    AdjustStockView,
    InventoryListView,
    RestockView,
    StockHistoryView,
)

urlpatterns = [
    path("", InventoryListView.as_view()),
    path("<int:product_id>/history/", StockHistoryView.as_view()),
    path("<int:product_id>/restock/", RestockView.as_view()),
    path("<int:product_id>/adjust/", AdjustStockView.as_view()),
]
