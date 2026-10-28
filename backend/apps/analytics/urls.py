from django.urls import path

from apps.analytics.views import OverviewView, ProductBehaviourView, SalesOverviewView, SystemHealthView

urlpatterns = [
    path("overview/", OverviewView.as_view()),
    path("products/", ProductBehaviourView.as_view()),
    path("sales/", SalesOverviewView.as_view()),
    path("system/", SystemHealthView.as_view()),
]
