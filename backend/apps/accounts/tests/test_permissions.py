from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from apps.accounts.permissions import IsAdminRole, IsOwnerOrAdminRole


def _user_mock(*, authenticated: bool = True, is_admin: bool = False, pk: int = 1):
    user = MagicMock()
    user.is_authenticated = authenticated
    user.is_admin = is_admin
    user.pk = pk
    return user


class TestIsAdminRole:
    def test_admin_authenticated_user_allowed(self):
        request = MagicMock(user=_user_mock(authenticated=True, is_admin=True))
        assert IsAdminRole().has_permission(request, None) is True

    def test_tecnico_user_denied(self):
        request = MagicMock(user=_user_mock(authenticated=True, is_admin=False))
        assert IsAdminRole().has_permission(request, None) is False

    def test_anonymous_user_denied(self):
        request = MagicMock(user=_user_mock(authenticated=False, is_admin=False))
        assert IsAdminRole().has_permission(request, None) is False


class TestIsOwnerOrAdminRole:
    def test_owner_allowed(self):
        user = _user_mock(authenticated=True, is_admin=False, pk=42)
        obj = MagicMock(user_id=42)
        request = MagicMock(user=user)
        assert IsOwnerOrAdminRole().has_object_permission(request, None, obj) is True

    def test_admin_allowed_even_if_not_owner(self):
        user = _user_mock(authenticated=True, is_admin=True, pk=1)
        obj = MagicMock(user_id=999)
        request = MagicMock(user=user)
        assert IsOwnerOrAdminRole().has_object_permission(request, None, obj) is True

    def test_other_user_denied(self):
        user = _user_mock(authenticated=True, is_admin=False, pk=1)
        obj = MagicMock(user_id=2)
        request = MagicMock(user=user)
        assert IsOwnerOrAdminRole().has_object_permission(request, None, obj) is False

    def test_anonymous_denied(self):
        user = _user_mock(authenticated=False, is_admin=False, pk=1)
        obj = MagicMock(user_id=1)
        request = MagicMock(user=user)
        assert IsOwnerOrAdminRole().has_object_permission(request, None, obj) is False
