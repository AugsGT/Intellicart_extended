from django.urls import path

from apps.orders.views import (
    OrderCancelView,
    OrderDetailView,
    OrderListCreateView,
    OrderStaffListView,
    OrderStatusView,
)

urlpatterns = [
    path("", OrderListCreateView.as_view()),
    path("admin/all/", OrderStaffListView.as_view()),
    path("<int:pk>/", OrderDetailView.as_view()),
    path("<int:pk>/cancel/", OrderCancelView.as_view()),
    path("<int:pk>/status/", OrderStatusView.as_view()),
]
