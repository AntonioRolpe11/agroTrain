from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import joblib
import numpy as np
import pandas as pd
import pytest
from django.test import override_settings
from sklearn.dummy import DummyRegressor
from sklearn.preprocessing import MinMaxScaler

from apps.modelos.services.feature_engineering import add_features
from apps.modelos.services.hyperprofile_registry import (
    HYPERPROFILE_REGISTRY,
    UnknownHyperprofileError,
    get_hyperprofile,
)
from apps.modelos.services.prediction_service import PredictionService, PredictionServiceError
from apps.modelos.services.training_service import _build_estimator, ModelosServiceError


# ── hyperprofile_registry ──────────────────────────────────────────────────────

def test_get_hyperprofile_returns_copy():
    hp = get_hyperprofile("secano_mcd_pls_v1")
    hp["params"]["n_components"] = 999
    # original must be untouched
    assert HYPERPROFILE_REGISTRY["secano_mcd_pls_v1"]["params"]["n_components"] == 8


def test_get_hyperprofile_unknown_raises():
    with pytest.raises(UnknownHyperprofileError, match="nonexistent"):
        get_hyperprofile("nonexistent")


def test_all_profiles_have_required_keys():
    required_keys = {"algorithm", "feature_variant", "required_inputs", "optional_inputs", "params"}
    for name, profile in HYPERPROFILE_REGISTRY.items():
        missing = required_keys - profile.keys()
        assert not missing, f"Perfil {name!r} le faltan claves: {missing}"


def test_svr_profiles_have_max_samples():
    svr_profiles = [k for k, v in HYPERPROFILE_REGISTRY.items() if v["algorithm"] == "SVR"]
    for name in svr_profiles:
        assert "max_samples" in HYPERPROFILE_REGISTRY[name], f"{name} SVR debe tener max_samples"


# ── _build_estimator ───────────────────────────────────────────────────────────

def test_build_estimator_pls_clamps_n_components():
    est = _build_estimator("PLSRegression", {"n_components": 20, "scale": False}, n_features=5, n_samples=10)
    assert est.n_components == 5


def test_build_estimator_pls_clamps_to_n_samples():
    est = _build_estimator("PLSRegression", {"n_components": 10, "scale": False}, n_features=15, n_samples=4)
    assert est.n_components == 4


def test_build_estimator_elasticnet():
    est = _build_estimator("ElasticNet", {"alpha": 0.001, "l1_ratio": 0.9, "max_iter": 5000})
    assert est.alpha == 0.001


def test_build_estimator_svr():
    est = _build_estimator("SVR", {"C": 100.0, "kernel": "linear", "epsilon": 0.1, "gamma": "auto"})
    assert est.C == 100.0


def test_build_estimator_unknown_raises():
    with pytest.raises(ModelosServiceError, match="no soportado"):
        _build_estimator("FakeAlgorithm", {})


# ── per-target prediction backward compat ─────────────────────────────────────

def _write_per_target_model(
    base: Path,
    model_id: str,
    *,
    geo: dict | None = None,
    targets: list[str] | None = None,
    feature_variant: str = "target_only",
    window_size: int = 3,
) -> None:
    targets = targets or ["MCD"]
    model_dir = base / model_id
    model_dir.mkdir(parents=True)

    target_profiles = {}
    feature_columns_by_target = {}
    for t in targets:
        # Need ≥14 rows so roll14d/median14d are non-NaN for the last row
        n = 30
        df = pd.DataFrame({
            "date": pd.date_range("2026-01-01", periods=n, freq="D"),
            t: np.arange(n, dtype=float),
        })
        aug = add_features(df.copy(), [t], window_size, feature_variant)
        aug = aug.drop(columns=["date"], errors="ignore").dropna()
        feat_cols = [c for c in aug.columns if c != t]

        scaler = MinMaxScaler()
        arr = scaler.fit_transform(aug[[t] + feat_cols])
        reg = DummyRegressor(strategy="mean")
        reg.fit(arr[:, 1:], arr[:, 0])

        joblib.dump(reg, model_dir / f"model_{t}.pkl")
        joblib.dump(scaler, model_dir / f"scaler_{t}.pkl")
        feature_columns_by_target[t] = feat_cols
        target_profiles[t] = {
            "algorithm": "DummyRegressor",
            "window_size": window_size,
            "feature_variant": feature_variant,
            "hyperprofile": None,
        }

    default_geo = {"punto": {"lat": 37.1, "lng": -5.9}, "cloudThreshold": 20}
    (model_dir / "metadata.json").write_text(
        json.dumps({
            "model_id": model_id,
            "algorithm": "Mixed",
            "treatment": "RiegoControl",
            "features": [],
            "geo": geo if geo is not None else default_geo,
            "all_cols": targets,
            "targets": targets,
            "input_features": [],
            "window_size": window_size,
            "temporal_features": True,
            "feature_columns_by_target": feature_columns_by_target,
            "target_profiles": target_profiles,
            "n_samples": 16,
            "n_train": 12,
            "n_val": 4,
            "metrics": {},
            "warnings": [],
        }, ensure_ascii=False),
        encoding="utf-8",
    )


def _csv_for_targets(targets: list[str], rows: int = 16) -> bytes:
    lines = [";".join(["date"] + targets)]
    for i in range(rows):
        row = [f"2026-05-{i + 1:02d}"] + [str(float(10 + i))] * len(targets)
        lines.append(";".join(row))
    return "\n".join(lines).encode("utf-8")


@pytest.mark.django_db
def test_predict_per_target_single_target(tmp_path):
    model_id = "per-target-single"
    _write_per_target_model(tmp_path, model_id)

    with override_settings(MODELS_STORAGE_PATH=tmp_path):
        result = PredictionService().predict_one(model_id, _csv_for_targets(["MCD"]))

    assert set(result["predictions"]) == {"MCD"}
    assert isinstance(result["predictions"]["MCD"], float)


@pytest.mark.django_db
def test_predict_per_target_multiple_targets(tmp_path):
    model_id = "per-target-multi"
    _write_per_target_model(tmp_path, model_id, targets=["MCD", "TasaBuenos"])

    with override_settings(MODELS_STORAGE_PATH=tmp_path):
        result = PredictionService().predict_one(
            model_id, _csv_for_targets(["MCD", "TasaBuenos"])
        )

    assert set(result["predictions"]) == {"MCD", "TasaBuenos"}


@pytest.mark.django_db
def test_predict_per_target_insufficient_rows(tmp_path):
    model_id = "per-target-short"
    _write_per_target_model(tmp_path, model_id, window_size=5)

    with override_settings(MODELS_STORAGE_PATH=tmp_path):
        with pytest.raises(PredictionServiceError, match="días más recientes"):
            PredictionService().predict_one(model_id, _csv_for_targets(["MCD"], rows=3))


@pytest.mark.django_db
def test_legacy_metadata_without_target_profiles_still_works(tmp_path):
    """Models without target_profiles in metadata use the old sklearn path."""
    from apps.modelos.tests.test_prediction_service import _write_sklearn_model, _csv

    model_id = "legacy-no-profiles"
    _write_sklearn_model(tmp_path, model_id)

    with override_settings(MODELS_STORAGE_PATH=tmp_path):
        result = PredictionService().predict_one(model_id, _csv(rows=4))

    assert set(result["predictions"]) == {"MCD"}
