from django.urls import path

from apps.ai_assistant import ops_views

urlpatterns = [
    path("conversations/", ops_views.OpsConversationListCreateView.as_view()),
    path("conversations/<int:pk>/", ops_views.OpsConversationDetailView.as_view()),
    path("conversations/<int:pk>/messages/", ops_views.OpsAskView.as_view()),
]
