from __future__ import annotations

from pathlib import Path

import pytest

from apps.configurador.models import Configuracion, UVLVersion
from apps.configurador.services.flamapy_service import FlamapyService
from apps.configurador.services.uvl_version_service import _sha256


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "test_min.uvl"


@pytest.fixture(autouse=True)
def _ensure_warmed():
    FlamapyService.warm_up(FIXTURE_PATH)


@pytest.mark.django_db
class TestFeatureModelEndpoint:
    def test_get_feature_model_returns_tree(self, tecnico_client):
        response = tecnico_client.get("/api/v1/configurator/model")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Entrada"
        assert "relations" in data
        assert "constraints" in data


@pytest.mark.django_db
class TestValidateFeatures:
    def test_valid_full_config_returns_valid_true(self, tecnico_client):
        anon_client = tecnico_client
        payload = {
            "features": [
                "Entrada", "DatosParcela",
                "Tratamiento", "Secano",
                "TipoSuelo", "Vertisoles",
                "ParametrosEntrada", "Dendrometro", "DatoMCD",
                "DatosTelemetria", "Nubes",
                "VariableObjetivo", "MCD",
            ],
            "is_full": True,
            "step": "full",
        }
        response = anon_client.post("/api/v1/configurator/validate-features", payload, format="json")
        assert response.status_code == 200
        assert response.json()["valid"] is True

    def test_invalid_config_returns_errors(self, tecnico_client):
        anon_client = tecnico_client
        payload = {
            "features": [
                "Entrada", "DatosParcela",
                "Tratamiento", "Secano",
                "TipoSuelo", "Vertisoles",
                "ParametrosEntrada", "Dendrometro", "DatoTB",
                "DatosTelemetria", "Nubes",
                "VariableObjetivo", "MCD",  # MCD without DatoMCD
            ],
            "is_full": True,
            "step": "full",
        }
        response = anon_client.post("/api/v1/configurator/validate-features", payload, format="json")
        assert response.status_code == 200
        assert response.json()["valid"] is False
        assert response.json()["errors"]

    def test_missing_features_field_returns_400(self, tecnico_client):
        response = tecnico_client.post("/api/v1/configurator/validate-features", {}, format="json")
        assert response.status_code in (400, 422)

    def test_invalid_step_returns_400(self, tecnico_client):
        response = tecnico_client.post(
            "/api/v1/configurator/validate-features",
            {"features": [], "is_full": False, "step": "no-such-step"},
            format="json",
        )
        assert response.status_code in (400, 422)


@pytest.mark.django_db
class TestFlamapyEndpoints:
    def test_satisfiable_endpoint(self, tecnico_client):
        response = tecnico_client.post("/api/v1/configurator/flamapy/satisfiable", {}, format="json")
        assert response.status_code == 200
        assert response.json()["satisfiable"] is True

    def test_configurations_number_endpoint(self, tecnico_client):
        response = tecnico_client.post(
            "/api/v1/configurator/flamapy/configurations-number", {}, format="json"
        )
        assert response.status_code == 200
        assert response.json()["configurationsNumber"] > 0

    def test_dead_features_endpoint(self, tecnico_client):
        response = tecnico_client.post("/api/v1/configurator/flamapy/dead-features", {}, format="json")
        assert response.status_code == 200
        assert isinstance(response.json()["deadFeatures"], list)


@pytest.mark.django_db
class TestConfiguracionCRUD:
    def test_tecnico_can_create_and_list_own(self, tecnico_client):
        payload = {"nombre": "mi parcela", "features": ["Secano"], "geo": {"lat": 37, "lng": -5}}
        post = tecnico_client.post("/api/v1/configurator/configuraciones/", payload, format="json")
        assert post.status_code == 201

        listing = tecnico_client.get("/api/v1/configurator/configuraciones/")
        assert listing.status_code == 200
        assert len(listing.json()) == 1

    def test_tecnico_cannot_see_others_configs(self, tecnico_client, admin_user):
        Configuracion.objects.create(user=admin_user, nombre="admin cfg", features=[], geo={})
        listing = tecnico_client.get("/api/v1/configurator/configuraciones/")
        assert listing.status_code == 200
        # admin's config not returned
        assert all(c["nombre"] != "admin cfg" for c in listing.json())

    def test_admin_sees_all_configs(self, admin_client, tecnico_user):
        Configuracion.objects.create(user=tecnico_user, nombre="t-cfg", features=[], geo={})
        listing = admin_client.get("/api/v1/configurator/configuraciones/")
        names = [c["nombre"] for c in listing.json()]
        assert "t-cfg" in names

    def test_tecnico_cannot_delete_others_config(self, tecnico_client, admin_user):
        cfg = Configuracion.objects.create(user=admin_user, nombre="x", features=[], geo={})
        response = tecnico_client.delete(f"/api/v1/configurator/configuraciones/{cfg.pk}/")
        assert response.status_code == 403

    def test_owner_can_delete_own_config(self, tecnico_user, tecnico_client):
        cfg = Configuracion.objects.create(user=tecnico_user, nombre="my", features=[], geo={})
        response = tecnico_client.delete(f"/api/v1/configurator/configuraciones/{cfg.pk}/")
        assert response.status_code == 204
        assert not Configuracion.objects.filter(pk=cfg.pk).exists()

    def test_anon_cannot_list_configs(self, anon_client):
        response = anon_client.get("/api/v1/configurator/configuraciones/")
        assert response.status_code in (401, 403)


@pytest.mark.django_db
class TestUVLVersionEndpoints:
    def _create_version(self, settings, tmp_path, admin_user):
        settings.UVL_VERSIONS_PATH = tmp_path
        text = FIXTURE_PATH.read_text(encoding="utf-8")
        fname = "extra.uvl"
        (tmp_path / fname).write_text(text, encoding="utf-8")
        return UVLVersion.objects.create(
            name="extra", description="", file_path=fname,
            file_hash=_sha256(text) + "extra",
            author=admin_user, is_active=False, is_valid=True, validation_errors=[],
        )

    def test_list_versions_requires_admin(self, tecnico_client):
        assert tecnico_client.get("/api/v1/uvl/versions/").status_code == 403

    def test_admin_can_list_versions(self, admin_client):
        response = admin_client.get("/api/v1/uvl/versions/")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_cannot_delete_active_version(self, admin_client, settings, tmp_path, admin_user):
        version = self._create_version(settings, tmp_path, admin_user)
        version.is_active = True
        version.save()
        response = admin_client.delete(f"/api/v1/uvl/versions/{version.pk}/")
        assert response.status_code == 409

    def test_validate_endpoint_reports_invalid_tree(self, admin_client):
        bad_tree = {"name": "Lonely", "relations": []}
        response = admin_client.post(
            "/api/v1/uvl/versions/validate/",
            {"tree": bad_tree, "constraints_text": ""},
            format="json",
        )
        assert response.status_code == 200
        body = response.json()
        assert body["valid"] is False
        assert body["errors"]
