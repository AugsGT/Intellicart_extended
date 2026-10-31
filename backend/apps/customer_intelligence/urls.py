from django.urls import path

from apps.customer_intelligence.views import CustomerPurchaseHistoryView, HighIntentCustomersView, MyPurchaseHistoryView

urlpatterns = [
    path("me/purchase-history/", MyPurchaseHistoryView.as_view()),
    path("customers/<int:user_id>/purchase-history/", CustomerPurchaseHistoryView.as_view()),
    path("high-intent/", HighIntentCustomersView.as_view()),
]
