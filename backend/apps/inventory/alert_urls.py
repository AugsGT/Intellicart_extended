from django.urls import path

from apps.inventory.views import AlertListView, AlertResolveView

urlpatterns = [
    path("", AlertListView.as_view()),
    path("<int:pk>/resolve/", AlertResolveView.as_view()),
]
