from __future__ import annotations

import json
from pathlib import Path

import joblib
import pandas as pd
import pytest
from sklearn.dummy import DummyRegressor
from sklearn.preprocessing import MinMaxScaler

from apps.modelos.services.training_service import _add_temporal_features


def csv_bytes(rows: int = 6, *, include_tmax: bool = True) -> bytes:
    """Build a deterministic CSV (semicolon-separated) used by predict/train tests."""
    headers = ["date", "MCD"] + (["tmax"] if include_tmax else [])
    lines = [";".join(headers)]
    for i in range(rows):
        values = [f"2026-04-{20 + i:02d}", str(10 + i)]
        if include_tmax:
            values.append(str(20 + i))
        lines.append(";".join(values))
    return "\n".join(lines).encode("utf-8")


def write_sklearn_model(
    base: Path,
    model_id: str,
    *,
    geo: dict | None = None,
    window_size: int = 2,
    user_id: int | None = None,
) -> Path:
    """Persist a tiny sklearn model artifact (Dummy estimator) for prediction tests."""
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
    metadata: dict = {
        "model_id": model_id,
        "algorithm": "RandomForest",
        "treatment": "Secano",
        "features": ["Secano", "DatoMCD", "TemperaturaAire"],
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
    }
    if user_id is not None:
        metadata["user_id"] = user_id
    (model_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
    return model_dir


@pytest.fixture
def fake_sklearn_model_factory(tmp_path):
    """Return a function that writes a sklearn model in tmp_path."""
    def _factory(model_id: str = "test-model", **kwargs) -> Path:
        return write_sklearn_model(tmp_path, model_id, **kwargs)
    return _factory


@pytest.fixture
def csv_factory():
    """Return the csv_bytes helper."""
    return csv_bytes
