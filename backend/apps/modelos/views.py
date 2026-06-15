from __future__ import annotations

import json
import logging

from django.http import HttpResponse
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.permissions import IsAdminRole, IsOwnerOrAdminRole
from apps.configurador.services.flamapy_service import FlamapyService

from .models import ModeloGuardado
from .models import PrediccionModelo
from .serializers import (
    ModelListResponseSerializer,
    ModelMetadataSerializer,
    PredictionHistoryResponseSerializer,
    PredictionResponseSerializer,
    TrainStartResponseSerializer,
    TrainingStatusSerializer,
)
from .services.prediction_service import PredictionService, PredictionServiceError
from .services.storage_service import StorageError, StorageService
from .services.training_service import ModelosServiceError, TrainingService, get_training_status

logger = logging.getLogger(__name__)

_training_service = TrainingService()
_storage_service = StorageService()
_prediction_service = PredictionService()


def _features_to_training_params(features: list[str]) -> tuple[list[str], list[str], str]:
    """Derives targets, input_cols, treatment purely from UVL attributes — no hardcoded mappings."""
    features_set = set(features)
    target_names = set(FlamapyService.get_subtree_feature_names("VariableObjetivo"))
    treatment_names = set(FlamapyService.get_subtree_feature_names("Tratamiento")) - {"Tratamiento"}

    targets = [f for f in features_set if f in target_names]

    seen: set[str] = set()
    input_cols: list[str] = []
    for feature_name in features_set:
        if feature_name in target_names or feature_name in treatment_names:
            continue
        for col in FlamapyService.get_csv_columns(feature_name):
            if col not in seen:
                seen.add(col)
                input_cols.append(col)

    treatment = next((f for f in features_set if f in treatment_names), "")
    return targets, input_cols, treatment


def _metadata_from_db(record: ModeloGuardado) -> dict:
    return {
        "model_id": record.model_id,
        "algorithm": record.algorithm,
        "treatment": record.treatment,
        "features": record.features,
        "geo": record.geo,
        "all_cols": record.all_cols,
        "targets": record.targets,
        "input_features": record.input_features,
        "window_size": record.window_size,
        "n_samples": record.n_samples,
        "n_train": record.n_train,
        "n_val": record.n_val,
        # Operativo (100% datos) no guarda métricas → se deduce el tipo de ahí (sin columna DB).
        "is_validation": bool(record.metrics),
        "metrics": record.metrics,
        "warnings": record.warnings,
        "imported": record.imported,
        "created_at": record.created_at.isoformat(),
    }


def _prediction_from_db(record: PrediccionModelo) -> dict:
    return {
        "prediction_id": record.id,
        "model_id": record.model.model_id,
        "generated_at": record.generated_at.isoformat(),
        "predicted_for_date": record.predicted_for_date,
        "predictions": record.predictions,
        "input_row_count": record.input_row_count,
        "warnings": record.warnings,
    }


def _get_authorized_model(request, model_id: str) -> ModeloGuardado | Response:
    try:
        record = ModeloGuardado.objects.get(model_id=model_id)
    except ModeloGuardado.DoesNotExist:
        return Response({"detail": "Modelo no encontrado."}, status=404)

    perm = IsOwnerOrAdminRole()
    if not perm.has_object_permission(request, None, record):
        return Response({"detail": "No autorizado."}, status=403)
    return record


def _legacy_metadata_allowed(request, metadata: dict) -> bool:
    if request.user.is_admin:
        return True
    return metadata.get("user_id") == request.user.pk


# ------------------------------------------------------------------ train

