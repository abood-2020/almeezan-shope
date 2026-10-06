from rest_framework.permissions import BasePermission

from shop.services import get_active_trader


class IsActiveTrader(BasePermission):
    message = "An active trader account is required."

    def has_permission(self, request, view):
        return get_active_trader(request.user) is not None


class IsStaffUser(BasePermission):
    message = "Staff access is required."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_active and user.is_staff)
