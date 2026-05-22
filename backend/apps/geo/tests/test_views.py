from __future__ import annotations

from unittest.mock import patch

import pytest

from apps.geo.services.geo_service import GeoService


@pytest.mark.django_db
class TestGeoEndpoints:
    def test_provincias_returns_list(self, tecnico_client):
        response = tecnico_client.get("/api/v1/geo/provincias")
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 52
        assert all("id" in p and "nombre" in p for p in body)

    def test_municipios_requires_provincia_id(self, tecnico_client):
        response = tecnico_client.get("/api/v1/geo/municipios")
        assert response.status_code == 422

    def test_municipios_returns_list(self, tecnico_client):
        response = tecnico_client.get("/api/v1/geo/municipios?provincia_id=41")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_viewport_requires_params(self, tecnico_client):
        assert tecnico_client.get("/api/v1/geo/municipio-viewport").status_code == 422

    def test_viewport_returns_data_when_found(self, tecnico_client):
        munis = GeoService().get_municipios("41")
        if not munis:
            pytest.skip("No municipios data")
        target = munis[0]
        fake = {"bbox": (-5.0, 37.0, -4.0, 38.0), "centroid": (-4.5, 37.5)}
        with patch.object(GeoService, "_geocode_municipio_bounds", staticmethod(lambda *_: fake)):
            response = tecnico_client.get(
                f"/api/v1/geo/municipio-viewport?provincia_id=41&municipio_id={target['id']}"
            )
        assert response.status_code == 200
        assert response.json()["found"] is True
