import pytest
from django.contrib.auth.models import AnonymousUser
from rest_framework.test import APIRequestFactory

from apps.accounts.models import User
from apps.accounts.permissions import IsOwnerOrStaff
from tests.conftest import PASSWORD

pytestmark = pytest.mark.django_db


# ---------- registration ----------

def register(client, **overrides):
    body = {"username": "new", "email": "New@Example.com", "password": PASSWORD, **overrides}
    return client.post("/users/register/", body, format="json")


def test_register_creates_customer_with_hashed_password(client):
    response = register(client)
    assert response.status_code == 201
    assert response.json()["role"] == "CUSTOMER"
    assert "password" not in response.json()
    user = User.objects.get(email="new@example.com")  # stored lowercase
    assert user.password != PASSWORD and user.check_password(PASSWORD)


def test_register_cannot_choose_a_role(client):
    response = register(client, role="ADMIN", is_superuser=True)
    assert response.status_code == 201
    user = User.objects.get(email="new@example.com")
    assert user.role == "CUSTOMER" and not user.is_superuser


def test_register_rejects_duplicate_email_ignoring_case(client):
    assert register(client).status_code == 201
    assert register(client, username="other", email="NEW@example.COM").status_code == 400


def test_register_rejects_weak_password(client):
    assert register(client, password="12345678").status_code == 400
    assert register(client, password="short").status_code == 400


# ---------- login, refresh, logout ----------

def test_login_returns_tokens_and_email_is_case_insensitive(client, make_user):
    user = make_user(email="shopper@example.com")
    response = client.post("/auth/login/", {"email": "SHOPPER@example.com", "password": PASSWORD}, format="json")
    assert response.status_code == 200
    assert set(response.json()) == {"access", "refresh"}


def test_login_failures_are_401_with_same_message(client, make_user):
    user = make_user()
    wrong_password = client.post("/auth/login/", {"email": user.email, "password": "nope-nope-nope"}, format="json")
    unknown_email = client.post("/auth/login/", {"email": "ghost@example.com", "password": PASSWORD}, format="json")
    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()


def test_deactivated_user_cannot_log_in(client, make_user):
    user = make_user()
    user.is_active = False
    user.save()
    response = client.post("/auth/login/", {"email": user.email, "password": PASSWORD}, format="json")
    assert response.status_code == 401


def test_login_is_rate_limited(client, make_user):
    user = make_user()
    codes = [
        client.post("/auth/login/", {"email": user.email, "password": "wrong-wrong"}, format="json").status_code
        for _ in range(12)
    ]
    assert codes[:10] == [401] * 10
    assert 429 in codes[10:]


def test_refresh_rotates_and_old_refresh_is_blacklisted(client, make_user, login_as):
    tokens = login_as(make_user()).tokens
    first = client.post("/auth/refresh/", {"refresh": tokens["refresh"]}, format="json")
    assert first.status_code == 200 and first.json()["refresh"] != tokens["refresh"]
    reuse = client.post("/auth/refresh/", {"refresh": tokens["refresh"]}, format="json")
    assert reuse.status_code == 401


def test_logout_blacklists_refresh_token(client, make_user, login_as):
    authed = login_as(make_user())
    assert authed.post("/auth/logout/", {"refresh": authed.tokens["refresh"]}, format="json").status_code == 200
    again = client.post("/auth/refresh/", {"refresh": authed.tokens["refresh"]}, format="json")
    assert again.status_code == 401


def test_logout_requires_login(client, make_user, login_as):
    tokens = login_as(make_user()).tokens
    assert client.post("/auth/logout/", {"refresh": tokens["refresh"]}, format="json").status_code == 401


# ---------- profile ----------

def test_me_requires_login(client):
    assert client.get("/users/me/").status_code == 401


def test_me_returns_own_profile(make_user, login_as):
    user = make_user(email="me@example.com")
    response = login_as(user).get("/users/me/")
    assert response.status_code == 200
    assert response.json()["email"] == "me@example.com" and response.json()["role"] == "CUSTOMER"


def test_customer_cannot_change_own_role(make_user, login_as):
    user = make_user()
    response = login_as(user).patch("/users/me/", {"role": "ADMIN", "username": "renamed"}, format="json")
    assert response.status_code == 200
    user.refresh_from_db()
    assert user.role == "CUSTOMER" and user.username == "renamed"


def test_cannot_take_another_users_email(make_user, login_as):
    other = make_user(email="taken@example.com")
    me = make_user()
    response = login_as(me).patch("/users/me/", {"email": "TAKEN@example.com"}, format="json")
    assert response.status_code == 400


# ---------- role permissions ----------

@pytest.mark.parametrize("role,expected", [("CUSTOMER", 403), ("OPERATIONS", 403), ("ADMIN", 200)])
def test_only_admin_can_list_users(make_user, login_as, role, expected):
    assert login_as(make_user(role=role)).get("/users/").status_code == expected


def test_anonymous_gets_401_not_403_on_admin_routes(client):
    assert client.get("/users/").status_code == 401


def test_admin_can_change_role_and_it_applies_immediately(make_user, login_as):
    admin = login_as(make_user(role="ADMIN"))
    target = make_user()
    target_client = login_as(target)
    assert target_client.get("/users/").status_code == 403

    assert admin.patch(f"/users/{target.id}/", {"role": "ADMIN"}, format="json").status_code == 200
    # Same access token, new role: permissions are read from the database, not the token.
    assert target_client.get("/users/").status_code == 200


def test_admin_deactivates_instead_of_deleting_and_not_self(make_user, login_as, client):
    admin_user = make_user(role="ADMIN")
    admin = login_as(admin_user)
    target = make_user()

    assert admin.delete(f"/users/{admin_user.id}/").status_code == 400
    assert admin.delete(f"/users/{target.id}/").status_code == 200
    assert User.objects.filter(pk=target.id, is_active=False).exists()
    assert client.post("/auth/login/", {"email": target.email, "password": PASSWORD}, format="json").status_code == 401


def test_deactivated_users_existing_token_stops_working(make_user, login_as):
    user = make_user()
    authed = login_as(user)
    user.is_active = False
    user.save()
    assert authed.get("/users/me/").status_code == 401


# ---------- ownership permission (used by cart/orders from Phase 3) ----------

class Owned:
    def __init__(self, user_id):
        self.user_id = user_id


def check_owner(user, obj):
    request = APIRequestFactory().get("/")
    request.user = user
    return IsOwnerOrStaff().has_object_permission(request, None, obj)


def test_owner_permission_allows_owner_and_staff_only(make_user):
    owner, stranger = make_user(), make_user()
    ops, admin = make_user(role="OPERATIONS"), make_user(role="ADMIN")
    order = Owned(owner.id)
    assert check_owner(owner, order)
    assert check_owner(ops, order) and check_owner(admin, order)
    assert not check_owner(stranger, order)
