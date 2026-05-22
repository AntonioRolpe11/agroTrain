"""Integration test for the /train endpoint success path."""
from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from apps.configurador.services.flamapy_service import FlamapyService


FIXTURE_PATH = Path(__file__).parent.parent.parent / "configurador" / "tests" / "fixtures" / "test_min.uvl"


@pytest.fixture(autouse=True)
def _warm():
    FlamapyService.warm_up(FIXTURE_PATH)


def _csv_bytes(n: int = 80) -> bytes:
    rng = np.random.default_rng(0)
    dates = pd.date_range("2026-01-01", periods=n, freq="D")
    df = pd.DataFrame({
        "date": dates,
        "MCD": 10 + rng.normal(0, 0.2, n).cumsum(),
        "tmax": 25 + rng.normal(0, 1, n),
        "tmin": 5 + rng.normal(0, 1, n),
    })
    return df.to_csv(index=False, sep=";").encode("utf-8")


@pytest.mark.django_db
class TestTrainSuccess:
    def test_train_returns_model_id_and_status_202(self, tecnico_client, tmp_path, monkeypatch):
        # Inhibit background threading so the test is deterministic
        called: dict = {}

        def fake_start(self, targets, input_cols, treatment, csv_content, **kwargs):
            called.update({
                "targets": targets, "input_cols": input_cols,
                "treatment": treatment, "user_id": kwargs.get("user_id"),
            })
            return "fake-model-id"

        monkeypatch.setattr(
            "apps.modelos.services.training_service.TrainingService.start_training",
            fake_start,
        )

        features = [
            "Entrada", "DatosParcela",
            "Tratamiento", "Secano",
            "TipoSuelo", "Vertisoles",
            "ParametrosEntrada", "Dendrometro", "DatoMCD",
            "TemperaturaAire",
            "VariableObjetivo", "MCD",
        ]
        response = tecnico_client.post(
            "/api/v1/modelos/train",
            {
                "features": json.dumps(features),
                "geo": json.dumps({"punto": {"lat": 37.1, "lng": -5.9}}),
                "csv_file": SimpleUploadedFile("x.csv", _csv_bytes(40), content_type="text/csv"),
            },
            format="multipart",
        )
        assert response.status_code == 202
        assert response.json()["model_id"] == "fake-model-id"
        assert called["treatment"] == "Secano"
        assert "MCD" in called["targets"]

    def test_train_with_invalid_geo_json_returns_400(self, tecnico_client):
        response = tecnico_client.post(
            "/api/v1/modelos/train",
            {
                "features": "[]",
                "geo": "not-json",
                "csv_file": SimpleUploadedFile("x.csv", b"a;b\n1;2", content_type="text/csv"),
            },
            format="multipart",
        )
        assert response.status_code == 400


@pytest.mark.django_db
class TestStatusEndpoint:
    def test_status_returns_404_when_model_not_found(self, tecnico_client):
        response = tecnico_client.get("/api/v1/modelos/never-trained/status")
        assert response.status_code == 404
