from django.urls import path

from apps.cart.views import CartItemDetailView, CartItemsView, CartMergeView, CartView

urlpatterns = [
    path("", CartView.as_view()),
    path("items/", CartItemsView.as_view()),
    path("items/<int:item_id>/", CartItemDetailView.as_view()),
    path("merge/", CartMergeView.as_view()),
]
