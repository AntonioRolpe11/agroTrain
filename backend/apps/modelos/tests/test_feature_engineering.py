from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from apps.modelos.services.feature_engineering import add_features


def _base_df(n: int = 40, extra_cols: list[str] | None = None) -> pd.DataFrame:
    data: dict = {
        "date": pd.date_range("2025-01-01", periods=n, freq="D"),
        "MCD": np.random.default_rng(0).uniform(100, 200, n),
        "tmax": np.random.default_rng(1).uniform(20, 35, n),
        "tmin": np.random.default_rng(2).uniform(5, 20, n),
        "dpv": np.random.default_rng(3).uniform(0.5, 3.0, n),
        "pluv": np.random.default_rng(4).uniform(0, 5, n),
    }
    for col in (extra_cols or []):
        data[col] = np.random.default_rng(5).uniform(0, 1, n)
    return pd.DataFrame(data)


def test_target_only_excludes_external_sensors():
    df = _base_df()
    result = add_features(df, ["MCD"], window_size=3, variant="target_only")
    cols = set(result.columns) - {"date"}
    assert "MCD" in cols
    # No tmax, tmin, dpv, pluv columns (except as part of MCD-derived names)
    assert not any(c in cols for c in ("tmax", "tmin", "dpv", "pluv"))
    # No day_sin from calendar
    assert "day_sin" not in cols


def test_target_only_contains_lags_and_smoothing():
    df = _base_df()
    result = add_features(df, ["MCD"], window_size=3, variant="target_only")
    cols = set(result.columns)
    assert "MCD_lag1" in cols
    assert "MCD_lag3" in cols
    assert "MCD_ema30" in cols
    assert "MCD_diff1d" in cols


def test_ema_uses_shifted_values():
    """EMA features must not use current-day values (shift(1) required)."""
    df = _base_df(n=20)
    result = add_features(df.copy(), ["MCD"], window_size=3, variant="ema")
    # ema30 of row i must equal ewm of rows 0..i-1, not including row i
    manual_ema = df["MCD"].shift(1).ewm(alpha=0.3, adjust=False).mean()
    pd.testing.assert_series_equal(
        result["MCD_ema30"].reset_index(drop=True),
        manual_ema.reset_index(drop=True),
        check_names=False,
    )


def test_lags_use_shifted_values():
    df = _base_df(n=20)
    result = add_features(df.copy(), ["MCD"], window_size=3, variant="basic")
    pd.testing.assert_series_equal(
        result["MCD_lag1"].reset_index(drop=True),
        df["MCD"].shift(1).reset_index(drop=True),
        check_names=False,
    )


def test_irrigation_memory_tolerates_missing_riego():
    """irrigation_memory must not crash when 'riego' column absent."""
    df = _base_df()  # has pluv but not riego
    result = add_features(df.copy(), ["MCD", "tmax", "dpv", "pluv"], window_size=3, variant="irrigation_memory")
    assert "pluv_acc3d" in result.columns
    assert "riego_acc3d" not in result.columns
    # water_acc7d requires both riego and pluv; only pluv present → should not appear
    assert "water_acc7d" not in result.columns


def test_stress_indices_without_pluv():
    """stress_indices builds dpv/temp features even when pluv absent."""
    df = _base_df()[["date", "MCD", "tmax", "tmin", "dpv"]]
    result = add_features(df.copy(), ["MCD", "tmax", "tmin", "dpv"], window_size=3, variant="stress_indices")
    assert "temp_air_range" in result.columns
    assert "dpv_x_tmax" in result.columns
    assert "dpv_x_temp_range" in result.columns
    # pluv absent → water_prev_day should not appear
    assert "water_prev_day" not in result.columns


def test_stress_indices_without_tmax_tmin_skips_derived():
    """If required columns for a derived feature are absent, that feature is silently skipped."""
    df = _base_df()[["date", "MCD", "dpv", "pluv"]]
    result = add_features(df.copy(), ["MCD", "dpv"], window_size=2, variant="stress_indices")
    # tmax absent → no temp_air_range, no dpv_x_tmax
    assert "temp_air_range" not in result.columns
    assert "dpv_x_tmax" not in result.columns


def test_unknown_variant_raises():
    df = _base_df()
    with pytest.raises(ValueError, match="Variante desconocida"):
        add_features(df, ["MCD"], window_size=3, variant="nonexistent_variant")


def test_soil_profile_optional_depths():
    """soil_profile computes aggregates from whatever humidity depths are present."""
    df = _base_df(extra_cols=["humedad_Hd05", "humedad_Hd35", "humedad_Hd55"])
    result = add_features(
        df.copy(),
        ["MCD", "tmax", "humedad_Hd05", "humedad_Hd35", "humedad_Hd55"],
        window_size=3,
        variant="soil_profile",
    )
    assert "humedad_profile_mean" in result.columns
    assert "humedad_profile_std" in result.columns


def test_add_features_returns_copy():
    df = _base_df()
    original_cols = list(df.columns)
    add_features(df, ["MCD"], window_size=3, variant="basic")
    assert list(df.columns) == original_cols
