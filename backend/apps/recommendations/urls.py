from django.urls import path

from apps.recommendations import views

urlpatterns = [
    path("products/<int:product_id>/similar/", views.SimilarView.as_view()),
    path("products/<int:product_id>/frequently-bought-together/", views.FrequentlyBoughtTogetherView.as_view()),
    path("products/<int:product_id>/substitutes/", views.SubstitutesView.as_view()),
    path("recently-viewed/", views.RecentlyViewedView.as_view()),
    path("cart-based/", views.CartBasedView.as_view()),
    path("personalized/", views.PersonalizedView.as_view()),
    path("click/", views.ClickView.as_view()),
    path("stats/", views.StatsView.as_view()),
]
