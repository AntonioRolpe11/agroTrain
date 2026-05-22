from __future__ import annotations

from unittest.mock import patch

import pytest

from apps.geo.services.geo_service import GeoCatalogError, GeoService


class TestProvincias:
    def test_returns_full_list(self):
        provincias = GeoService().get_provincias()
        assert len(provincias) == 52  # 50 provincias + Ceuta + Melilla
        assert all("id" in p and "nombre" in p for p in provincias)

    def test_known_ids_present(self):
        ids = {p["id"] for p in GeoService().get_provincias()}
        assert "41" in ids  # Sevilla
        assert "23" in ids  # Jaen
        assert "11" in ids  # Cadiz


class TestMunicipios:
    def test_returns_municipios_for_known_provincia(self):
        result = GeoService().get_municipios("41")
        assert len(result) > 0
        assert all(m["provinciaId"] == "41" for m in result)

    def test_unknown_provincia_returns_empty(self):
        # No raise, returns empty list (the data file has no entries for 99)
        result = GeoService().get_municipios("99")
        assert result == []

    def test_results_sorted_alphabetically(self):
        result = GeoService().get_municipios("23")
        names = [m["nombre"] for m in result]
        assert names == sorted(names, key=lambda n: n.casefold())


class TestMunicipioViewport:
    def test_unknown_provincia_raises(self):
        with pytest.raises(GeoCatalogError):
            GeoService().get_municipio_viewport("99", "99999")

    def test_municipio_not_in_provincia_raises(self):
        # Find a municipio from a different provincia, but pass a wrong provincia_id
        munis_41 = GeoService().get_municipios("41")
        if not munis_41:
            pytest.skip("No municipios for provincia 41 in fixture data")
        # Use municipio from provincia 41 but request provincia 23
        with pytest.raises(GeoCatalogError):
            GeoService().get_municipio_viewport("23", munis_41[0]["id"])

    def test_returns_viewport_when_geocoding_succeeds(self):
        munis = GeoService().get_municipios("41")
        if not munis:
            pytest.skip("No municipios for provincia 41")
        target = munis[0]
        fake = {
            "bbox": (-5.0, 37.0, -4.0, 38.0),
            "centroid": (-4.5, 37.5),
        }
        with patch.object(GeoService, "_geocode_municipio_bounds", staticmethod(lambda *_: fake)):
            result = GeoService().get_municipio_viewport("41", target["id"])
        assert result["found"] is True
        assert result["bbox"] == fake["bbox"]
        assert result["centroid"] == fake["centroid"]

    def test_returns_not_found_when_geocoding_fails(self):
        munis = GeoService().get_municipios("41")
        if not munis:
            pytest.skip("No municipios for provincia 41")
        target = munis[0]
        with patch.object(GeoService, "_geocode_municipio_bounds", staticmethod(lambda *_: None)):
            result = GeoService().get_municipio_viewport("41", target["id"])
        assert result == {"found": False}
