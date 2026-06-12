from __future__ import annotations

from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.configurador.services.flamapy_service import FlamapyService

from .serializers import TelemetryExtractRequestSerializer, TelemetryExtractResponseSerializer
from .services.telemetry_service import TelemetryRequest, TelemetryService, TelemetryServiceError

telemetry_service = TelemetryService()

def _get_telemetry_index_names() -> frozenset[str]:
    return frozenset(
        name
        for name in FlamapyService.get_subtree_feature_names("DatosTelemetria")
        if FlamapyService.get_csv_columns(name)
    )


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
    try:
        valid, errors = FlamapyService(settings.UVL_MODEL_PATH).validate_features(features, is_full=False, step="telemetry")
    except Exception as exc:
        return Response({"success": False, "errors": [f"Error validando features: {exc}"], "indices": []})
    if not valid:
        return Response({"success": False, "errors": errors, "indices": []})

    indices = [f for f in features if f in _get_telemetry_index_names()]
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
