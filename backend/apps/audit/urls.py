from django.urls import path

from apps.audit.views import AuditActionsView, AuditLogListView

urlpatterns = [
    path("", AuditLogListView.as_view()),
    path("actions/", AuditActionsView.as_view()),
]
