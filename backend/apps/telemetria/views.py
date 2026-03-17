from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .serializers import TelemetryExtractRequestSerializer, TelemetryExtractResponseSerializer
from .services.telemetry_service import TelemetryRequest, TelemetryService, TelemetryServiceError

telemetry_service = TelemetryService()

_TELEMETRY_INDEX_NAMES: frozenset[str] = frozenset(["NDVI", "EVI", "SAVI", "NDWI"])


def _validate_serializer(serializer_class, data):
    serializer = serializer_class(data=data)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


@extend_schema(
    request=TelemetryExtractRequestSerializer,
    responses={200: TelemetryExtractResponseSerializer},
)
@api_view(["POST"])
def extract_telemetry(request):
    payload = _validate_serializer(TelemetryExtractRequestSerializer, request.data)
    features: list[str] = payload["features"]
    indices = [f for f in features if f in _TELEMETRY_INDEX_NAMES]
    punto = payload.get("punto") or {}
    try:
        return Response(
            telemetry_service.extract(
                TelemetryRequest(
                    lat=punto.get("lat"),
                    lng=punto.get("lng"),
                    indices=indices,
                    start_date=payload["startDate"],
                    end_date=payload["endDate"],
                    cloud_threshold=payload["cloudThreshold"],
                )
            )
        )
    except TelemetryServiceError as exc:
        return Response({"success": False, "errors": [str(exc)], "indices": indices})
    except Exception as exc:
        return Response({"detail": f"Error extrayendo telemetría: {exc}"}, status=500)
