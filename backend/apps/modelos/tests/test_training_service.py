from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from apps.modelos.services.storage_service import StorageService
from apps.modelos.services.training_service import (
    ModelosServiceError,
    TrainingService,
    _add_temporal_features,
    _build_estimator,
    _compute_metrics,
    _desescalar_parcial,
    _despike_isolated,
    _interpolate_sensor_gaps,
    get_training_status,
)
from sklearn.preprocessing import MinMaxScaler


def _build_csv(n_rows: int = 60) -> bytes:
    rng = np.random.default_rng(42)
    dates = pd.date_range("2026-01-01", periods=n_rows, freq="D")
    mcd = 10 + rng.normal(0, 0.5, size=n_rows).cumsum()
    tmax = 25 + rng.normal(0, 1, size=n_rows)
    df = pd.DataFrame({"date": dates.strftime("%Y-%m-%d"), "MCD": mcd, "tmax": tmax})
    return df.to_csv(index=False, sep=";").encode("utf-8")


class TestHelpers:
    def test_add_temporal_features_adds_lag_and_rolling(self):
        df = pd.DataFrame({"date": pd.date_range("2026-01-01", periods=10), "x": range(10)})
        out = _add_temporal_features(df, ["x"], window_size=3)
        assert "x_lag1" in out.columns
        assert "x_lag3" in out.columns
        assert "x_roll3d" in out.columns
        assert "day_sin" in out.columns
        assert "day_cos" in out.columns

    def test_add_temporal_features_skips_unknown_columns(self):
        df = pd.DataFrame({"date": pd.date_range("2026-01-01", periods=5), "x": range(5)})
        out = _add_temporal_features(df, ["x", "y"], window_size=2)
        assert "y_lag1" not in out.columns

    def test_interpolate_sensor_gaps_fills_humedad_with_5d_window(self):
        df = pd.DataFrame({"humedad_Hd05": [1.0, None, None, 5.0, 6.0]})
        out = _interpolate_sensor_gaps(df, ["humedad_Hd05"])
        assert out["humedad_Hd05"].isna().sum() == 0

    def test_interpolate_sensor_gaps_zero_fills_event_columns(self):
        # riego/lluvia con fill_strategy='zero': día sin evento -> 0, sin interpolar.
        df = pd.DataFrame({"riego": [None, 2.0, None, None, 8.0, None]})
        out = _interpolate_sensor_gaps(df, ["riego"], zero_fill_cols={"riego"})
        assert out["riego"].tolist() == [0.0, 2.0, 0.0, 0.0, 8.0, 0.0]

    def test_despike_isolated_corrects_one_day_spike(self):
        # Ruido diario pequeño + un pico aislado enorme -> se sustituye por media de vecinos.
        s = pd.Series([100.0, 101.0, 99.0, 100.0, 98.0, 900.0, 100.0, 101.0, 99.0, 100.0])
        out, n = _despike_isolated(s)
        assert n == 1
        assert out.iloc[5] == pytest.approx((98.0 + 100.0) / 2.0)  # media de vecinos

    def test_despike_isolated_keeps_real_trend(self):
        # Escalón sostenido (cambio real): vecinos NO son similares entre sí -> no se toca.
        s = pd.Series([100.0, 101.0, 99.0, 100.0, 200.0, 201.0, 199.0, 200.0])
        out, n = _despike_isolated(s)
        assert n == 0
        assert out.tolist() == s.tolist()

    def test_compute_metrics_returns_keys(self):
        y_true = np.array([1, 2, 3, 4, 5])
        y_pred = np.array([1, 2, 3, 4, 5])
        metrics = _compute_metrics(y_true, y_pred)
        assert set(metrics) == {"mae", "rmse", "r2"}
        assert metrics["r2"] == pytest.approx(1.0)

    def test_desescalar_parcial(self):
        scaler = MinMaxScaler()
        scaler.fit([[0, 10], [100, 20]])
        scaled = np.array([[0.5], [0.0]])
        result = _desescalar_parcial(scaler, scaled, col_idx=0)
        assert result.shape == (2, 1)


