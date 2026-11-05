from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from apps.accounts import services
from apps.accounts.models import User
from apps.accounts.permissions import STAFF_ROLES, IsAdminRole
from apps.audit import services as audit
from apps.accounts.serializers import (
    AdminUserUpdateSerializer,
    LoginSerializer,
    LogoutSerializer,
    ProfileUpdateSerializer,
    RegisterSerializer,
    UserSerializer,
)


class LoginThrottle(AnonRateThrottle):
    scope = "login"  # rate set in REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]


class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [LoginThrottle]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]
        try:
            tokens = services.login(**serializer.validated_data)
        except services.AuthError as error:
            audit.record(request, "LOGIN_FAILED", f"Failed login for {email}", entity_type="user", details={"email": email[:200]})
            return Response({"detail": str(error)}, status=status.HTTP_401_UNAUTHORIZED)

        user = User.objects.filter(email__iexact=email.strip()).first()
        if user is not None and user.role in STAFF_ROLES:
            audit.record(request, "STAFF_LOGIN", f"{user.email} logged in", actor=user, entity_type="user", entity_id=user.id)
        return Response(tokens)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            services.logout(serializer.validated_data["refresh"])
        except services.AuthError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": "Logged out"})


class RegisterThrottle(AnonRateThrottle):
    scope = "register"


class RegisterView(generics.CreateAPIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [RegisterThrottle]
    serializer_class = RegisterSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


class MeView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "patch", "head", "options"]

    def get_object(self):
        return self.request.user

    def get_serializer_class(self):
        return UserSerializer if self.request.method == "GET" else ProfileUpdateSerializer

    def patch(self, request, *args, **kwargs):
        serializer = ProfileUpdateSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(UserSerializer(request.user).data)


class UserListView(generics.ListAPIView):
    permission_classes = [IsAdminRole]
    serializer_class = UserSerializer
    queryset = User.objects.order_by("id")


class UserDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdminRole]
    queryset = User.objects.all()
    http_method_names = ["get", "patch", "delete", "head", "options"]

    def get_serializer_class(self):
        return UserSerializer if self.request.method == "GET" else AdminUserUpdateSerializer

    def patch(self, request, *args, **kwargs):
        user = self.get_object()
        fields = ("username", "email", "role", "is_active")
        before = {f: getattr(user, f) for f in fields}
        serializer = AdminUserUpdateSerializer(user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        changes = audit.changed_fields(before, {f: getattr(user, f) for f in fields})
        if changes:
            audit.record(request, "USER_UPDATED", f"Updated account {user.email}: {', '.join(changes)}",
                         entity_type="user", entity_id=user.id, details={"changes": changes})
        return Response(UserSerializer(user).data)

    def destroy(self, request, *args, **kwargs):
        # Accounts are deactivated, not deleted, so orders and history keep their owner.
        user = self.get_object()
        if user.pk == request.user.pk:
            return Response({"detail": "You cannot deactivate your own account"}, status=status.HTTP_400_BAD_REQUEST)
        user.is_active = False
        user.save(update_fields=["is_active"])
        audit.record(request, "USER_DEACTIVATED", f"Deactivated account {user.email}", entity_type="user", entity_id=user.id)
        return Response({"detail": "Account deactivated"})
