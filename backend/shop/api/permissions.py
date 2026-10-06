from rest_framework.permissions import BasePermission

from shop.services import get_active_trader


class IsActiveTrader(BasePermission):
    message = "An active trader account is required."

    def has_permission(self, request, view):
        return get_active_trader(request.user) is not None
