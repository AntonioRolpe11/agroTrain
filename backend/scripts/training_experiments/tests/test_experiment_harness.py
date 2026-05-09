from __future__ import annotations

import json
import random

import pandas as pd
import pytest

from backend.scripts.training_experiments.data_prep import platform_input_columns, to_platform_training_frame
from backend.scripts.training_experiments.features import add_features
from backend.scripts.training_experiments.run_experiments import (
    _build_rf,
    _prepare_xy,
    _sample_rf,
    iter_temporal_splits,
    temporal_holdout_index,
)
from backend.scripts.training_experiments.select_winners import select


def _toy_daily_frame(n: int = 24) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.date_range("2025-01-01", periods=n, freq="D"),
            "MCD": [float(i) for i in range(1, n + 1)],
            "riego": [float(i) for i in range(n)],
            "pluv": [float(i % 3) for i in range(n)],
            "humedad_Hd05": [20.0 + i for i in range(n)],
            "humedad_Hd75": [35.0 + i for i in range(n)],
            "tmax": [28.0 + i for i in range(n)],
            "tmin": [12.0 + i for i in range(n)],
            "dpv": [1.0 + i / 10.0 for i in range(n)],
            "temp_s05": [18.0 + i for i in range(n)],
            "riego": [float(i % 2) for i in range(n)],
            "ce_riego": [0.5 for _ in range(n)],
        }
    )


def test_rolling_lags_ema_and_diffs_are_shifted_one_day() -> None:
    df = _toy_daily_frame()

    basic = add_features(df, ["MCD", "riego"], window_size=3, variant="basic")
    assert basic.loc[4, "MCD_lag1"] == pytest.approx(4.0)
    assert basic.loc[4, "MCD_roll3d"] == pytest.approx((2.0 + 3.0 + 4.0) / 3.0)

    irrigation = add_features(df, ["MCD", "riego"], window_size=3, variant="irrigation_memory")
    assert irrigation.loc[4, "riego_acc3d"] == pytest.approx(df.loc[1:3, "riego"].sum())

    target_only = add_features(df, ["MCD", "riego"], window_size=3, variant="target_only")
    assert "riego" not in target_only.columns
    assert target_only.loc[1, "MCD_ema30"] == pytest.approx(1.0)
    assert target_only.loc[4, "MCD_diff1d"] == pytest.approx(1.0)


def test_prepare_xy_target_only_excludes_external_sensors() -> None:
    X, y = _prepare_xy(
        _toy_daily_frame(),
        target="MCD",
        window_size=3,
        feature_variant="target_only",
        inputs=["riego", "pluv", "humedad_Hd05"],
    )

    assert not X.empty
    assert not y.empty
    assert all(not col.startswith(("riego", "pluv", "humedad")) for col in X.columns)
    assert any(col.startswith("MCD_lag") for col in X.columns)


def test_platform_training_frame_excludes_non_uvl_and_telemetry_columns() -> None:
    df = _toy_daily_frame()
    df["NDVI"] = 0.7
    platform_df = to_platform_training_frame(df)

    assert "date" in platform_df.columns
    assert "MCD" in platform_df.columns
    assert "humedad_Hd05" in platform_df.columns
    assert "tmax" in platform_df.columns
    assert "dpv" in platform_df.columns
    assert "temp_s05" not in platform_df.columns
    assert "riego" not in platform_df.columns
    assert "ce_riego" not in platform_df.columns
    assert "NDVI" not in platform_df.columns
    assert platform_input_columns(platform_df) == [
        "humedad_Hd05",
        "humedad_Hd75",
        "tmax",
        "tmin",
        "pluv",
        "dpv",
    ]


def test_temporal_split_never_mixes_future_into_training() -> None:
    splits = iter_temporal_splits(40, n_splits=5, max_train_size=10)

    assert len(splits) == 5
    for train_idx, val_idx in splits:
        assert max(train_idx) < min(val_idx)
        assert len(train_idx) <= 10


