from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .serializers import (
    MunicipioOptionSerializer,
    MunicipioViewportResponseSerializer,
    ProvinciaOptionSerializer,
)
from .services.geo_service import GeoCatalogError, GeoService

geo_service = GeoService()


def _validate_serializer(serializer_class, data):
    serializer = serializer_class(data=data)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


def _error(message: str, status_code: int) -> Response:
    return Response({"detail": message}, status=status_code)


@extend_schema(responses={200: ProvinciaOptionSerializer(many=True)})
@api_view(["GET"])
def get_provincias(_request):
    return Response(geo_service.get_provincias())


@extend_schema(responses={200: MunicipioOptionSerializer(many=True)})
@api_view(["GET"])
def get_municipios(request):
    provincia = request.query_params.get("provincia_id")
    if not provincia:
        return _error("Debes indicar provincia_id.", 422)
    try:
        return Response(geo_service.get_municipios(provincia))
    except GeoCatalogError as exc:
        return _error(str(exc), 502)


@extend_schema(responses={200: MunicipioViewportResponseSerializer})
@api_view(["GET"])
def get_municipio_viewport(request):
    provincia_id = request.query_params.get("provincia_id")
    municipio_id = request.query_params.get("municipio_id")
    if not provincia_id or not municipio_id:
        return _error("Debes indicar provincia_id y municipio_id.", 422)
    try:
        return Response(geo_service.get_municipio_viewport(provincia_id=provincia_id, municipio_id=municipio_id))
    except GeoCatalogError as exc:
        return _error(str(exc), 502)


