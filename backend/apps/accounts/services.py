from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import User


class AuthError(Exception):
    pass


def login(email: str, password: str) -> dict:
    """Check credentials and return a token pair. The same message is used for
    unknown email, wrong password and disabled account, so it reveals nothing."""
    user = User.objects.filter(email__iexact=email.strip()).first()
    if user is None or not user.is_active or not user.check_password(password):
        raise AuthError("Invalid email or password")

    refresh = RefreshToken.for_user(user)
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


def logout(refresh_token: str) -> None:
    """Blacklist the refresh token. The short-lived access token simply expires
    (access tokens are stateless; see ACCESS_TOKEN_LIFETIME)."""
    try:
        RefreshToken(refresh_token).blacklist()
    except TokenError as error:
        raise AuthError("Invalid token") from error
