"""
Feature engineering variants for offline experimentation.

The `basic` variant matches `_add_temporal_features` in
`backend/apps/modelos/services/training_service.py` closely enough to reproduce
the production baseline. Other variants extend it with longer target/sensor
memory, calendar context, soil profile aggregates, stress proxies and robust
smoothed signals.

All lag/rolling/EMA/difference features are built from values shifted at least
one day into the past. Current-day columns that remain in the frame are raw
same-day sensor inputs, not target-derived engineered values.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

VARIANTS: tuple[str, ...] = (
    "basic",
    "long_lags",
    "multi_roll",
    "ema",
    "calendar",
    "irrigation_memory",
    "soil_profile",
    "stress_indices",
    "robust_smoothing",
    "target_only",
    "full",
)

HUMIDITY_DEPTHS: tuple[tuple[str, int], ...] = (
    ("humedad_Hd05", 5),
    ("humedad_Hd15", 15),
    ("humedad_Hd25", 25),
    ("humedad_Hd35", 35),
    ("humedad_Hd45", 45),
    ("humedad_Hd55", 55),
    ("humedad_Hd65", 65),
    ("humedad_Hd75", 75),
)
TEMP_DEPTHS: tuple[tuple[str, int], ...] = (
    ("temp_s05", 5),
    ("temp_s15", 15),
    ("temp_s25", 25),
    ("temp_s35", 35),
    ("temp_s45", 45),
    ("temp_s55", 55),
    ("temp_s65", 65),
    ("temp_s75", 75),
)


def _add_day_of_year_cyclical(df: pd.DataFrame) -> pd.DataFrame:
    if "date" not in df.columns:
        return df
    doy = pd.to_datetime(df["date"]).dt.dayofyear
    df["day_sin"] = np.sin(2 * np.pi * doy / 365.0)
    df["day_cos"] = np.cos(2 * np.pi * doy / 365.0)
    return df


def _add_calendar(df: pd.DataFrame) -> pd.DataFrame:
    if "date" not in df.columns:
        return df
    date = pd.to_datetime(df["date"])
    month = date.dt.month
    week = date.dt.isocalendar().week.astype(int)
    df["month"] = month
    df["weekofyear"] = week
    df["month_sin"] = np.sin(2 * np.pi * month / 12.0)
    df["month_cos"] = np.cos(2 * np.pi * month / 12.0)
    df["week_sin"] = np.sin(2 * np.pi * week / 53.0)
    df["week_cos"] = np.cos(2 * np.pi * week / 53.0)

    # Coarse agronomic seasons for olive orchards in Mediterranean climate.
    season = np.select(
        [
            month.isin([3, 4, 5]),
            month.isin([6, 7, 8]),
            month.isin([9, 10, 11]),
        ],
        [1, 2, 3],
        default=0,
    )
    df["agro_season"] = season.astype(float)
    return df


def _add_lags(df: pd.DataFrame, cols: list[str], lags: list[int]) -> pd.DataFrame:
    for col in cols:
        if col not in df.columns:
            continue
        for lag in lags:
            df[f"{col}_lag{lag}"] = df[col].shift(lag)
    return df


def _add_rolling(df: pd.DataFrame, cols: list[str], windows: list[int]) -> pd.DataFrame:
    for col in cols:
        if col not in df.columns:
            continue
        for w in windows:
            df[f"{col}_roll{w}d"] = df[col].shift(1).rolling(w).mean()
    return df


def _add_ema(df: pd.DataFrame, cols: list[str], alphas: list[float]) -> pd.DataFrame:
    for col in cols:
        if col not in df.columns:
            continue
        for a in alphas:
            df[f"{col}_ema{int(a * 100)}"] = df[col].shift(1).ewm(alpha=a, adjust=False).mean()
    return df



def _existing_depth_cols(df: pd.DataFrame, depth_cols: tuple[tuple[str, int], ...]) -> list[str]:
    return [col for col, _depth in depth_cols if col in df.columns]


def _add_soil_profile(df: pd.DataFrame) -> pd.DataFrame:
    humidity_cols = _existing_depth_cols(df, HUMIDITY_DEPTHS)
    temp_cols = _existing_depth_cols(df, TEMP_DEPTHS)

    if humidity_cols:
        shallow_h = [c for c in ("humedad_Hd05", "humedad_Hd15", "humedad_Hd25") if c in df.columns]
        deep_h = [c for c in ("humedad_Hd55", "humedad_Hd65", "humedad_Hd75") if c in df.columns]
        df["humedad_profile_mean"] = df[humidity_cols].mean(axis=1)
        df["humedad_profile_std"] = df[humidity_cols].std(axis=1)
        if shallow_h:
            df["humedad_shallow_mean"] = df[shallow_h].mean(axis=1)
        if deep_h:
            df["humedad_deep_mean"] = df[deep_h].mean(axis=1)
        if shallow_h and deep_h:
            df["humedad_surface_deep_gap"] = df["humedad_shallow_mean"] - df["humedad_deep_mean"]
        if "humedad_Hd05" in df.columns and "humedad_Hd75" in df.columns:
            df["humedad_05_75_gradient"] = df["humedad_Hd05"] - df["humedad_Hd75"]

    if temp_cols:
        shallow_t = [c for c in ("temp_s05", "temp_s15", "temp_s25") if c in df.columns]
        deep_t = [c for c in ("temp_s55", "temp_s65", "temp_s75") if c in df.columns]
        df["temp_soil_profile_mean"] = df[temp_cols].mean(axis=1)
        df["temp_soil_profile_std"] = df[temp_cols].std(axis=1)
        if shallow_t:
            df["temp_soil_shallow_mean"] = df[shallow_t].mean(axis=1)
        if deep_t:
            df["temp_soil_deep_mean"] = df[deep_t].mean(axis=1)
        if shallow_t and deep_t:
            df["temp_soil_surface_deep_gap"] = df["temp_soil_shallow_mean"] - df["temp_soil_deep_mean"]
    return df


def _add_stress_indices(df: pd.DataFrame) -> pd.DataFrame:
    if "tmax" in df.columns and "tmin" in df.columns:
        df["temp_air_range"] = df["tmax"] - df["tmin"]
    if "dpv" in df.columns and "tmax" in df.columns:
        df["dpv_x_tmax"] = df["dpv"] * df["tmax"]
    if "dpv" in df.columns and "temp_air_range" in df.columns:
        df["dpv_x_temp_range"] = df["dpv"] * df["temp_air_range"]

    return df


def _add_robust_smoothing(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    for col in cols:
        if col not in df.columns:
            continue
        shifted = df[col].shift(1)
        for window in (3, 7, 14):
            df[f"{col}_median{window}d"] = shifted.rolling(window).median()
        df[f"{col}_diff1d"] = df[col].shift(1) - df[col].shift(2)
    return df


def add_features(
    df: pd.DataFrame,
    feature_cols: list[str],
    window_size: int,
    variant: str,
) -> pd.DataFrame:
    """
    Returns a copy of `df` augmented with engineered features for the requested variant.

    `feature_cols` should include both inputs and targets (autoregressive); production code
    passes `targets + input_features` so target lags are also available.
    """
    if variant not in VARIANTS:
        raise ValueError(f"Unknown variant {variant!r}. Allowed: {VARIANTS}")

    out = df.copy()

    base_lags = list(range(1, window_size + 1))
    base_roll = [min(7, window_size)]

    if variant == "basic":
        out = _add_day_of_year_cyclical(out)
        out = _add_lags(out, feature_cols, base_lags)
        out = _add_rolling(out, feature_cols, base_roll)
    elif variant == "long_lags":
        out = _add_day_of_year_cyclical(out)
        extra = [lag for lag in (14, 21, 28) if lag not in base_lags]
        out = _add_lags(out, feature_cols, base_lags + extra)
        out = _add_rolling(out, feature_cols, base_roll)
    elif variant == "multi_roll":
        out = _add_day_of_year_cyclical(out)
        out = _add_lags(out, feature_cols, base_lags)
        rolls = sorted({3, 7, 14, 30, *base_roll})
        out = _add_rolling(out, feature_cols, rolls)
    elif variant == "ema":
        out = _add_day_of_year_cyclical(out)
        out = _add_lags(out, feature_cols, base_lags)
        out = _add_rolling(out, feature_cols, base_roll)
        out = _add_ema(out, feature_cols, [0.3, 0.7])
    elif variant == "calendar":
        out = _add_day_of_year_cyclical(out)
        out = _add_calendar(out)
        out = _add_lags(out, feature_cols, base_lags)
        out = _add_rolling(out, feature_cols, base_roll)
    elif variant == "irrigation_memory":
        out = _add_day_of_year_cyclical(out)
        out = _add_lags(out, feature_cols, base_lags)
        out = _add_rolling(out, feature_cols, base_roll)
    elif variant == "soil_profile":
        out = _add_day_of_year_cyclical(out)
        out = _add_lags(out, feature_cols, base_lags)
        out = _add_rolling(out, feature_cols, base_roll)
        out = _add_soil_profile(out)
    elif variant == "stress_indices":
        out = _add_day_of_year_cyclical(out)
        out = _add_lags(out, feature_cols, base_lags)
        out = _add_rolling(out, feature_cols, base_roll)
        out = _add_stress_indices(out)
    elif variant == "robust_smoothing":
        out = _add_day_of_year_cyclical(out)
        out = _add_lags(out, feature_cols, base_lags)
        out = _add_rolling(out, feature_cols, base_roll)
        out = _add_robust_smoothing(out, feature_cols)
    elif variant == "target_only":
        # Caller passes the target as the first column. Keep this variant as a
        # pure autoregressive benchmark: no calendar or external sensor signal.
        target_cols = feature_cols[:1]
        keep_cols = [c for c in ("date", *target_cols) if c in out.columns]
        out = out[keep_cols].copy()
        out = _add_lags(out, target_cols, base_lags)
        out = _add_rolling(out, target_cols, sorted({3, 7, 14, *base_roll}))
        out = _add_ema(out, target_cols, [0.3, 0.7])
        out = _add_robust_smoothing(out, target_cols)
    elif variant == "full":
        out = _add_day_of_year_cyclical(out)
        out = _add_calendar(out)
        extra = [lag for lag in (14, 21, 28) if lag not in base_lags]
        out = _add_lags(out, feature_cols, base_lags + extra)
        rolls = sorted({3, 7, 14, 30, *base_roll})
        out = _add_rolling(out, feature_cols, rolls)
        out = _add_ema(out, feature_cols, [0.3, 0.7])
        out = _add_soil_profile(out)
        out = _add_stress_indices(out)
        out = _add_robust_smoothing(out, feature_cols)

    return out