@extend_schema(
    request={"multipart/form-data": {"type": "object", "properties": {
        "features": {"type": "string", "description": "JSON array de features UVL seleccionadas"},
        "geo": {"type": "string", "description": "JSON con datos de parcela/ubicación"},
        "csv_file": {"type": "string", "format": "binary"},
    }}},
    responses={202: TrainStartResponseSerializer},
)
@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser])
@permission_classes([IsAuthenticated])
def train_model(request):
    features_json = request.data.get("features")
    geo_json = request.data.get("geo")
    csv_file = request.FILES.get("csv_file")

    if not features_json:
        return Response({"detail": "Falta el campo 'features'."}, status=400)
    if not csv_file:
        return Response({"detail": "Falta el archivo CSV ('csv_file')."}, status=400)

    try:
        features = json.loads(features_json)
        if not isinstance(features, list):
            raise ValueError
    except (json.JSONDecodeError, ValueError):
        return Response({"detail": "El campo 'features' debe ser un array JSON."}, status=400)

    geo: dict = {}
    if geo_json:
        try:
            geo = json.loads(geo_json)
            if not isinstance(geo, dict):
                raise ValueError
        except (json.JSONDecodeError, ValueError):
            return Response({"detail": "El campo 'geo' debe ser un objeto JSON."}, status=400)

    try:
        targets, input_cols, treatment = _features_to_training_params(features)
    except RuntimeError as exc:
        return Response({"detail": str(exc)}, status=503)

    csv_content = csv_file.read()

    # Tipo de sensor: validación (split 80/20 + métricas) vs operativo (100% datos, sin métricas).
    is_validation = request.data.get("is_validation", "true") != "false"

    try:
        model_id = _training_service.start_training(
            targets, input_cols, treatment, csv_content,
            features=features, geo=geo, user_id=request.user.pk, is_validation=is_validation,
        )
    except ModelosServiceError as exc:
        return Response({"detail": str(exc)}, status=400)

    return Response({"model_id": model_id, "status": "training"}, status=202)


# ------------------------------------------------------------------ status

@extend_schema(responses={200: TrainingStatusSerializer})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_status(request, model_id: str):
    entry = get_training_status(model_id)

    if entry is not None:
        if entry.get("user_id") != request.user.pk and not request.user.is_admin:
            return Response({"detail": "No autorizado."}, status=403)
        return Response(entry)

    try:
        record = ModeloGuardado.objects.get(model_id=model_id)
        perm = IsOwnerOrAdminRole()
        if not perm.has_object_permission(request, None, record):
            return Response({"detail": "No autorizado."}, status=403)
        return Response({"status": "completed", **_metadata_from_db(record)})
    except ModeloGuardado.DoesNotExist:
        pass

    # Fallback: lectura desde disco (modelos anteriores sin registro DB)
    try:
        metadata = _storage_service.load_metadata(model_id)
        if not _legacy_metadata_allowed(request, metadata):
            return Response({"detail": "No autorizado."}, status=403)
        return Response({"status": "completed", **metadata})
    except StorageError:
        return Response({"detail": "Modelo no encontrado."}, status=404)


# ------------------------------------------------------------------ list

@extend_schema(responses={200: ModelListResponseSerializer})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_models(request):
    if request.user.is_admin:
        records = ModeloGuardado.objects.all()
    else:
        records = ModeloGuardado.objects.filter(user=request.user)
    return Response({"models": [_metadata_from_db(r) for r in records]})


# ------------------------------------------------------------------ get / delete

@extend_schema(responses={200: ModelMetadataSerializer})
@api_view(["GET", "DELETE"])
@permission_classes([IsAuthenticated])
def model_detail(request, model_id: str):
    try:
        record = ModeloGuardado.objects.get(model_id=model_id)
    except ModeloGuardado.DoesNotExist:
        # Fallback: modelo sin registro DB. Admin o dueño si metadata conserva user_id.
        try:
            metadata = _storage_service.load_metadata(model_id)
        except StorageError as exc:
            return Response({"detail": str(exc)}, status=404)
        if not _legacy_metadata_allowed(request, metadata):
            return Response({"detail": "No autorizado."}, status=403)
        if request.method == "DELETE":
            try:
                _storage_service.delete_model(model_id)
                return Response(status=204)
            except StorageError as exc:
                return Response({"detail": str(exc)}, status=404)
        return Response(metadata)

    perm = IsOwnerOrAdminRole()
    if not perm.has_object_permission(request, None, record):
        return Response({"detail": "No autorizado."}, status=403)

    if request.method == "DELETE":
        try:
            _storage_service.delete_model(model_id)
        except StorageError:
            pass
        record.delete()
        return Response(status=204)

    return Response(_metadata_from_db(record))


