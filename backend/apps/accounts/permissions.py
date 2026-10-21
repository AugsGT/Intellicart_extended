"""Role and ownership permissions. These run on the server; the frontend's
role checks are only a convenience."""
from rest_framework.permissions import BasePermission

from apps.accounts.models import User

STAFF_ROLES = (User.Role.ADMIN, User.Role.OPERATIONS)


class IsAdminRole(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.role == User.Role.ADMIN)


class IsStaffRole(BasePermission):
    """ADMIN or OPERATIONS."""

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.role in STAFF_ROLES)


class IsOwnerOrStaff(BasePermission):
    """Object-level rule for customer data (carts, orders, conversations):
    the owner (`obj.user`) or a staff member. Everyone else is refused."""

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.role in STAFF_ROLES:
            return True
        return getattr(obj, "user_id", None) == user.id


class IsAdminOrReadOnly(BasePermission):
    """Anyone may read (catalogue); only ADMIN may write."""

    def has_permission(self, request, view):
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return True
        return IsAdminRole().has_permission(request, view)
