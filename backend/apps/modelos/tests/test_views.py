from __future__ import annotations

import json

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from apps.modelos.models import ModeloGuardado, PrediccionModelo
from apps.modelos.tests.conftest import csv_bytes, write_sklearn_model


@pytest.mark.django_db
class TestListModels:
    def test_tecnico_sees_only_own_models(self, tecnico_user, tecnico_client, admin_user):
        ModeloGuardado.objects.create(
            model_id="own", user=tecnico_user, algorithm="RF", treatment="S",
            targets=["MCD"], input_features=["tmax"], metrics={},
        )
        ModeloGuardado.objects.create(
            model_id="other", user=admin_user, algorithm="RF", treatment="S",
            targets=["MCD"], input_features=["tmax"], metrics={},
        )
        response = tecnico_client.get("/api/v1/modelos/")
        assert response.status_code == 200
        ids = [m["model_id"] for m in response.data["models"]]
        assert ids == ["own"]

    def test_admin_sees_all_models(self, admin_client, tecnico_user):
        ModeloGuardado.objects.create(
            model_id="t-model", user=tecnico_user, algorithm="RF", treatment="S",
            targets=["MCD"], input_features=[], metrics={},
        )
        response = admin_client.get("/api/v1/modelos/")
        ids = [m["model_id"] for m in response.data["models"]]
        assert "t-model" in ids

    def test_anonymous_cannot_list(self, anon_client):
        assert anon_client.get("/api/v1/modelos/").status_code in (401, 403)


@pytest.mark.django_db
class TestModelDetail:
    def test_owner_sees_metadata(self, tecnico_user, tecnico_client):
        m = ModeloGuardado.objects.create(
            model_id="o", user=tecnico_user, algorithm="RF", treatment="S",
            targets=["MCD"], input_features=[], metrics={},
        )
        response = tecnico_client.get(f"/api/v1/modelos/{m.model_id}/")
        assert response.status_code == 200
        assert response.data["algorithm"] == "RF"

    def test_other_tecnico_blocked(self, tecnico_client, admin_user):
        m = ModeloGuardado.objects.create(
            model_id="not-mine", user=admin_user, algorithm="RF", treatment="S",
            targets=["MCD"], input_features=[], metrics={},
        )
        response = tecnico_client.get(f"/api/v1/modelos/{m.model_id}/")
        assert response.status_code == 403

    def test_owner_can_delete(self, tecnico_user, tecnico_client, tmp_path):
        m = ModeloGuardado.objects.create(
            model_id="del", user=tecnico_user, algorithm="RF", treatment="S",
            targets=["MCD"], input_features=[], metrics={},
        )
        with override_settings(MODELS_STORAGE_PATH=tmp_path):
            response = tecnico_client.delete(f"/api/v1/modelos/{m.model_id}/")
        assert response.status_code == 204
        assert not ModeloGuardado.objects.filter(model_id="del").exists()


@pytest.mark.django_db
class TestTrainEndpoint:
    def test_missing_features_field_returns_400(self, tecnico_client):
        response = tecnico_client.post("/api/v1/modelos/train", {}, format="multipart")
        assert response.status_code == 400

    def test_missing_csv_file_returns_400(self, tecnico_client):
        response = tecnico_client.post(
            "/api/v1/modelos/train", {"features": "[]"}, format="multipart"
        )
        assert response.status_code == 400

    def test_features_must_be_array(self, tecnico_client):
        response = tecnico_client.post(
            "/api/v1/modelos/train",
            {
                "features": "{\"not\": \"array\"}",
                "csv_file": SimpleUploadedFile("x.csv", b"a,b", content_type="text/csv"),
            },
            format="multipart",
        )
        assert response.status_code == 400


@pytest.mark.django_db
class TestPredictEndpoint:
    def test_requires_csv(self, tecnico_user, tecnico_client, tmp_path):
        m = ModeloGuardado.objects.create(
            model_id="p1", user=tecnico_user, algorithm="RF", treatment="S",
            targets=["MCD"], input_features=["tmax"],
            geo={"punto": {"lat": 37.1, "lng": -5.9}}, metrics={},
        )
        with override_settings(MODELS_STORAGE_PATH=tmp_path):
            response = tecnico_client.post(
                f"/api/v1/modelos/{m.model_id}/predict", {}, format="multipart"
            )
        assert response.status_code == 400
        assert "csv_file" in response.data["detail"]

    def test_model_without_geo_blocked(self, tecnico_user, tecnico_client, tmp_path):
        m = ModeloGuardado.objects.create(
            model_id="no-geo", user=tecnico_user, algorithm="RF", treatment="S",
            targets=["MCD"], input_features=["tmax"], geo={}, metrics={},
        )
        with override_settings(MODELS_STORAGE_PATH=tmp_path):
            response = tecnico_client.post(
                f"/api/v1/modelos/{m.model_id}/predict",
                {"csv_file": SimpleUploadedFile("x.csv", csv_bytes(4), content_type="text/csv")},
                format="multipart",
            )
        assert response.status_code == 400
        assert "ubicación" in response.data["detail"]

    def test_prediction_persists_record(self, tecnico_user, tecnico_client, tmp_path):
        write_sklearn_model(tmp_path, "with-files", user_id=tecnico_user.pk)
        m = ModeloGuardado.objects.create(
            model_id="with-files", user=tecnico_user, algorithm="RandomForest",
            treatment="Secano", targets=["MCD"], input_features=["tmax"],
            all_cols=["MCD", "tmax"], window_size=2,
            geo={"punto": {"lat": 37.1, "lng": -5.9}}, metrics={},
        )
        with override_settings(MODELS_STORAGE_PATH=tmp_path):
            response = tecnico_client.post(
                f"/api/v1/modelos/{m.model_id}/predict",
                {"csv_file": SimpleUploadedFile("x.csv", csv_bytes(6), content_type="text/csv")},
                format="multipart",
            )
        assert response.status_code == 201
        assert PrediccionModelo.objects.filter(model=m).count() == 1
        assert "MCD" in response.data["predictions"]

    def test_duplicate_prediction_returns_409(self, tecnico_user, tecnico_client, tmp_path):
        write_sklearn_model(tmp_path, "dup", user_id=tecnico_user.pk)
        m = ModeloGuardado.objects.create(
            model_id="dup", user=tecnico_user, algorithm="RandomForest",
            treatment="Secano", targets=["MCD"], input_features=["tmax"],
            all_cols=["MCD", "tmax"], window_size=2,
            geo={"punto": {"lat": 37.1, "lng": -5.9}}, metrics={},
        )
        with override_settings(MODELS_STORAGE_PATH=tmp_path):
            tecnico_client.post(
                f"/api/v1/modelos/{m.model_id}/predict",
                {"csv_file": SimpleUploadedFile("x.csv", csv_bytes(6), content_type="text/csv")},
                format="multipart",
            )
            second = tecnico_client.post(
                f"/api/v1/modelos/{m.model_id}/predict",
                {"csv_file": SimpleUploadedFile("x.csv", csv_bytes(6), content_type="text/csv")},
                format="multipart",
            )
        assert second.status_code == 409


