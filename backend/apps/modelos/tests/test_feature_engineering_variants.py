"""Cover the less-used feature_engineering variants to lift module coverage."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from apps.modelos.services.feature_engineering import VARIANTS, add_features


@pytest.fixture
def base_df():
    dates = pd.date_range("2026-01-01", periods=40, freq="D")
    return pd.DataFrame(
        {
            "date": dates,
            "MCD": np.linspace(10, 14, 40),
            "tmax": np.linspace(20, 25, 40),
            "tmin": np.linspace(5, 10, 40),
            "dpv": np.linspace(0.5, 1.5, 40),
            "humedad_Hd05": np.linspace(20, 30, 40),
            "humedad_Hd15": np.linspace(22, 32, 40),
            "humedad_Hd25": np.linspace(24, 34, 40),
            "humedad_Hd55": np.linspace(15, 18, 40),
            "humedad_Hd65": np.linspace(13, 16, 40),
            "humedad_Hd75": np.linspace(10, 14, 40),
        }
    )


@pytest.mark.parametrize("variant", VARIANTS)
def test_each_variant_produces_dataframe(base_df, variant):
    feature_cols = ["MCD", "tmax", "tmin", "dpv"]
    out = add_features(base_df.copy(), feature_cols, window_size=5, variant=variant)
    assert isinstance(out, pd.DataFrame)
    # Basic lag features should always be present (target_only variant restricts to target col)
    if variant == "target_only":
        assert "MCD_lag1" in out.columns
    else:
        assert "MCD_lag1" in out.columns
        assert "tmax_lag1" in out.columns


def test_calendar_variant_includes_month_and_week(base_df):
    out = add_features(base_df, ["MCD"], 5, "calendar")
    assert "month" in out.columns
    assert "weekofyear" in out.columns
    assert "agro_season" in out.columns


def test_soil_profile_variant_includes_humidity_features(base_df):
    out = add_features(base_df, ["MCD"], 5, "soil_profile")
    assert "humedad_profile_mean" in out.columns
    assert "humedad_shallow_mean" in out.columns
    assert "humedad_deep_mean" in out.columns
    assert "humedad_surface_deep_gap" in out.columns


def test_stress_indices_variant(base_df):
    out = add_features(base_df, ["MCD"], 5, "stress_indices")
    assert "temp_air_range" in out.columns
    assert "dpv_x_tmax" in out.columns


def test_robust_smoothing_variant(base_df):
    out = add_features(base_df, ["MCD"], 5, "robust_smoothing")
    assert "MCD_median3d" in out.columns
    assert "MCD_diff1d" in out.columns


def test_unknown_variant_raises(base_df):
    with pytest.raises(ValueError):
        add_features(base_df, ["MCD"], 5, "no-such-variant")


def test_full_variant_combines_all(base_df):
    out = add_features(base_df, ["MCD"], 5, "full")
    # Should have lag, rolling, ema, calendar, stress, soil, smoothing
    assert "MCD_lag1" in out.columns
    assert "month_sin" in out.columns
    assert "MCD_median3d" in out.columns
    assert "humedad_profile_mean" in out.columns
