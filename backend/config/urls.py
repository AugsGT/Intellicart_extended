from django.contrib import admin
from django.db import connection
from django.http import JsonResponse
from django.urls import include, path
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny


@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    """Liveness plus a database check, for the ops console and Docker later."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        database_up = True
    except Exception:
        database_up = False

    body = {"status": "healthy" if database_up else "degraded", "database": "up" if database_up else "down"}
    return JsonResponse(body, status=200 if database_up else 503)


handler404 = "config.exceptions.not_found"
handler500 = "config.exceptions.server_error"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", health),
    path("auth/", include("apps.accounts.auth_urls")),
    path("users/", include("apps.accounts.user_urls")),
    path("categories/", include("apps.categories.urls")),
    path("products/", include("apps.products.urls")),
    path("inventory/", include("apps.inventory.urls")),
    path("alerts/", include("apps.inventory.alert_urls")),
    path("cart/", include("apps.cart.urls")),
    path("orders/", include("apps.orders.urls")),
    path("customer-intelligence/", include("apps.customer_intelligence.urls")),
    path("analytics/", include("apps.analytics.urls")),
    path("demand/", include("apps.demand_intelligence.urls")),
    path("events/", include("apps.events.urls")),
    path("recommendations/", include("apps.recommendations.urls")),
    path("interventions/", include("apps.interventions.urls")),
    path("assistant/", include("apps.ai_assistant.urls")),
    path("ops-assistant/", include("apps.ai_assistant.ops_urls")),
    path("audit/", include("apps.audit.urls")),
]