@pytest.mark.django_db
class TestPredictionHistory:
    def test_lists_predictions(self, tecnico_user, tecnico_client):
        m = ModeloGuardado.objects.create(
            model_id="ph", user=tecnico_user, algorithm="RF", treatment="S",
            targets=["MCD"], input_features=[], metrics={},
            geo={"punto": {"lat": 1, "lng": 1}},
        )
        PrediccionModelo.objects.create(
            model=m, user=tecnico_user, predicted_for_date="2026-04-30",
            predictions={"MCD": 1.0}, input_row_count=5, warnings=[],
        )
        response = tecnico_client.get(f"/api/v1/modelos/{m.model_id}/predictions")
        assert response.status_code == 200
        assert len(response.data["predictions"]) == 1


@pytest.mark.django_db
class TestDeletePrediction:
    def _model_with_prediction(self, owner, *, model_id="dp"):
        m = ModeloGuardado.objects.create(
            model_id=model_id, user=owner, algorithm="RF", treatment="S",
            targets=["MCD"], input_features=[], metrics={},
            geo={"punto": {"lat": 1, "lng": 1}},
        )
        p = PrediccionModelo.objects.create(
            model=m, user=owner, predicted_for_date="2026-04-30",
            predictions={"MCD": 1.0}, input_row_count=5, warnings=[],
        )
        return m, p

    def test_owner_can_delete(self, tecnico_user, tecnico_client):
        m, p = self._model_with_prediction(tecnico_user)
        response = tecnico_client.delete(f"/api/v1/modelos/{m.model_id}/predictions/{p.id}")
        assert response.status_code == 204
        assert not PrediccionModelo.objects.filter(pk=p.id).exists()

    def test_missing_prediction_returns_404(self, tecnico_user, tecnico_client):
        m, _ = self._model_with_prediction(tecnico_user)
        response = tecnico_client.delete(f"/api/v1/modelos/{m.model_id}/predictions/999999")
        assert response.status_code == 404

    def test_other_tecnico_blocked(self, tecnico_client, admin_user):
        m, p = self._model_with_prediction(admin_user, model_id="dp-foreign")
        response = tecnico_client.delete(f"/api/v1/modelos/{m.model_id}/predictions/{p.id}")
        assert response.status_code == 403
        assert PrediccionModelo.objects.filter(pk=p.id).exists()

    def test_admin_can_delete_any(self, tecnico_user, admin_client):
        m, p = self._model_with_prediction(tecnico_user, model_id="dp-admin")
        response = admin_client.delete(f"/api/v1/modelos/{m.model_id}/predictions/{p.id}")
        assert response.status_code == 204
        assert not PrediccionModelo.objects.filter(pk=p.id).exists()

    def test_anonymous_blocked(self, tecnico_user, anon_client):
        m, p = self._model_with_prediction(tecnico_user, model_id="dp-anon")
        response = anon_client.delete(f"/api/v1/modelos/{m.model_id}/predictions/{p.id}")
        assert response.status_code in (401, 403)
        assert PrediccionModelo.objects.filter(pk=p.id).exists()


@pytest.mark.django_db
class TestDownloadModel:
    def test_owner_can_download(self, tecnico_user, tecnico_client, tmp_path):
        write_sklearn_model(tmp_path, "dl", user_id=tecnico_user.pk)
        ModeloGuardado.objects.create(
            model_id="dl", user=tecnico_user, algorithm="RandomForest",
            treatment="Secano", targets=["MCD"], input_features=["tmax"],
            all_cols=["MCD", "tmax"], window_size=2, metrics={},
            geo={"punto": {"lat": 1, "lng": 1}},
        )
        with override_settings(MODELS_STORAGE_PATH=tmp_path):
            response = tecnico_client.get("/api/v1/modelos/dl/download")
        assert response.status_code == 200
        assert response["Content-Type"] == "application/zip"