def test_holdout_index_reserves_final_15_percent() -> None:
    assert temporal_holdout_index(100) == 85
    assert temporal_holdout_index(10) == 8


def test_random_search_and_estimators_are_reproducible() -> None:
    params_a = _sample_rf(random.Random(42))
    params_b = _sample_rf(random.Random(42))

    assert params_a == params_b
    assert _build_rf(params_a).random_state == 42


def test_select_winners_discards_holdout_overfit_and_prefers_simple_near_tie(tmp_path) -> None:
    results = pd.DataFrame(
        [
            {
                "station": "S1",
                "target": "MCD",
                "algo": "RandomForest",
                "variant_id": "RandomForest#BASELINE",
                "window_size": 7,
                "feature_variant": "basic",
                "params": "{}",
                "rmse_mean": 10.0,
                "rmse_std": 1.0,
                "r2_mean": 0.1,
                "mae_mean": 8.0,
                "holdout_rmse": 11.0,
                "holdout_r2": 0.1,
                "n_train_avg": 20,
                "n_folds": 5,
                "train_time_sec": 0.1,
                "feature_importances": "{}",
                "error": "",
            },
            {
                "station": "S1",
                "target": "MCD",
                "algo": "CatBoost",
                "variant_id": "CatBoost#000",
                "window_size": 7,
                "feature_variant": "full",
                "params": "{}",
                "rmse_mean": 3.0,
                "rmse_std": 0.1,
                "r2_mean": 0.9,
                "mae_mean": 2.5,
                "holdout_rmse": 4.5,
                "holdout_r2": 0.7,
                "n_train_avg": 20,
                "n_folds": 5,
                "train_time_sec": 0.1,
                "feature_importances": "{}",
                "error": "",
            },
            {
                "station": "S1",
                "target": "MCD",
                "algo": "ElasticNet",
                "variant_id": "ElasticNet#000",
                "window_size": 5,
                "feature_variant": "target_only",
                "params": "{}",
                "rmse_mean": 4.0,
                "rmse_std": 0.1,
                "r2_mean": 0.8,
                "mae_mean": 3.5,
                "holdout_rmse": 4.2,
                "holdout_r2": 0.6,
                "n_train_avg": 20,
                "n_folds": 5,
                "train_time_sec": 0.1,
                "feature_importances": json.dumps({"MCD_lag1": 1.0}),
                "error": "",
            },
            {
                "station": "S1",
                "target": "TasaBuenos",
                "algo": "CatBoost",
                "variant_id": "CatBoost#001",
                "window_size": 7,
                "feature_variant": "full",
                "params": "{}",
                "rmse_mean": 4.0,
                "rmse_std": 0.0,
                "r2_mean": 0.9,
                "mae_mean": 3.0,
                "holdout_rmse": 4.1,
                "holdout_r2": 0.7,
                "n_train_avg": 20,
                "n_folds": 5,
                "train_time_sec": 0.1,
                "feature_importances": "{}",
                "error": "",
            },
            {
                "station": "S1",
                "target": "TasaBuenos",
                "algo": "ElasticNet",
                "variant_id": "ElasticNet#001",
                "window_size": 5,
                "feature_variant": "target_only",
                "params": "{}",
                "rmse_mean": 4.05,
                "rmse_std": 0.0,
                "r2_mean": 0.9,
                "mae_mean": 3.0,
                "holdout_rmse": 4.1,
                "holdout_r2": 0.7,
                "n_train_avg": 20,
                "n_folds": 5,
                "train_time_sec": 0.1,
                "feature_importances": "{}",
                "error": "",
            },
        ]
    )
    results_csv = tmp_path / "results.csv"
    results.to_csv(results_csv, index=False)

    winners_path, report_path = select(results_csv, tmp_path)
    winners = json.loads(winners_path.read_text(encoding="utf-8"))

    assert winners["S1"]["MCD"]["variant_id"] == "ElasticNet#000"
    assert winners["S1"]["TasaBuenos"]["variant_id"] == "ElasticNet#001"
    assert "Mejora vs baseline" in report_path.read_text(encoding="utf-8")
