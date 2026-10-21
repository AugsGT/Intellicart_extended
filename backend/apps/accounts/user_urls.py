from django.urls import path

from apps.accounts.views import MeView, RegisterView, UserDetailView, UserListView

urlpatterns = [
    path("me/", MeView.as_view()),
    path("register/", RegisterView.as_view()),
    path("<int:pk>/", UserDetailView.as_view()),
    path("", UserListView.as_view()),
]
