from __future__ import annotations

from rest_framework.permissions import BasePermission


class IsAdminRole(BasePermission):
    """Permite solo a usuarios con role='administrador'."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_admin)


class IsOwnerOrAdminRole(BasePermission):
    """Permite al dueño del objeto o a admins. El objeto debe tener atributo `user`."""

    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.is_admin or obj.user_id == request.user.pk
