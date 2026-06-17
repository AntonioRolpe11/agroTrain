from __future__ import annotations

import pytest

from apps.accounts.models import ROLE_ADMIN, ROLE_TECNICO, CustomUser


@pytest.mark.django_db
class TestLogin:
    def test_login_returns_tokens(self, tecnico_user, anon_client):
        response = anon_client.post(
            "/api/v1/auth/login",
            {"email": tecnico_user.email, "password": "tecnico1234"},
            format="json",
        )
        assert response.status_code == 200
        assert "access" in response.data and "refresh" in response.data

    def test_login_with_invalid_credentials_fails(self, tecnico_user, anon_client):
        response = anon_client.post(
            "/api/v1/auth/login",
            {"email": tecnico_user.email, "password": "wrong"},
            format="json",
        )
        assert response.status_code == 401

    def test_refresh_returns_new_access_token(self, tecnico_user, anon_client):
        login = anon_client.post(
            "/api/v1/auth/login",
            {"email": tecnico_user.email, "password": "tecnico1234"},
            format="json",
        )
        refresh = login.data["refresh"]
        response = anon_client.post("/api/v1/auth/refresh", {"refresh": refresh}, format="json")
        assert response.status_code == 200
        assert "access" in response.data


@pytest.mark.django_db
class TestMe:
    def test_me_returns_current_user(self, tecnico_user, tecnico_client):
        response = tecnico_client.get("/api/v1/auth/me")
        assert response.status_code == 200
        assert response.data["email"] == tecnico_user.email
        assert response.data["role"] == ROLE_TECNICO

    def test_me_requires_authentication(self, anon_client):
        assert anon_client.get("/api/v1/auth/me").status_code == 401


@pytest.mark.django_db
class TestUserList:
    def test_admin_can_list_users(self, admin_client, tecnico_user):
        response = admin_client.get("/api/v1/auth/users/")
        assert response.status_code == 200
        emails = [u["email"] for u in response.data]
        assert tecnico_user.email in emails

    def test_tecnico_cannot_list_users(self, tecnico_client):
        assert tecnico_client.get("/api/v1/auth/users/").status_code == 403

    def test_anonymous_cannot_list_users(self, anon_client):
        assert anon_client.get("/api/v1/auth/users/").status_code in (401, 403)


@pytest.mark.django_db
class TestUserCreate:
    def test_admin_can_create_user(self, admin_client):
        response = admin_client.post(
            "/api/v1/auth/users/",
            {"email": "new@u.com", "nombre": "Nuevo", "role": ROLE_TECNICO, "password": "newpass12"},
            format="json",
        )
        assert response.status_code == 201
        assert CustomUser.objects.filter(email="new@u.com").exists()

    def test_create_user_with_short_password_fails(self, admin_client):
        response = admin_client.post(
            "/api/v1/auth/users/",
            {"email": "x@x.com", "nombre": "X", "role": ROLE_TECNICO, "password": "short"},
            format="json",
        )
        assert response.status_code in (400, 422)

    def test_tecnico_cannot_create_user(self, tecnico_client):
        response = tecnico_client.post(
            "/api/v1/auth/users/",
            {"email": "x@x.com", "nombre": "X", "role": ROLE_TECNICO, "password": "newpass12"},
            format="json",
        )
        assert response.status_code == 403


