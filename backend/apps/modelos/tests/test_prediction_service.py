from __future__ import annotations

import json
from pathlib import Path

import joblib
import pandas as pd
import pytest
from django.test import override_settings
from sklearn.dummy import DummyRegressor
from sklearn.preprocessing import MinMaxScaler

from apps.modelos.services.prediction_service import PredictionService, PredictionServiceError
from apps.modelos.services.training_service import _add_temporal_features


def _write_sklearn_model(base: Path, model_id: str, *, geo: dict | None = None, window_size: int = 2) -> None:
    model_dir = base / model_id
    model_dir.mkdir(parents=True)

    train_df = pd.DataFrame(
        {
            "date": pd.date_range("2026-04-25", periods=6, freq="D"),
            "MCD": [10, 11, 12, 13, 14, 15],
            "tmax": [20, 21, 22, 23, 24, 25],
        }
    )
    df_aug = _add_temporal_features(train_df.copy(), ["MCD", "tmax"], window_size)
    df_aug = df_aug.drop(columns=["date"], errors="ignore").dropna()
    feat_cols = [c for c in df_aug.columns if c != "MCD"]

    scaler = MinMaxScaler()
    arr = scaler.fit_transform(df_aug[["MCD", *feat_cols]])
    reg = DummyRegressor(strategy="mean")
    reg.fit(arr[:, 1:], arr[:, 0])

    joblib.dump(reg, model_dir / "model_MCD.pkl")
    joblib.dump(scaler, model_dir / "scaler_MCD.pkl")
    (model_dir / "metadata.json").write_text(
        json.dumps(
            {
                "model_id": model_id,
                "algorithm": "GradientBoosting",
                "crop": "Olivo",
                "features": ["Olivo", "DatoMCD", "TemperaturaAire"],
                "geo": geo if geo is not None else {"punto": {"lat": 37.1, "lng": -5.9}, "cloudThreshold": 20},
                "all_cols": ["MCD", "tmax"],
                "targets": ["MCD"],
                "input_features": ["tmax"],
                "window_size": window_size,
                "temporal_features": True,
                "feature_columns_by_target": {"MCD": feat_cols},
                "n_samples": 4,
                "n_train": 3,
                "n_val": 1,
                "metrics": {},
                "warnings": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _csv(rows: int = 4, *, include_tmax: bool = True) -> bytes:
    headers = ["date", "MCD"] + (["tmax"] if include_tmax else [])
    lines = [";".join(headers)]
    for i in range(rows):
        values = [f"2026-04-{20 + i:02d}", str(10 + i)]
        if include_tmax:
            values.append(str(20 + i))
        lines.append(";".join(values))
    return "\n".join(lines).encode("utf-8")


@pytest.mark.django_db
def test_predict_sklearn_generates_single_value(tmp_path):
    model_id = "model-ok"
    _write_sklearn_model(tmp_path, model_id)

    with override_settings(MODELS_STORAGE_PATH=tmp_path):
        result = PredictionService().predict_one(model_id, _csv(rows=4))

    assert result["model_id"] == model_id
    assert result["input_row_count"] == 4
    assert set(result["predictions"]) == {"MCD"}
    assert isinstance(result["predictions"]["MCD"], float)
    assert str(result["predicted_for_date"]) == "2026-04-24"


@pytest.mark.django_db
def test_predict_requires_geo(tmp_path):
    model_id = "model-no-geo"
    _write_sklearn_model(tmp_path, model_id, geo={})

    with override_settings(MODELS_STORAGE_PATH=tmp_path):
        with pytest.raises(PredictionServiceError, match="ubicación"):
            PredictionService().predict_one(model_id, _csv(rows=4))


@pytest.mark.django_db
def test_predict_requires_all_columns(tmp_path):
    model_id = "model-missing-column"
    _write_sklearn_model(tmp_path, model_id)

    with override_settings(MODELS_STORAGE_PATH=tmp_path):
        with pytest.raises(PredictionServiceError, match="Columnas ausentes"):
            PredictionService().predict_one(model_id, _csv(rows=4, include_tmax=False))


@pytest.mark.django_db
def test_predict_requires_enough_window_rows(tmp_path):
    model_id = "model-short"
    _write_sklearn_model(tmp_path, model_id, window_size=3)

    with override_settings(MODELS_STORAGE_PATH=tmp_path):
        with pytest.raises(PredictionServiceError, match="días más recientes"):
            PredictionService().predict_one(model_id, _csv(rows=2))


@pytest.mark.django_db
def test_predict_tolerates_old_gaps_with_warning(tmp_path):
    """Hueco antiguo no impide predecir si la ventana reciente está completa; solo avisa."""
    model_id = "model-old-gap"
    _write_sklearn_model(tmp_path, model_id, window_size=2)

    # Falta 2026-04-21 (hueco antiguo); las 2 fechas recientes (04-22, 04-23) están completas.
    csv = (
        "date;MCD;tmax\n"
        "2026-04-20;10;20\n"
        "2026-04-22;12;22\n"
        "2026-04-23;13;23\n"
    ).encode("utf-8")

    with override_settings(MODELS_STORAGE_PATH=tmp_path):
        result = PredictionService().predict_one(model_id, csv)

    assert isinstance(result["predictions"]["MCD"], float)
    assert any("2026-04-21" in str(w) or "anteriores" in str(w) for w in result["warnings"])
