from __future__ import annotations

import io
import json
import zipfile

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APIClient

from apps.accounts.models import ROLE_ADMIN, ROLE_TECNICO, CustomUser
from apps.modelos.services.training_service import _lock, _registry


def _user(email: str, role: str):
    return CustomUser.objects.create_user(email=email, password="x", nombre=email, role=role)


def _zip_with(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


def _metadata(*, user_id: int | None = None) -> str:
    payload = {
            "algorithm": "RandomForest",
            "treatment": "Secano",
            "features": ["Secano", "DatoMCD"],
            "targets": ["MCD"],
            "input_features": [],
            "all_cols": ["MCD"],
            "metrics": {},
            "warnings": [],
            "n_samples": 10,
            "n_train": 8,
            "n_val": 2,
            "window_size": 2,
            "geo": {"punto": {"lat": 37.1, "lng": -5.9}},
    }
    if user_id is not None:
        payload["user_id"] = user_id
    return json.dumps(payload)


@pytest.mark.django_db
def test_import_model_requires_admin(tmp_path):
    client = APIClient()
    client.force_authenticate(_user("tech@example.com", ROLE_TECNICO))
    payload = _zip_with({"metadata.json": _metadata()})

    with override_settings(MODELS_STORAGE_PATH=tmp_path):
        response = client.post(
            "/api/v1/modelos/import",
            {"zip_file": SimpleUploadedFile("model.zip", payload, content_type="application/zip")},
            format="multipart",
        )

    assert response.status_code == 403


@pytest.mark.django_db
def test_import_model_rejects_zipslip(tmp_path):
    client = APIClient()
    client.force_authenticate(_user("admin@example.com", ROLE_ADMIN))
    payload = _zip_with({"metadata.json": _metadata(), "../escape.txt": "bad"})

    with override_settings(MODELS_STORAGE_PATH=tmp_path):
        response = client.post(
            "/api/v1/modelos/import",
            {"zip_file": SimpleUploadedFile("model.zip", payload, content_type="application/zip")},
            format="multipart",
        )

    assert response.status_code == 400
    assert not (tmp_path.parent / "escape.txt").exists()


@pytest.mark.django_db
def test_training_status_requires_owner():
    owner = _user("owner@example.com", ROLE_TECNICO)
    other = _user("other@example.com", ROLE_TECNICO)
    model_id = "00000000-0000-0000-0000-000000000001"
    with _lock:
        _registry[model_id] = {"status": "training", "phase": "entrenando", "user_id": owner.pk}

    client = APIClient()
    client.force_authenticate(other)
    try:
        response = client.get(f"/api/v1/modelos/{model_id}/status")
    finally:
        with _lock:
            _registry.pop(model_id, None)

    assert response.status_code == 403


@pytest.mark.django_db
def test_legacy_model_detail_requires_admin(tmp_path):
    model_id = "legacy-model"
    model_dir = tmp_path / model_id
    model_dir.mkdir()
    (model_dir / "metadata.json").write_text(_metadata(), encoding="utf-8")

    client = APIClient()
    client.force_authenticate(_user("tech2@example.com", ROLE_TECNICO))

    with override_settings(MODELS_STORAGE_PATH=tmp_path):
        response = client.get(f"/api/v1/modelos/{model_id}/")

    assert response.status_code == 403


@pytest.mark.django_db
def test_legacy_model_detail_allows_metadata_owner(tmp_path):
    owner = _user("legacy-owner@example.com", ROLE_TECNICO)
    model_id = "legacy-owned-model"
    model_dir = tmp_path / model_id
    model_dir.mkdir()
    (model_dir / "metadata.json").write_text(_metadata(user_id=owner.pk), encoding="utf-8")

    client = APIClient()
    client.force_authenticate(owner)

    with override_settings(MODELS_STORAGE_PATH=tmp_path):
        response = client.get(f"/api/v1/modelos/{model_id}/")

    assert response.status_code == 200
