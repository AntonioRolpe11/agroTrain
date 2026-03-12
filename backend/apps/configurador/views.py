from __future__ import annotations

from django.conf import settings
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.permissions import IsAdminRole, IsOwnerOrAdminRole

from .models import Configuracion, UVLVersion
from .serializers import (
    ActivateUVLVersionSerializer,
    ConfiguracionSerializer,
    ConfigurationsNumberResponseSerializer,
    CreateUVLVersionSerializer,
    DeadFeaturesResponseSerializer,
    SatisfiableResponseSerializer,
    UVLRequestSerializer,
    UVLVersionDetailSerializer,
    UVLVersionListSerializer,
    ValidateFeaturesRequestSerializer,
    ValidateResponseSerializer,
    ValidateUVLSerializer,
)
from .services.flamapy_service import FlamapyService
from .services.uvl_version_service import (
    activate_version,
    create_version,
    preview_activation,
    validate_uvl_text,
)
from .services.uvl_serializer import to_uvl

flamapy_service = FlamapyService(default_model_path=settings.UVL_MODEL_PATH)


def _validate_serializer(serializer_class, data):
    serializer = serializer_class(data=data)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


def _error(message: str, status_code: int) -> Response:
    return Response({"detail": message}, status=status_code)


# ------------------------------------------------------------------ existing flamapy endpoints

@extend_schema(request=ValidateFeaturesRequestSerializer, responses={200: ValidateResponseSerializer})
@api_view(["POST"])
def validate_features(request):
    payload = _validate_serializer(ValidateFeaturesRequestSerializer, request.data)
    try:
        valid, errors = flamapy_service.validate_features(
            payload["features"], payload["is_full"], payload["step"]
        )
    except Exception as exc:
        return _error(f"Error validando features con Flamapy: {exc}", 500)
    return Response({"valid": valid, "errors": errors})


@extend_schema(request=UVLRequestSerializer, responses={200: SatisfiableResponseSerializer})
@api_view(["POST"])
def satisfiable(request):
    payload = _validate_serializer(UVLRequestSerializer, request.data)
    try:
        return Response({"satisfiable": flamapy_service.satisfiable(payload.get("uvl"))})
    except Exception as exc:
        return _error(f"Error evaluando satisfiable: {exc}", 500)


@extend_schema(request=UVLRequestSerializer, responses={200: ConfigurationsNumberResponseSerializer})
@api_view(["POST"])
def configurations_number(request):
    payload = _validate_serializer(UVLRequestSerializer, request.data)
    try:
        return Response({"configurationsNumber": flamapy_service.configurations_number(payload.get("uvl"))})
    except Exception as exc:
        return _error(f"Error calculando número de configuraciones: {exc}", 500)


@extend_schema(request=UVLRequestSerializer, responses={200: DeadFeaturesResponseSerializer})
@api_view(["POST"])
def dead_features(request):
    payload = _validate_serializer(UVLRequestSerializer, request.data)
    try:
        return Response({"deadFeatures": flamapy_service.dead_features(payload.get("uvl"))})
    except Exception as exc:
        return _error(f"Error obteniendo dead features: {exc}", 500)


@extend_schema(responses={200: {"type": "object", "description": "Árbol del feature model UVL"}})
@api_view(["GET"])
def feature_model(request):
    try:
        return Response(flamapy_service.to_dict())
    except Exception as exc:
        return _error(f"Error obteniendo árbol del modelo: {exc}", 500)


# ------------------------------------------------------------------ configuraciones

@extend_schema(request=ConfiguracionSerializer, responses={200: ConfiguracionSerializer(many=True), 201: ConfiguracionSerializer})
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def configuracion_list_create(request):
    if request.method == "GET":
        qs = Configuracion.objects.all() if request.user.is_admin else Configuracion.objects.filter(user=request.user)
        return Response(ConfiguracionSerializer(qs, many=True).data)

    serializer = ConfiguracionSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    # Link to active UVL version
    active_version = UVLVersion.objects.filter(is_active=True).first()
    serializer.save(user=request.user, uvl_version=active_version)
    return Response(serializer.data, status=status.HTTP_201_CREATED)


