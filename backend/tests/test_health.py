import pytest
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_health_is_public_and_reports_database():
    response = APIClient().get("/health/")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "database": "up"}


def test_private_by_default_unknown_api_requires_login_setting():
    from django.conf import settings

    permissions = settings.REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"]
    assert permissions == ["rest_framework.permissions.IsAuthenticated"]
