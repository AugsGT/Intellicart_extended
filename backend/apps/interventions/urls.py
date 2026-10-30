from django.urls import path

from apps.interventions import views

urlpatterns = [
    path("", views.InterventionListView.as_view()),
    path("active/", views.ActiveInterventionView.as_view()),
    path("<int:pk>/dismiss/", views.DismissView.as_view()),
    path("<int:pk>/click/", views.ClickView.as_view()),
]
