from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from apps.telemetria.services.telemetry_service import (
    TelemetryRequest,
    TelemetryService,
    TelemetryServiceError,
)


def _make_request(**overrides) -> TelemetryRequest:
    defaults = dict(
        lat=37.5,
        lng=-5.5,
        indices=["NDVI"],
        start_date=date(2026, 3, 1),
        end_date=date(2026, 4, 1),
        cloud_threshold=20.0,
    )
    defaults.update(overrides)
    return TelemetryRequest(**defaults)


class TestValidation:
    def test_rejects_empty_indices(self):
        svc = TelemetryService()
        with pytest.raises(TelemetryServiceError, match="índice"):
            svc.extract(_make_request(indices=[]))

    def test_rejects_missing_lat_lng(self):
        svc = TelemetryService()
        with pytest.raises(TelemetryServiceError):
            svc.extract(_make_request(lat=None))

    def test_rejects_inverted_dates(self):
        svc = TelemetryService()
        with pytest.raises(TelemetryServiceError, match="anterior"):
            svc.extract(_make_request(start_date=date(2026, 4, 1), end_date=date(2026, 3, 1)))

    def test_rejects_oversized_range(self):
        svc = TelemetryService()
        with pytest.raises(TelemetryServiceError, match="730"):
            svc.extract(_make_request(start_date=date(2020, 1, 1), end_date=date(2026, 1, 1)))


class TestExtraction:
    def test_empty_collection_returns_zero_points(self):
        """If no images match, the service returns success=True with no points."""
        svc = TelemetryService()
        svc._initialized = True  # skip real ee initialisation

        fake_collection = MagicMock()
        fake_collection.size.return_value.getInfo.return_value = 0

        with patch("apps.telemetria.services.telemetry_service.ee") as ee_mock:
            ee_mock.ImageCollection.return_value = fake_collection
            fake_collection.filterBounds.return_value = fake_collection
            fake_collection.filterDate.return_value = fake_collection
            fake_collection.filter.return_value = fake_collection
            fake_collection.map.return_value = fake_collection
            ee_mock.Geometry.Point.return_value.buffer.return_value = MagicMock()

            response = svc.extract(_make_request())

        assert response["success"] is True
        assert response["imageCount"] == 0
        assert response["points"] == []

    def test_extraction_returns_indexed_points(self):
        """When ee returns features, the service must round and surface them."""
        svc = TelemetryService()
        svc._initialized = True

        fake_collection = MagicMock()
        fake_collection.size.return_value.getInfo.return_value = 2

        fake_features = {
            "features": [
                {
                    "properties": {
                        "date": "2026-03-15",
                        "NDVI": 0.6543219,
                        "cloud_cover": 12.345,
                    }
                },
                {
                    "properties": {
                        "date": "2026-03-20",
                        "NDVI": 0.4123456,
                        "cloud_cover": 8.0,
                    }
                },
            ]
        }

        with patch("apps.telemetria.services.telemetry_service.ee") as ee_mock:
            ee_mock.ImageCollection.return_value = fake_collection
            fake_collection.filterBounds.return_value = fake_collection
            fake_collection.filterDate.return_value = fake_collection
            fake_collection.filter.return_value = fake_collection
            fake_collection.map.return_value = fake_collection
            ee_mock.Geometry.Point.return_value.buffer.return_value = MagicMock()
            fake_fc = MagicMock()
            fake_fc.getInfo.return_value = fake_features
            ee_mock.FeatureCollection.return_value = fake_fc

            response = svc.extract(_make_request())

        assert response["success"] is True
        assert response["imageCount"] == 2
        assert len(response["points"]) == 2
        assert response["points"][0]["values"]["NDVI"] == pytest.approx(0.654322, rel=1e-3)
        assert response["points"][0]["cloudCover"] == pytest.approx(12.345)
        assert response["indices"] == ["NDVI"]


class TestInitializeEE:
    def test_raises_when_credentials_missing(self, monkeypatch):
        svc = TelemetryService()
        # Reset
        svc._initialized = False
        monkeypatch.delenv("EE_SERVICE_ACCOUNT", raising=False)
        monkeypatch.delenv("EE_PRIVATE_KEY_FILE", raising=False)

        with patch("apps.telemetria.services.telemetry_service.ee", MagicMock()):
            with pytest.raises(TelemetryServiceError, match="EE_SERVICE_ACCOUNT"):
                svc._initialize_ee()

    def test_raises_when_credentials_file_missing(self, monkeypatch):
        svc = TelemetryService()
        svc._initialized = False
        monkeypatch.setenv("EE_SERVICE_ACCOUNT", "x@y.com")
        monkeypatch.setenv("EE_PRIVATE_KEY_FILE", "/nonexistent/file.json")

        with patch("apps.telemetria.services.telemetry_service.ee", MagicMock()):
            with pytest.raises(TelemetryServiceError, match="EE_PRIVATE_KEY_FILE"):
                svc._initialize_ee()