@extend_schema(request=ConfiguracionSerializer, responses={200: ConfiguracionSerializer})
@api_view(["GET", "PUT", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def configuracion_detail(request, pk: int):
    configuracion = get_object_or_404(Configuracion, pk=pk)

    perm = IsOwnerOrAdminRole()
    if not perm.has_object_permission(request, None, configuracion):
        return Response({"detail": "No autorizado."}, status=status.HTTP_403_FORBIDDEN)

    if request.method == "GET":
        return Response(ConfiguracionSerializer(configuracion).data)

    if request.method == "DELETE":
        configuracion.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    partial = request.method == "PATCH"
    serializer = ConfiguracionSerializer(configuracion, data=request.data, partial=partial)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data)


# ------------------------------------------------------------------ UVL versioning (admin only)

@extend_schema(responses={200: UVLVersionListSerializer(many=True)})
@api_view(["GET"])
@permission_classes([IsAdminRole])
def uvl_version_list(request):
    versions = UVLVersion.objects.all()
    return Response(UVLVersionListSerializer(versions, many=True).data)


@extend_schema(responses={200: UVLVersionDetailSerializer})
@api_view(["GET", "DELETE"])
@permission_classes([IsAdminRole])
def uvl_version_detail_or_delete(request, pk: int):
    version = get_object_or_404(UVLVersion, pk=pk)

    if request.method == "GET":
        return Response(UVLVersionDetailSerializer(version).data)

    # DELETE
    if version.is_active:
        return _error("No se puede eliminar la versión activa.", 409)
    if UVLVersion.objects.count() <= 1:
        return _error("No se puede eliminar la única versión existente.", 409)

    from pathlib import Path
    uvl_file = Path(settings.UVL_VERSIONS_PATH) / version.file_path
    uvl_file.unlink(missing_ok=True)
    version.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(request=ValidateUVLSerializer, responses={200: ValidateResponseSerializer})
@api_view(["POST"])
@permission_classes([IsAdminRole])
def uvl_version_validate(request):
    payload = _validate_serializer(ValidateUVLSerializer, request.data)
    from .services.uvl_version_service import _build_uvl_from_tree_and_text
    uvl_text = _build_uvl_from_tree_and_text(payload["tree"], payload["constraints_text"])
    errors = validate_uvl_text(uvl_text)
    return Response({"valid": not errors, "errors": errors})


@extend_schema(request=CreateUVLVersionSerializer, responses={201: UVLVersionListSerializer})
@api_view(["POST"])
@permission_classes([IsAdminRole])
def uvl_version_create(request):
    payload = _validate_serializer(CreateUVLVersionSerializer, request.data)
    version, errors = create_version(
        name=payload["name"],
        description=payload["description"],
        tree=payload["tree"],
        constraints_text=payload["constraints_text"],
        author=request.user,
    )
    if errors:
        return Response({"detail": errors[0], "errors": errors}, status=status.HTTP_400_BAD_REQUEST)
    return Response(UVLVersionListSerializer(version).data, status=status.HTTP_201_CREATED)


@api_view(["GET"])
@permission_classes([IsAdminRole])
def uvl_version_preview_activation(request, pk: int):
    get_object_or_404(UVLVersion, pk=pk)
    try:
        report = preview_activation(pk)
    except Exception as exc:
        return _error(f"Error calculando preview: {exc}", 500)
    return Response(report)


@extend_schema(request=ActivateUVLVersionSerializer)
@api_view(["POST"])
@permission_classes([IsAdminRole])
def uvl_version_activate(request, pk: int):
    get_object_or_404(UVLVersion, pk=pk)
    payload = _validate_serializer(ActivateUVLVersionSerializer, request.data)
    success, error_msg, report = activate_version(
        version_id=pk,
        confirm_incompatible=payload["confirm_incompatible"],
    )
    if not success:
        resp = {"detail": error_msg}
        if report:
            resp["report"] = report
        return Response(resp, status=status.HTTP_409_CONFLICT)
    return Response({"detail": "Versión activada correctamente.", "report": report})
