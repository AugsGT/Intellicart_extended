from django.urls import path

from apps.categories.views import (
    AttributeDefinitionCreateView,
    CategoryAttributesView,
    CategoryDetailView,
    CategoryListCreateView,
)

urlpatterns = [
    path("", CategoryListCreateView.as_view()),
    path("attributes/", AttributeDefinitionCreateView.as_view()),
    path("<int:pk>/", CategoryDetailView.as_view()),
    path("<int:pk>/attributes/", CategoryAttributesView.as_view()),
]
