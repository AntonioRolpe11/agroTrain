from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.mark.django_db
class TestExtractEndpoint:
    def _payload(self, **overrides):
        # Full valid configuration so FlamapyService.validate_features passes
        base = {
            "features": [
                "Entrada", "DatosParcela",
                "Tratamiento", "Secano",
                "TipoSuelo", "Vertisoles",
                "ParametrosEntrada", "Dendrometro", "DatoMCD",
                "DatosTelemetria", "Nubes", "NDVI",
                "VariableObjetivo", "MCD",
            ],
            "punto": {"lat": 37.5, "lng": -5.5},
            "cloudThreshold": 20.0,
            "startDate": "2026-03-01",
            "endDate": "2026-04-01",
        }
        base.update(overrides)
        return base

    def test_requires_authentication(self, anon_client):
        response = anon_client.post("/api/v1/telemetry/extract", self._payload(), format="json")
        assert response.status_code in (401, 403)

    def test_invalid_payload_returns_400(self, tecnico_client):
        response = tecnico_client.post(
            "/api/v1/telemetry/extract",
            {"features": ["NDVI"], "punto": {"lat": 99, "lng": 99}, "startDate": "2026-03-01", "endDate": "2026-04-01"},
            format="json",
        )
        assert response.status_code in (400, 422)

    def test_service_error_propagated_with_success_false(self, tecnico_client):
        from apps.telemetria.services.telemetry_service import TelemetryServiceError

        with patch(
            "apps.telemetria.views.telemetry_service.extract",
            side_effect=TelemetryServiceError("ee misconfigured"),
        ):
            response = tecnico_client.post(
                "/api/v1/telemetry/extract", self._payload(), format="json"
            )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert any("ee misconfigured" in err for err in data["errors"])

    def test_features_invalid_returns_success_false(self, tecnico_client):
        # MCD target without DatoMCD violates UVL constraint → view returns success=False
        response = tecnico_client.post(
            "/api/v1/telemetry/extract",
            self._payload(features=["DatosTelemetria", "NDVI", "VariableObjetivo", "MCD"]),
            format="json",
        )
        assert response.status_code == 200
        assert response.json()["success"] is False

    def test_returns_telemetry_when_service_succeeds(self, tecnico_client):
        fake_result = {
            "success": True,
            "errors": [],
            "collection": "S2",
            "indices": ["NDVI"],
            "startDate": "2026-03-01",
            "endDate": "2026-04-01",
            "imageCount": 1,
            "points": [{"date": "2026-03-10", "values": {"NDVI": 0.5}, "cloudCover": 5.0}],
        }
        with patch(
            "apps.telemetria.views.telemetry_service.extract",
            return_value=fake_result,
        ):
            response = tecnico_client.post(
                "/api/v1/telemetry/extract", self._payload(), format="json"
            )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["imageCount"] == 1
        assert data["points"][0]["values"]["NDVI"] == 0.5