@pytest.mark.django_db
class TestUserDetail:
    def test_admin_can_view_other_user(self, admin_client, tecnico_user):
        response = admin_client.get(f"/api/v1/auth/users/{tecnico_user.pk}/")
        assert response.status_code == 200
        assert response.data["email"] == tecnico_user.email

    def test_tecnico_cannot_view_self_detail(self, tecnico_user, tecnico_client):
        # La gestión de usuarios es solo de admin; el técnico usa /auth/me.
        response = tecnico_client.get(f"/api/v1/auth/users/{tecnico_user.pk}/")
        assert response.status_code == 403

    def test_tecnico_cannot_view_other(self, tecnico_user, tecnico_client):
        other = CustomUser.objects.create_user(
            email="other@u.com", password="x", nombre="O", role=ROLE_TECNICO
        )
        response = tecnico_client.get(f"/api/v1/auth/users/{other.pk}/")
        assert response.status_code == 403

    def test_tecnico_cannot_edit_self(self, tecnico_user, tecnico_client):
        response = tecnico_client.patch(
            f"/api/v1/auth/users/{tecnico_user.pk}/",
            {"nombre": "Hackeado"},
            format="json",
        )
        assert response.status_code == 403
        tecnico_user.refresh_from_db()
        assert tecnico_user.nombre != "Hackeado"

    def test_admin_updates_user(self, admin_client, tecnico_user):
        response = admin_client.patch(
            f"/api/v1/auth/users/{tecnico_user.pk}/",
            {"nombre": "Nuevo Nombre"},
            format="json",
        )
        assert response.status_code == 200
        tecnico_user.refresh_from_db()
        assert tecnico_user.nombre == "Nuevo Nombre"

    def test_admin_deletes_user(self, admin_client, tecnico_user):
        pk = tecnico_user.pk
        response = admin_client.delete(f"/api/v1/auth/users/{pk}/")
        assert response.status_code == 204
        assert not CustomUser.objects.filter(pk=pk).exists()

    def test_tecnico_cannot_delete_admin(self, tecnico_client, admin_user):
        response = tecnico_client.delete(f"/api/v1/auth/users/{admin_user.pk}/")
        assert response.status_code == 403

    def test_admin_cannot_delete_self(self, admin_client, admin_user):
        response = admin_client.delete(f"/api/v1/auth/users/{admin_user.pk}/")
        assert response.status_code == 400

    def test_admin_cannot_deactivate_self(self, admin_client, admin_user):
        response = admin_client.patch(
            f"/api/v1/auth/users/{admin_user.pk}/",
            {"is_active": False},
            format="json",
        )
        assert response.status_code == 400

    def test_tecnico_cannot_escalate_own_role(self, tecnico_user, tecnico_client):
        response = tecnico_client.patch(
            f"/api/v1/auth/users/{tecnico_user.pk}/",
            {"role": ROLE_ADMIN},
            format="json",
        )
        assert response.status_code == 403
        tecnico_user.refresh_from_db()
        assert tecnico_user.role == ROLE_TECNICO

    def test_admin_can_change_other_user_role(self, admin_client, tecnico_user):
        response = admin_client.patch(
            f"/api/v1/auth/users/{tecnico_user.pk}/",
            {"role": ROLE_ADMIN},
            format="json",
        )
        assert response.status_code == 200
        tecnico_user.refresh_from_db()
        assert tecnico_user.role == ROLE_ADMIN

    def test_admin_cannot_change_own_role(self, admin_client, admin_user):
        response = admin_client.patch(
            f"/api/v1/auth/users/{admin_user.pk}/",
            {"role": ROLE_TECNICO},
            format="json",
        )
        assert response.status_code == 400
        admin_user.refresh_from_db()
        assert admin_user.role == ROLE_ADMIN

    def test_admin_can_change_email(self, admin_client, tecnico_user):
        response = admin_client.patch(
            f"/api/v1/auth/users/{tecnico_user.pk}/",
            {"email": "nuevo@u.com"},
            format="json",
        )
        assert response.status_code == 200
        tecnico_user.refresh_from_db()
        assert tecnico_user.email == "nuevo@u.com"

    def test_change_email_to_existing_fails(self, admin_client, admin_user, tecnico_user):
        response = admin_client.patch(
            f"/api/v1/auth/users/{tecnico_user.pk}/",
            {"email": admin_user.email},
            format="json",
        )
        assert response.status_code in (400, 422)
        tecnico_user.refresh_from_db()
        assert tecnico_user.email != admin_user.email

    def test_admin_can_reset_other_user_password(self, admin_client, tecnico_user):
        response = admin_client.patch(
            f"/api/v1/auth/users/{tecnico_user.pk}/",
            {"password": "nuevaClave9"},
            format="json",
        )
        assert response.status_code == 200
        tecnico_user.refresh_from_db()
        assert tecnico_user.check_password("nuevaClave9")

    def test_reset_password_too_short_fails(self, admin_client, tecnico_user):
        response = admin_client.patch(
            f"/api/v1/auth/users/{tecnico_user.pk}/",
            {"password": "short"},
            format="json",
        )
        assert response.status_code in (400, 422)

    def test_tecnico_cannot_change_own_password(self, tecnico_user, tecnico_client):
        response = tecnico_client.patch(
            f"/api/v1/auth/users/{tecnico_user.pk}/",
            {"password": "nuevaClave9"},
            format="json",
        )
        assert response.status_code == 403
        tecnico_user.refresh_from_db()
        assert not tecnico_user.check_password("nuevaClave9")