class TestBuildEstimator:
    def test_random_forest(self):
        from sklearn.ensemble import RandomForestRegressor
        est = _build_estimator("RandomForest", {})
        assert isinstance(est, RandomForestRegressor)

    def test_gradient_boosting(self):
        from sklearn.ensemble import HistGradientBoostingRegressor
        est = _build_estimator("GradientBoosting", {})
        assert isinstance(est, HistGradientBoostingRegressor)

    def test_svr(self):
        from sklearn.svm import SVR
        est = _build_estimator("SVR", {"kernel": "linear"})
        assert isinstance(est, SVR)

    def test_pls_clamps_n_components_to_data(self):
        from sklearn.cross_decomposition import PLSRegression
        warnings_out: list[str] = []
        est = _build_estimator(
            "PLSRegression", {"n_components": 10},
            n_features=3, n_samples=20,
            warnings_out=warnings_out, target="T",
        )
        assert isinstance(est, PLSRegression)
        assert est.n_components == 3
        assert any("PLSRegression" in w for w in warnings_out)

    def test_elasticnet(self):
        from sklearn.linear_model import ElasticNet
        est = _build_estimator("ElasticNet", {"alpha": 0.1, "l1_ratio": 0.5})
        assert isinstance(est, ElasticNet)

    def test_unknown_algorithm_raises(self):
        with pytest.raises(ModelosServiceError):
            _build_estimator("UnknownAlgo", {})


@pytest.mark.django_db
class TestTrainingPipeline:
    def test_run_pipeline_with_random_forest(self, tmp_path, settings, admin_user):
        settings.MODELS_STORAGE_PATH = tmp_path

        svc = TrainingService()
        csv = _build_csv(n_rows=80)
        # Run pipeline synchronously (no thread)
        svc._run_pipeline(
            model_id="m1",
            targets=["MCD"],
            input_cols=["tmax"],
            treatment="Secano",  # treatment from fixture: window_size=5, RandomForest
            csv_content=csv,
            features=["Secano", "DatoMCD", "TemperaturaAire", "MCD"],
            geo={"punto": {"lat": 37.1, "lng": -5.9}},
            user_id=admin_user.pk,
        )

        # Metadata + model files must exist
        storage = StorageService()
        metadata = storage.load_metadata("m1")
        assert metadata["model_id"] == "m1"
        assert metadata["algorithm"] in ("RandomForest", "GradientBoosting", "HistGB")
        assert "MCD" in metadata["targets"]
        assert (tmp_path / "m1" / "model_MCD.pkl").exists()
        assert (tmp_path / "m1" / "scaler_MCD.pkl").exists()

    def test_missing_target_columns_raises(self, tmp_path, settings):
        settings.MODELS_STORAGE_PATH = tmp_path
        svc = TrainingService()
        with pytest.raises(ModelosServiceError, match="Columnas ausentes"):
            svc._run_pipeline(
                model_id="m2",
                targets=["NoExisteCol"],
                input_cols=["tmax"],
                treatment="Secano",
                csv_content=_build_csv(50),
                features=[],
                geo={},
                user_id=None,
            )

    def test_invalid_csv_raises(self, tmp_path, settings):
        settings.MODELS_STORAGE_PATH = tmp_path
        svc = TrainingService()
        with pytest.raises(ModelosServiceError, match="CSV"):
            svc._run_pipeline(
                model_id="m3",
                targets=["MCD"],
                input_cols=[],
                treatment="Secano",
                csv_content=b"not a csv",
                features=[],
                geo={},
                user_id=None,
            )

    def test_empty_targets_raises(self, tmp_path, settings):
        settings.MODELS_STORAGE_PATH = tmp_path
        svc = TrainingService()
        with pytest.raises(ModelosServiceError, match="objetivo"):
            svc._run_pipeline(
                model_id="m4",
                targets=[],
                input_cols=["tmax"],
                treatment="Secano",
                csv_content=_build_csv(40),
                features=[],
                geo={},
                user_id=None,
            )


class TestRegistry:
    def test_get_training_status_unknown_returns_none(self):
        assert get_training_status("never-existed") is None
