from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

try:
    import ee  # type: ignore
except ImportError:  # pragma: no cover
    ee = None


class TelemetryServiceError(RuntimeError):
    pass


@dataclass(slots=True)
class TelemetryRequest:
    lat: float
    lng: float
    indices: list[str]
    start_date: date
    end_date: date
    cloud_threshold: float


class TelemetryService:
    DATASET_ID = "COPERNICUS/S2_SR_HARMONIZED"
    REFLECTANCE_SCALE = 10000
    CLOUD_BIT_MASK = 1 << 10
    CIRRUS_BIT_MASK = 1 << 11
    REDUCE_SCALE = 10  # resolución espacial Sentinel-2 10m (B2, B3, B4, B8)

    def __init__(self) -> None:
        self._initialized = False

    def extract(self, request: TelemetryRequest) -> dict[str, Any]:
        if not request.indices:
            raise TelemetryServiceError("Debes seleccionar al menos un índice de telemetría.")
        if request.lat is None or request.lng is None:
            raise TelemetryServiceError("La configuración no incluye la ubicación del árbol.")
        if request.start_date > request.end_date:
            raise TelemetryServiceError("La fecha inicial no puede ser posterior a la fecha final.")

        self._initialize_ee()

        if ee is None:  # pragma: no cover
            raise TelemetryServiceError("La librería de Google Earth Engine no está disponible en el backend.")

        geometry = self._build_geometry(request.lat, request.lng)
        end_date_exclusive = request.end_date + timedelta(days=1)

        collection = (
            ee.ImageCollection(self.DATASET_ID)
            .filterBounds(geometry)
            .filterDate(request.start_date.isoformat(), end_date_exclusive.isoformat())
            .filter(ee.Filter.lte("CLOUDY_PIXEL_PERCENTAGE", request.cloud_threshold))
            .map(lambda image: self._add_requested_indices(self._prepare_image(image), request.indices))
        )

        image_count = int(collection.size().getInfo())
        logger.debug("Telemetry collection: %d images for indices %s", image_count, request.indices)

        if image_count == 0:
            return self._empty_response(request)

        features = ee.FeatureCollection(
            collection.map(lambda image: self._feature_from_image(image, geometry, request.indices))
        )
        payload = features.getInfo()
        raw_features = payload.get("features", []) if isinstance(payload, dict) else []

        points: list[dict[str, Any]] = []
        for feature in raw_features:
            if not isinstance(feature, dict):
                continue
            properties = feature.get("properties", {})
            if not isinstance(properties, dict):
                continue
            point_date = properties.get("date")
            if not isinstance(point_date, str):
                continue

            values: dict[str, float] = {}
            for index_name in request.indices:
                value = properties.get(index_name)
                if isinstance(value, (int, float)):
                    values[index_name] = round(float(value), 6)

            cloud_cover_raw = properties.get("cloud_cover")
            cloud_cover = round(float(cloud_cover_raw), 3) if isinstance(cloud_cover_raw, (int, float)) else None
            if values:
                points.append({"date": point_date, "values": values, "cloudCover": cloud_cover})

        return {
            "success": True,
            "errors": [],
            "collection": self.DATASET_ID,
            "indices": request.indices,
            "startDate": request.start_date.isoformat(),
            "endDate": request.end_date.isoformat(),
            "imageCount": image_count,
            "points": points,
        }

    def _empty_response(self, request: TelemetryRequest) -> dict[str, Any]:
        return {
            "success": True,
            "errors": [],
            "collection": self.DATASET_ID,
            "indices": request.indices,
            "startDate": request.start_date.isoformat(),
            "endDate": request.end_date.isoformat(),
            "imageCount": 0,
            "points": [],
        }

    @staticmethod
    def _build_geometry(lat: float, lng: float) -> Any:
        if ee is None:  # pragma: no cover
            raise TelemetryServiceError("La librería de Google Earth Engine no está disponible en el backend.")

        try:
            return ee.Geometry.Point([lng, lat]).buffer(50)
        except Exception as exc:
            raise TelemetryServiceError(
                f"No se pudo construir la geometría del punto en Earth Engine: {exc}"
            ) from exc

    def _initialize_ee(self) -> None:
        if self._initialized:
            return

        if ee is None:
            raise TelemetryServiceError(
                "earthengine-api no está instalado. Ejecuta: pip install -r backend/requirements/base.txt"
            )

        service_account = os.getenv("EE_SERVICE_ACCOUNT")
        credentials_file = os.getenv("EE_PRIVATE_KEY_FILE")
        project_id = os.getenv("EE_PROJECT")

        if not service_account or not credentials_file:
            raise TelemetryServiceError(
                "Falta configurar Google Earth Engine. "
                "Define EE_SERVICE_ACCOUNT y EE_PRIVATE_KEY_FILE en el entorno del backend."
            )

        if not os.path.exists(credentials_file):
            raise TelemetryServiceError("No se encontró el fichero indicado en EE_PRIVATE_KEY_FILE.")

        try:
            credentials = ee.ServiceAccountCredentials(service_account, credentials_file)
            if project_id:
                ee.Initialize(credentials, project=project_id)
            else:
                ee.Initialize(credentials)
        except Exception as exc:  # pragma: no cover
            raise TelemetryServiceError(f"No se pudo inicializar Google Earth Engine: {exc}") from exc

        self._initialized = True
        logger.info("Google Earth Engine inicializado (account=%s, project=%s)", service_account, project_id or "default")

    def _prepare_image(self, image: Any) -> Any:
        image = ee.Image(image)
        qa = image.select("QA60")
        mask = (
            qa.bitwiseAnd(self.CLOUD_BIT_MASK).eq(0)
            .And(qa.bitwiseAnd(self.CIRRUS_BIT_MASK).eq(0))
        )
        prepared = image.updateMask(mask).divide(self.REFLECTANCE_SCALE)
        return prepared.copyProperties(image, ["system:time_start", "CLOUDY_PIXEL_PERCENTAGE"])

    @staticmethod
    def _add_requested_indices(image: Any, indices: list[str]) -> Any:
        image = ee.Image(image)
        enriched = image
        for index_name in indices:
            if index_name == "NDVI":
                enriched = enriched.addBands(image.normalizedDifference(["B8", "B4"]).rename("NDVI"))
            elif index_name == "EVI":
                evi = image.expression(
                    "2.5 * ((NIR - RED) / (NIR + 6 * RED - 7.5 * BLUE + 1))",
                    {"NIR": image.select("B8"), "RED": image.select("B4"), "BLUE": image.select("B2")},
                ).rename("EVI")
                enriched = enriched.addBands(evi)
            elif index_name == "SAVI":
                savi = image.expression(
                    "1.5 * ((NIR - RED) / (NIR + RED + 0.5))",
                    {"NIR": image.select("B8"), "RED": image.select("B4")},
                ).rename("SAVI")
                enriched = enriched.addBands(savi)
            elif index_name == "NDWI":
                enriched = enriched.addBands(image.normalizedDifference(["B3", "B8"]).rename("NDWI"))
        return enriched

    @staticmethod
    def _feature_from_image(image: Any, geometry: Any, indices: list[str]) -> Any:
        image = ee.Image(image)
        stats = image.select(indices).reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=geometry,
            scale=TelemetryService.REDUCE_SCALE,
            bestEffort=True,
            maxPixels=1_000_000_000,
        )
        properties = (
            stats
            .set("date", image.date().format("YYYY-MM-dd"))
            .set("cloud_cover", image.get("CLOUDY_PIXEL_PERCENTAGE"))
        )
        return ee.Feature(None, properties)
