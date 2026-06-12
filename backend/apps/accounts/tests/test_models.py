from __future__ import annotations

import pytest

from apps.accounts.models import ROLE_ADMIN, ROLE_TECNICO, CustomUser


@pytest.mark.django_db
class TestCustomUserManager:
    def test_create_user_persists_with_hashed_password(self):
        user = CustomUser.objects.create_user(
            email="u@example.com", password="secret123", nombre="U", role=ROLE_TECNICO
        )
        assert user.pk is not None
        assert user.email == "u@example.com"
        assert user.role == ROLE_TECNICO
        assert user.check_password("secret123")
        # Password is never stored in plain text
        assert user.password != "secret123"

    def test_create_user_normalises_email(self):
        user = CustomUser.objects.create_user(
            email="Foo@Example.COM", password="x", nombre="N", role=ROLE_TECNICO
        )
        assert user.email == "Foo@example.com"

    def test_create_user_rejects_empty_email(self):
        with pytest.raises(ValueError, match="email"):
            CustomUser.objects.create_user(email="", password="x", nombre="N", role=ROLE_TECNICO)

    def test_create_superuser_sets_admin_flags(self):
        user = CustomUser.objects.create_superuser(
            email="root@example.com", password="x"
        )
        assert user.is_staff is True
        assert user.is_superuser is True
        assert user.role == ROLE_ADMIN


@pytest.mark.django_db
class TestCustomUser:
    def test_is_admin_property_true_for_administrador(self):
        u = CustomUser.objects.create_user(email="a@a.com", password="x", nombre="A", role=ROLE_ADMIN)
        assert u.is_admin is True

    def test_is_admin_property_false_for_tecnico(self):
        u = CustomUser.objects.create_user(email="t@t.com", password="x", nombre="T", role=ROLE_TECNICO)
        assert u.is_admin is False

    def test_email_is_unique(self):
        from django.db import IntegrityError
        CustomUser.objects.create_user(email="dup@x.com", password="x", nombre="A", role=ROLE_TECNICO)
        with pytest.raises(IntegrityError):
            CustomUser.objects.create_user(email="dup@x.com", password="y", nombre="B", role=ROLE_TECNICO)

    def test_str_representation_includes_email_and_name(self):
        u = CustomUser.objects.create_user(email="x@y.com", password="p", nombre="Ana", role=ROLE_TECNICO)
        assert "Ana" in str(u) and "x@y.com" in str(u)
