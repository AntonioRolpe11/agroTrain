"""Cover the admin-only UVL version REST endpoints."""
from __future__ import annotations

from pathlib import Path

import pytest

from apps.configurador.models import UVLVersion
from apps.configurador.services.flamapy_service import FlamapyService
from apps.configurador.services.uvl_version_service import _sha256


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "test_min.uvl"


@pytest.fixture(autouse=True)
def _warm():
    FlamapyService.warm_up(FIXTURE_PATH)


def _seed_version(versions_path, admin_user, name="v"):
    text = FIXTURE_PATH.read_text(encoding="utf-8")
    fname = f"{name}.uvl"
    (versions_path / fname).write_text(text, encoding="utf-8")
    return UVLVersion.objects.create(
        name=name, description="", file_path=fname,
        file_hash=_sha256(text) + name,
        author=admin_user, is_active=False, is_valid=True, validation_errors=[],
    )


@pytest.mark.django_db
class TestVersionDetailEndpoint:
    def test_admin_can_get_version_detail(self, admin_client, admin_user, settings, tmp_path):
        settings.UVL_VERSIONS_PATH = tmp_path
        version = _seed_version(tmp_path, admin_user, "detail")
        response = admin_client.get(f"/api/v1/uvl/versions/{version.pk}/")
        assert response.status_code == 200
        assert response.json()["name"] == "detail"

    def test_delete_version_when_not_active(self, admin_client, admin_user, settings, tmp_path):
        settings.UVL_VERSIONS_PATH = tmp_path
        # Two versions so the "only version" guard doesn't fire
        _seed_version(tmp_path, admin_user, "keep")
        rm = _seed_version(tmp_path, admin_user, "removeme")
        response = admin_client.delete(f"/api/v1/uvl/versions/{rm.pk}/")
        assert response.status_code == 204
        assert not UVLVersion.objects.filter(pk=rm.pk).exists()

    def test_delete_only_version_blocked(self, admin_client, admin_user, settings, tmp_path):
        settings.UVL_VERSIONS_PATH = tmp_path
        # Delete every existing version first (e.g., the one seeded on migrate)
        UVLVersion.objects.all().delete()
        sole = _seed_version(tmp_path, admin_user, "sole")
        response = admin_client.delete(f"/api/v1/uvl/versions/{sole.pk}/")
        assert response.status_code == 409


@pytest.mark.django_db
class TestPreviewActivationEndpoint:
    def test_admin_preview_returns_report(self, admin_client, admin_user, settings, tmp_path):
        settings.UVL_VERSIONS_PATH = tmp_path
        version = _seed_version(tmp_path, admin_user, "preview")
        response = admin_client.get(f"/api/v1/uvl/versions/{version.pk}/preview-activation/")
        assert response.status_code == 200
        data = response.json()
        assert "total" in data and "affected" in data


@pytest.mark.django_db
class TestActivateVersionEndpoint:
    def test_activate_succeeds_when_no_incompatible_configs(self, admin_client, admin_user, settings, tmp_path):
        settings.UVL_VERSIONS_PATH = tmp_path
        version = _seed_version(tmp_path, admin_user, "actv")
        response = admin_client.post(
            f"/api/v1/uvl/versions/{version.pk}/activate/",
            {"confirm_incompatible": False},
            format="json",
        )
        assert response.status_code == 200
        version.refresh_from_db()
        assert version.is_active is True


@pytest.mark.django_db
class TestCreateVersionEndpoint:
    def test_validate_endpoint_passes_on_valid_uvl(self, admin_client):
        # Reuse the active fixture tree
        tree = FlamapyService.to_dict()
        # ConstraintAST evaluation expects a constraint block — build a minimal one
        # The validate endpoint will technically check structural integrity only
        response = admin_client.post(
            "/api/v1/uvl/versions/validate/",
            {"tree": tree, "constraints_text": "Dendrometro => DatoMCD | DatoTB"},
            format="json",
        )
        assert response.status_code == 200
