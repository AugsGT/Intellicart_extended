from django.urls import path

from apps.products.views import ProductDetailView, ProductListCreateView

urlpatterns = [
    path("", ProductListCreateView.as_view()),
    path("<int:pk>/", ProductDetailView.as_view()),
]
