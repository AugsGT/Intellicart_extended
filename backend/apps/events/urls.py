from django.urls import path

from apps.events.views import CheckoutStartedView, DeadLetterListView, EventListView

urlpatterns = [
    path("", EventListView.as_view()),
    path("dead-letters/", DeadLetterListView.as_view()),
    path("checkout-started/", CheckoutStartedView.as_view()),
]
