from django.urls import path

from apps.demand_intelligence import views

urlpatterns = [
    path("overview/", views.OverviewView.as_view()),
    path("products/", views.ProductListView.as_view()),
    path("products/<int:product_id>/", views.ProductDetailView.as_view()),
    path("restock/", views.RestockView.as_view()),
    path("sales/", views.SalesView.as_view()),
]