# ------------------------------------------------------------------ download

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def download_model(request, model_id: str):
    try:
        record = ModeloGuardado.objects.get(model_id=model_id)
        perm = IsOwnerOrAdminRole()
        if not perm.has_object_permission(request, None, record):
            return Response({"detail": "No autorizado."}, status=403)
    except ModeloGuardado.DoesNotExist:
        try:
            metadata = _storage_service.load_metadata(model_id)
        except StorageError as exc:
            return Response({"detail": str(exc)}, status=404)
        if not _legacy_metadata_allowed(request, metadata):
            return Response({"detail": "No autorizado."}, status=403)

    try:
        zip_bytes = _storage_service.export_zip(model_id)
    except StorageError as exc:
        return Response({"detail": str(exc)}, status=404)

    response = HttpResponse(zip_bytes, content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="modelo_{model_id[:8]}.zip"'
    return response


# ------------------------------------------------------------------ import

@extend_schema(
    request={"multipart/form-data": {"type": "object", "properties": {
        "zip_file": {"type": "string", "format": "binary"},
    }}},
    responses={201: ModelMetadataSerializer},
)
@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser])
@permission_classes([IsAdminRole])
def import_model(request):
    zip_file = request.FILES.get("zip_file")
    if not zip_file:
        return Response({"detail": "Falta el archivo ZIP ('zip_file')."}, status=400)

    try:
        new_id = _storage_service.import_zip(zip_file.read())
        metadata = _storage_service.load_metadata(new_id)
    except StorageError as exc:
        return Response({"detail": str(exc)}, status=400)

    ModeloGuardado.objects.get_or_create(
        model_id=new_id,
        defaults={
            "user": request.user,
            "algorithm": metadata.get("algorithm", ""),
            "treatment": metadata.get("treatment") or metadata.get("crop", ""),
            "features": metadata.get("features", []),
            "geo": metadata.get("geo", {}),
            "targets": metadata.get("targets", []),
            "input_features": metadata.get("input_features", []),
            "all_cols": metadata.get("all_cols", []),
            "metrics": metadata.get("metrics", {}),
            "warnings": metadata.get("warnings", []),
            "n_samples": metadata.get("n_samples", 0),
            "n_train": metadata.get("n_train", 0),
            "n_val": metadata.get("n_val", 0),
            "window_size": metadata.get("window_size", 0),
            "imported": True,
        },
    )

    return Response(metadata, status=201)


# ------------------------------------------------------------------ predict

@extend_schema(
    request={"multipart/form-data": {"type": "object", "properties": {
        "csv_file": {"type": "string", "format": "binary"},
    }}},
    responses={201: PredictionResponseSerializer},
)
@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser])
@permission_classes([IsAuthenticated])
def predict_model(request, model_id: str):
    record_or_response = _get_authorized_model(request, model_id)
    if isinstance(record_or_response, Response):
        return record_or_response
    record = record_or_response

    csv_file = request.FILES.get("csv_file")
    if not csv_file:
        return Response({"detail": "Falta el archivo CSV ('csv_file')."}, status=400)
    if not record.geo or not isinstance(record.geo, dict) or not record.geo.get("punto"):
        return Response({"detail": "El modelo no tiene ubicación guardada para extraer telemetría GEE."}, status=400)

    try:
        result = _prediction_service.predict_one(model_id, csv_file.read())
    except (PredictionServiceError, StorageError) as exc:
        return Response({"detail": str(exc)}, status=400)

    predicted_for_date = result["predicted_for_date"]
    existing = PrediccionModelo.objects.filter(model=record, predicted_for_date=predicted_for_date).first()
    if existing:
        return Response(
            {
                "detail": f"Ya existe una predicción para el {predicted_for_date} en este modelo.",
                "existing_prediction_id": existing.id,
                "predicted_for_date": str(predicted_for_date),
            },
            status=409,
        )

    prediction = PrediccionModelo.objects.create(
        model=record,
        user=request.user,
        predicted_for_date=result["predicted_for_date"],
        predictions=result["predictions"],
        input_row_count=result["input_row_count"],
        warnings=result.get("warnings", []),
    )
    return Response(_prediction_from_db(prediction), status=201)


@extend_schema(responses={200: PredictionHistoryResponseSerializer})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_predictions(request, model_id: str):
    record_or_response = _get_authorized_model(request, model_id)
    if isinstance(record_or_response, Response):
        return record_or_response
    record = record_or_response

    predictions = PrediccionModelo.objects.filter(model=record)
    if not request.user.is_admin:
        predictions = predictions.filter(user=request.user)
    return Response({"predictions": [_prediction_from_db(p) for p in predictions]})


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_prediction(request, model_id: str, prediction_id: int):
    record_or_response = _get_authorized_model(request, model_id)
    if isinstance(record_or_response, Response):
        return record_or_response
    record = record_or_response

    predictions = PrediccionModelo.objects.filter(model=record, pk=prediction_id)
    if not request.user.is_admin:
        predictions = predictions.filter(user=request.user)

    prediction = predictions.first()
    if prediction is None:
        return Response({"detail": "Predicción no encontrada."}, status=404)

    prediction.delete()
    return Response(status=204)
