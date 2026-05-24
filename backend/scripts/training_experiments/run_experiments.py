"""
Cross-station × target × variant runner for offline ML experimentation.

For each (station, target, algo, params, window_size, feature_variant) combination,
trains the model with `TimeSeriesSplit(5)` cross-validation on the first 85% of the
station's data, then evaluates the same configuration retrained on all 85% against
the held-out final 15% (`holdout_*` metrics). All results are streamed to a CSV.

Algorithms:
- Current baselines: RandomForest, HistGradientBoosting, LSTM
- Expanded tabular search: ExtraTrees, GradientBoosting, KNN, SVR,
  ElasticNet, PLSRegression
- Optional boosters behind `--include-optional-boosters`: LightGBM, XGBoost,
  CatBoost when installed
- Sequential TensorFlow families: LSTM, GRU, Conv1D, CNN-LSTM
- Final tabular ensembles: weighted top-3 and simple ridge stacking

The metric used for selection is computed downstream by `select_winners.py`.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import os
import random
import time
import warnings as wmodule
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

os.environ.setdefault("LOKY_MAX_CPU_COUNT", str(os.cpu_count() or 1))
os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/agrotrain_mplconfig")
os.environ.setdefault("XDG_CACHE_HOME", "/private/tmp/agrotrain_cache")
DEFAULT_N_JOBS = max((os.cpu_count() or 2) - 1, 1)
wmodule.filterwarnings("ignore", message="Could not find the number of physical cores.*")

from sklearn.cross_decomposition import PLSRegression
from sklearn.ensemble import (
    ExtraTreesRegressor,
    GradientBoostingRegressor,
    HistGradientBoostingRegressor,
    RandomForestRegressor,
)
from sklearn.linear_model import ElasticNet, RidgeCV
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import TimeSeriesSplit
from sklearn.neighbors import KNeighborsRegressor
from sklearn.preprocessing import MinMaxScaler
from sklearn.exceptions import ConvergenceWarning
from sklearn.svm import SVR

from .data_prep import STATIONS, PLATFORM_INPUTS_NO_TELEMETRY, platform_input_columns, prepare_station, to_platform_training_frame
from .features import VARIANTS, add_features
from .treatment_data import load_training_csv_frames

logger = logging.getLogger(__name__)

TARGETS = ("MCD", "TasaBuenos", "TasaSeveros")
WINDOW_SIZES = (2, 3, 5, 7, 10, 14, 21, 28, 35)
HOLDOUT_FRACTION = 0.15
DEFAULT_RNG_SEED = 42
CV_SPLITS = 5
SEQUENCE_CV_SPLITS = 3

# Fixed-size sliding window for CV. Chosen so each fold has roughly the same
# train size as the holdout retrain, removing the "early fold has 30 rows"
# pessimism that distorts rmse_mean upward.
MAX_TRAIN_SIZE_CV = 220

# Production baselines mirroring backend/apps/modelos/services/training_service.py
# (`_build_gb`, `_build_rf`, default UVL window_size for Olivo).
BASELINE_HISTGB_PARAMS = {
    "learning_rate": 0.05,
    "max_depth": 5,
    "max_iter": 300,
    "l2_regularization": 0.0,
    "min_samples_leaf": 20,
}
BASELINE_RF_PARAMS = {
    "n_estimators": 300,
    "max_depth": None,
    "min_samples_split": 4,
    "min_samples_leaf": 2,
    "max_features": "sqrt",
}
BASELINE_LSTM_PARAMS = {
    "model_type": "lstm",
    "units": 128,
    "layers": 1,
    "dropout": 0.2,
    "bidirectional": False,
    "lr": 0.001,
    "batch_size": 32,
    "patience": 20,
}
BASELINE_WINDOW_SIZE = 7
BASELINE_FEATURE_VARIANT = "basic"

SIMPLE_MODEL_SCORE_TOLERANCE = 0.02
ALGO_COMPLEXITY = {
    "ElasticNet": 1,
    "PLSRegression": 1,
    "KNeighbors": 2,
    "SVR": 2,
    "HistGB": 3,
    "GradientBoosting": 3,
    "RandomForest": 4,
    "ExtraTrees": 4,
    "LightGBM": 5,
    "XGBoost": 5,
    "CatBoost": 5,
    "LSTM": 6,
    "GRU": 6,
    "Conv1D": 6,
    "CNN-LSTM": 7,
    "WeightedTop3": 8,
    "StackingTop3": 9,
}


def _rmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    return float(math.sqrt(mean_squared_error(y_true, y_pred)))


@dataclass
class ExperimentResult:
    station: str
    target: str
    algo: str
    variant_id: str
    window_size: int
    feature_variant: str
    params: dict[str, Any]
    rmse_mean: float = float("nan")
    rmse_std: float = float("nan")
    r2_mean: float = float("nan")
    mae_mean: float = float("nan")
    holdout_rmse: float = float("nan")
    holdout_r2: float = float("nan")
    n_train_avg: float = 0.0
    n_folds: int = 0
    train_time_sec: float = 0.0
    feature_importances: dict[str, float] = field(default_factory=dict)
    error: str = ""

    def to_row(self) -> dict[str, Any]:
        d = asdict(self)
        d["params"] = json.dumps(self.params, sort_keys=True)
        d["feature_importances"] = json.dumps(self.feature_importances, sort_keys=True)
        return d


@dataclass
class TabularCandidate:
    station: str
    target: str
    algo: str
    variant_id: str
    window_size: int
    feature_variant: str
    params: dict[str, Any]
    build_fn: Callable[[dict[str, Any]], Any]
    rmse_mean: float
    rmse_std: float
    holdout_rmse: float


# ─────────────────────────────────────── parameter sampling ──

def _sample_histgb(rng: random.Random) -> dict[str, Any]:
    return {
        "learning_rate": rng.choice([0.01, 0.03, 0.05, 0.08, 0.12]),
        "max_depth": rng.choice([2, 3, 5, 8, None]),
        "max_iter": rng.choice([300, 600, 1200, 2000]),
        "l2_regularization": rng.choice([0.0, 0.01, 0.1, 0.5, 1.0]),
        "min_samples_leaf": rng.choice([5, 10, 20, 30, 50]),
    }


def _sample_rf(rng: random.Random) -> dict[str, Any]:
    return {
        "n_estimators": rng.choice([300, 600, 1000]),
        "max_depth": rng.choice([None, 8, 14, 20, 30]),
        "min_samples_split": rng.choice([2, 4, 8]),
        "min_samples_leaf": rng.choice([1, 2, 4, 8]),
        "max_features": rng.choice(["sqrt", 0.5, 0.8, 1.0]),
    }


def _sample_extra_trees(rng: random.Random) -> dict[str, Any]:
    return {
        "n_estimators": rng.choice([300, 600, 1000]),
        "max_depth": rng.choice([None, 8, 14, 20, 30]),
        "min_samples_split": rng.choice([2, 4, 8]),
        "min_samples_leaf": rng.choice([1, 2, 4, 8]),
        "max_features": rng.choice(["sqrt", 0.5, 0.8, 1.0]),
        "bootstrap": rng.choice([False, True]),
    }


def _sample_gradient_boosting(rng: random.Random) -> dict[str, Any]:
    return {
        "learning_rate": rng.choice([0.01, 0.03, 0.05, 0.08, 0.12]),
        "n_estimators": rng.choice([300, 600, 1200, 2000]),
        "max_depth": rng.choice([2, 3, 5, 8]),
        "min_samples_leaf": rng.choice([1, 2, 4, 8, 16]),
        "subsample": rng.choice([0.7, 0.85, 1.0]),
        "max_features": rng.choice([None, "sqrt", 0.5, 0.8]),
    }


def _sample_knn(rng: random.Random) -> dict[str, Any]:
    return {
        "n_neighbors": rng.choice([3, 5, 7, 11, 15, 21]),
        "weights": rng.choice(["uniform", "distance"]),
        "p": rng.choice([1, 2]),
    }


def _sample_svr(rng: random.Random) -> dict[str, Any]:
    return {
        "kernel": rng.choice(["rbf", "linear"]),
        "C": rng.choice([0.1, 1.0, 3.0, 10.0, 30.0, 100.0]),
        "epsilon": rng.choice([0.01, 0.05, 0.1, 0.2]),
        "gamma": rng.choice(["scale", "auto"]),
    }


def _sample_elasticnet(rng: random.Random) -> dict[str, Any]:
    return {
        "alpha": rng.choice([0.0001, 0.001, 0.01, 0.1, 1.0]),
        "l1_ratio": rng.choice([0.05, 0.15, 0.3, 0.5, 0.75, 0.9]),
        "max_iter": 20000,
    }


def _sample_pls(rng: random.Random) -> dict[str, Any]:
    return {
        "n_components": rng.choice([1, 2, 3, 5, 8, 12]),
        "scale": False,
    }


def _sample_lightgbm(rng: random.Random) -> dict[str, Any]:
    return {
        "learning_rate": rng.choice([0.01, 0.03, 0.05, 0.1]),
        "num_leaves": rng.choice([15, 31, 63, 127]),
        "max_depth": rng.choice([-1, 5, 8, 12]),
        "min_data_in_leaf": rng.choice([5, 10, 20, 40]),
        "n_estimators": rng.choice([300, 600, 1200]),
        "reg_lambda": rng.choice([0.0, 0.1, 1.0]),
    }


def _sample_xgboost(rng: random.Random) -> dict[str, Any]:
    return {
        "learning_rate": rng.choice([0.01, 0.03, 0.05, 0.08, 0.12]),
        "max_depth": rng.choice([2, 3, 5, 8]),
        "n_estimators": rng.choice([300, 600, 1200]),
        "subsample": rng.choice([0.7, 0.85, 1.0]),
        "colsample_bytree": rng.choice([0.6, 0.8, 1.0]),
        "reg_lambda": rng.choice([0.1, 1.0, 5.0]),
        "min_child_weight": rng.choice([1, 3, 7]),
    }


def _sample_catboost(rng: random.Random) -> dict[str, Any]:
    return {
        "learning_rate": rng.choice([0.01, 0.03, 0.05, 0.08, 0.12]),
        "depth": rng.choice([3, 5, 7, 9]),
        "iterations": rng.choice([300, 600, 1200]),
        "l2_leaf_reg": rng.choice([1.0, 3.0, 10.0]),
    }


def _sample_sequence(rng: random.Random) -> dict[str, Any]:
    return {
        "model_type": rng.choice(["lstm", "gru", "conv1d", "cnn_lstm"]),
        "units": rng.choice([32, 64, 128]),
        "layers": rng.choice([1, 2]),
        "dropout": rng.choice([0.1, 0.2, 0.35]),
        "bidirectional": rng.choice([False, True]),
        "lr": rng.choice([0.0003, 0.0005, 0.001, 0.002]),
        "batch_size": rng.choice([8, 16, 32]),
        "patience": rng.choice([20, 30, 40]),
    }


# ─────────────────────────────────────── estimators ──

def _build_histgb(params: dict[str, Any]) -> Any:
    return HistGradientBoostingRegressor(
        random_state=42,
        early_stopping=True,
        **params,
    )


def _build_rf(params: dict[str, Any]) -> Any:
    return RandomForestRegressor(
        n_jobs=DEFAULT_N_JOBS,
        random_state=42,
        **params,
    )


def _build_extra_trees(params: dict[str, Any]) -> Any:
    return ExtraTreesRegressor(
        n_jobs=DEFAULT_N_JOBS,
        random_state=42,
        **params,
    )


def _build_gradient_boosting(params: dict[str, Any]) -> Any:
    return GradientBoostingRegressor(random_state=42, **params)


def _build_knn(params: dict[str, Any]) -> Any:
    return KNeighborsRegressor(**params)


def _build_svr(params: dict[str, Any]) -> Any:
    return SVR(**params)


def _build_elasticnet(params: dict[str, Any]) -> Any:
    return ElasticNet(random_state=42, **params)


def _build_pls(params: dict[str, Any]) -> Any:
    return PLSRegression(**params)


def _build_lightgbm(params: dict[str, Any]) -> Any:
    import lightgbm as lgb
    return lgb.LGBMRegressor(random_state=42, n_jobs=DEFAULT_N_JOBS, verbose=-1, **params)


def _build_xgboost(params: dict[str, Any]) -> Any:
    import xgboost as xgb
    return xgb.XGBRegressor(
        random_state=42,
        n_jobs=DEFAULT_N_JOBS,
        objective="reg:squarederror",
        verbosity=0,
        **params,
    )


def _build_catboost(params: dict[str, Any]) -> Any:
    import catboost as cb
    return cb.CatBoostRegressor(random_seed=42, loss_function="RMSE", verbose=False, **params)


def _predict_1d(estimator: Any, X: np.ndarray) -> np.ndarray:
    return np.asarray(estimator.predict(X), dtype=float).reshape(-1)


def _extract_feature_importances(estimator: Any, feature_names: list[str], top_n: int = 15) -> dict[str, float]:
    values: np.ndarray | None = None
    if hasattr(estimator, "feature_importances_"):
        values = np.asarray(estimator.feature_importances_, dtype=float).reshape(-1)
    elif hasattr(estimator, "coef_"):
        values = np.abs(np.asarray(estimator.coef_, dtype=float).reshape(-1))

    if values is None or len(values) != len(feature_names):
        return {}

    total = float(np.nansum(np.abs(values)))
    if not total or not np.isfinite(total):
        return {}

    order = np.argsort(np.abs(values))[::-1][:top_n]
    return {
        feature_names[i]: float(abs(values[i]) / total)
        for i in order
        if np.isfinite(values[i]) and abs(values[i]) > 0
    }


# ─────────────────────────────────────── tabular pipeline ──

# Registries reused by treatment_winners.py to re-evaluate stored configs per parcela.
TABULAR_BUILDERS: dict[str, Callable[[dict[str, Any]], Any]] = {
    "HistGB": _build_histgb,
    "RandomForest": _build_rf,
    "ExtraTrees": _build_extra_trees,
    "GradientBoosting": _build_gradient_boosting,
    "KNeighbors": _build_knn,
    "SVR": _build_svr,
    "ElasticNet": _build_elasticnet,
    "PLSRegression": _build_pls,
    "LightGBM": _build_lightgbm,
    "XGBoost": _build_xgboost,
    "CatBoost": _build_catboost,
}
SEQUENCE_ALGOS: frozenset[str] = frozenset({"LSTM", "GRU", "Conv1D", "CNN-LSTM"})


def _prepare_xy(
    station_df: pd.DataFrame,
    target: str,
    window_size: int,
    feature_variant: str,
    inputs: list[str],
) -> tuple[pd.DataFrame, pd.Series]:
    """
    Per-target preparation: only the current target plus environmental inputs are kept.
    Other targets (MCD/TB/TS) are dropped — they shouldn't leak into a per-target model
    because they're co-derived from the same dendrometer signal (information leakage).
    Mirrors `training_service._train_sklearn` for the single-target case.
    """
    if feature_variant == "target_only":
        base_cols = [target]
    else:
        base_cols = [target] + [c for c in inputs if c in station_df.columns and c != target]
    df_t = station_df[["date"] + base_cols].dropna(subset=base_cols).copy()
    df_t = add_features(df_t, base_cols, window_size, feature_variant)
    df_t = df_t.drop(columns=["date"], errors="ignore").dropna()

    if df_t.empty or target not in df_t.columns:
        return pd.DataFrame(), pd.Series(dtype=float)

    y = df_t[target]
    X = df_t.drop(columns=[target])
    return X, y


def _fit_estimator(
    build_fn: Callable[[dict[str, Any]], Any],
    params: dict[str, Any],
    x_train: np.ndarray,
    y_train: np.ndarray,
) -> Any:
    fit_params = dict(params)
    if build_fn is _build_pls and "n_components" in fit_params:
        fit_params["n_components"] = max(1, min(int(fit_params["n_components"]), x_train.shape[1], len(y_train) - 1))
    estimator = build_fn(fit_params)
    estimator.fit(x_train, y_train)
    return estimator


def _eval_tabular(
    build_fn: Callable[[dict[str, Any]], Any],
    params: dict[str, Any],
    X: pd.DataFrame,
    y: pd.Series,
    n_splits: int,
    max_train_size: int | None = None,
    abort_rmse_threshold: float | None = None,
) -> tuple[dict[str, float], int, float, int, str]:
    """
    K-fold TimeSeriesSplit on `X, y`; returns mean/std metrics + average train size + total time.

    `max_train_size` caps each fold's training window so early folds aren't penalised
    for tiny train sets. With it set, CV becomes a fair sliding-window estimate
    closer to what the holdout fit sees.
    """
    if len(X) < n_splits + 5:
        return {}, 0, 0.0, 0, ""

    rmses, r2s, maes, n_trains = [], [], [], []
    t0 = time.perf_counter()
    stop_reason = ""
    for train_idx, val_idx in iter_temporal_splits(len(X), n_splits=n_splits, max_train_size=max_train_size):
        x_tr, x_vl = X.iloc[train_idx].values, X.iloc[val_idx].values
        y_tr, y_vl = y.iloc[train_idx].values, y.iloc[val_idx].values

        scaler = MinMaxScaler()
        x_tr_s = scaler.fit_transform(x_tr)
        x_vl_s = scaler.transform(x_vl)

        est = _fit_estimator(build_fn, params, x_tr_s, y_tr)
        y_pred = _predict_1d(est, x_vl_s)

        rmses.append(_rmse(y_vl, y_pred))
        r2s.append(r2_score(y_vl, y_pred))
        maes.append(mean_absolute_error(y_vl, y_pred))
        n_trains.append(len(y_tr))

        if abort_rmse_threshold is not None and len(rmses) >= 2 and float(np.mean(rmses)) > abort_rmse_threshold:
            stop_reason = "early_stopped_worse_than_baseline"
            break

    elapsed = time.perf_counter() - t0
    if stop_reason:
        return {}, int(np.mean(n_trains)) if n_trains else 0, elapsed, len(rmses), stop_reason
    return (
        {
            "rmse_mean": float(np.mean(rmses)),
            "rmse_std": float(np.std(rmses)),
            "r2_mean": float(np.mean(r2s)),
            "mae_mean": float(np.mean(maes)),
        },
        int(np.mean(n_trains)),
        elapsed,
        len(rmses),
        "",
    )


def _eval_holdout_tabular(
    build_fn: Callable[[dict[str, Any]], Any],
    params: dict[str, Any],
    X: pd.DataFrame,
    y: pd.Series,
    holdout_idx: int,
) -> tuple[float, float, dict[str, float]]:
    if holdout_idx <= 0 or holdout_idx >= len(X):
        return float("nan"), float("nan"), {}
    x_tr, x_h = X.iloc[:holdout_idx].values, X.iloc[holdout_idx:].values
    y_tr, y_h = y.iloc[:holdout_idx].values, y.iloc[holdout_idx:].values
    scaler = MinMaxScaler()
    x_tr_s = scaler.fit_transform(x_tr)
    x_h_s = scaler.transform(x_h)
    est = _fit_estimator(build_fn, params, x_tr_s, y_tr)
    y_pred = _predict_1d(est, x_h_s)
    importances = _extract_feature_importances(est, list(X.columns))
    return _rmse(y_h, y_pred), float(r2_score(y_h, y_pred)), importances


def iter_temporal_splits(
    n_samples: int,
    n_splits: int = CV_SPLITS,
    max_train_size: int | None = None,
) -> list[tuple[np.ndarray, np.ndarray]]:
    splitter = TimeSeriesSplit(n_splits=n_splits, max_train_size=max_train_size)
    return list(splitter.split(np.arange(n_samples)))


# ─────────────────────────────────────── LSTM pipeline ──

def _build_lstm_model(params: dict[str, Any], input_shape: tuple[int, int]):
    import tensorflow as tf
    from tensorflow.keras.layers import LSTM, GRU, Conv1D, Dense, Dropout, Flatten, Input, MaxPooling1D, Bidirectional
    from tensorflow.keras.models import Model
    from tensorflow.keras.losses import Huber

    inp = Input(shape=input_shape)
    x = inp
    model_type = params.get("model_type", "lstm")

    if model_type == "conv1d":
        for _ in range(params["layers"]):
            x = Conv1D(params["units"], kernel_size=3, activation="relu", padding="causal")(x)
            x = Dropout(params["dropout"])(x)
        x = Flatten()(x)
    elif model_type == "cnn_lstm":
        x = Conv1D(params["units"], kernel_size=3, activation="relu", padding="causal")(x)
        if input_shape[0] >= 4:
            x = MaxPooling1D(pool_size=2)(x)
        x = Dropout(params["dropout"])(x)
        x = LSTM(params["units"], activation="tanh")(x)
        x = Dropout(params["dropout"])(x)
    else:
        rnn_cls = GRU if model_type == "gru" else LSTM
        for layer_idx in range(params["layers"]):
            return_sequences = layer_idx < params["layers"] - 1
            rnn = rnn_cls(params["units"], activation="tanh", return_sequences=return_sequences)
            if params.get("bidirectional", False):
                rnn = Bidirectional(rnn)
            x = rnn(x)
            x = Dropout(params["dropout"])(x)

    x = Dense(64, activation="relu")(x)
    out = Dense(1)(x)
    model = Model(inp, out)
    model.compile(optimizer=tf.keras.optimizers.Adam(params["lr"]), loss=Huber())
    return model


def _eval_lstm(
    params: dict[str, Any],
    station_df: pd.DataFrame,
    target: str,
    window_size: int,
    inputs: list[str],
    holdout_frac: float,
    n_splits: int = 3,
) -> tuple[dict[str, float], int, float, float, float]:
    import tensorflow as tf
    from tensorflow.keras.callbacks import EarlyStopping

    tf.keras.utils.set_random_seed(DEFAULT_RNG_SEED)

    all_cols = [target] + [c for c in inputs if c in station_df.columns and c != target]
    if target not in station_df.columns:
        return {}, 0, 0.0, float("nan"), float("nan")

    df_clean = station_df[all_cols].dropna().reset_index(drop=True)
    if len(df_clean) < window_size + n_splits * 10 + 20:
        return {}, 0, 0.0, float("nan"), float("nan")

    holdout_size = max(window_size + 10, int(len(df_clean) * holdout_frac))
    cv_df = df_clean.iloc[:-holdout_size]
    holdout_df = df_clean.iloc[-(holdout_size + window_size):]

    rmses, r2s, maes, n_trains = [], [], [], []
    t0 = time.perf_counter()
    target_idx = all_cols.index(target)

    splitter = TimeSeriesSplit(n_splits=n_splits)
    for train_idx, val_idx in splitter.split(cv_df):
        if len(train_idx) <= window_size or len(val_idx) <= window_size:
            continue
        train_part = cv_df.iloc[train_idx]
        val_part = cv_df.iloc[val_idx]

        scaler_x = MinMaxScaler().fit(train_part)
        scaler_y = MinMaxScaler().fit(train_part[[target]])
        tr_s = scaler_x.transform(train_part)
        vl_s = scaler_x.transform(val_part)

        def windows(arr: np.ndarray) -> np.ndarray:
            return np.array([arr[i : i + window_size] for i in range(len(arr) - window_size)], dtype="float32")

        X_tr = windows(tr_s)
        X_vl = windows(vl_s)
        y_tr = scaler_y.transform(train_part[[target]].values[window_size:]).ravel().astype("float32")
        y_vl = scaler_y.transform(val_part[[target]].values[window_size:]).ravel().astype("float32")
        if len(X_tr) < 5 or len(X_vl) < 1:
            continue

        tf.keras.backend.clear_session()
        model = _build_lstm_model(params, (window_size, len(all_cols)))
        model.fit(
            X_tr, y_tr,
            validation_data=(X_vl, y_vl),
            epochs=200,
            batch_size=params["batch_size"],
            callbacks=[
                EarlyStopping(
                    monitor="val_loss",
                    patience=params.get("patience", 20),
                    restore_best_weights=True,
                    min_delta=1e-4,
                )
            ],
            verbose=0,
        )
        y_pred = scaler_y.inverse_transform(model.predict(X_vl, verbose=0)).ravel()
        y_true = scaler_y.inverse_transform(y_vl.reshape(-1, 1)).ravel()
        rmses.append(_rmse(y_true, y_pred))
        r2s.append(r2_score(y_true, y_pred))
        maes.append(mean_absolute_error(y_true, y_pred))
        n_trains.append(len(y_tr))
    elapsed = time.perf_counter() - t0

    if not rmses:
        return {}, 0, elapsed, float("nan"), float("nan")

    # Holdout: train on full CV portion, evaluate on holdout window
    scaler_x = MinMaxScaler().fit(cv_df)
    scaler_y = MinMaxScaler().fit(cv_df[[target]])
    cv_scaled = scaler_x.transform(cv_df)
    ho_scaled = scaler_x.transform(holdout_df)

    def windows(arr: np.ndarray) -> np.ndarray:
        return np.array([arr[i : i + window_size] for i in range(len(arr) - window_size)], dtype="float32")

    X_cv = windows(cv_scaled)
    y_cv = scaler_y.transform(cv_df[[target]].values[window_size:]).ravel().astype("float32")
    X_ho = windows(ho_scaled)
    y_ho_scaled = scaler_y.transform(holdout_df[[target]].values[window_size:]).ravel().astype("float32")

    tf.keras.backend.clear_session()
    model = _build_lstm_model(params, (window_size, len(all_cols)))
    model.fit(
        X_cv, y_cv,
        epochs=200,
        batch_size=params["batch_size"],
        callbacks=[
            EarlyStopping(
                monitor="loss",
                patience=params.get("patience", 20),
                restore_best_weights=True,
                min_delta=1e-4,
            )
        ],
        verbose=0,
    )
    y_ho_pred = scaler_y.inverse_transform(model.predict(X_ho, verbose=0)).ravel()
    y_ho_true = scaler_y.inverse_transform(y_ho_scaled.reshape(-1, 1)).ravel()
    holdout_rmse = _rmse(y_ho_true, y_ho_pred)
    holdout_r2 = float(r2_score(y_ho_true, y_ho_pred)) if len(y_ho_true) > 1 else float("nan")

    return (
        {
            "rmse_mean": float(np.mean(rmses)),
            "rmse_std": float(np.std(rmses)),
            "r2_mean": float(np.mean(r2s)),
            "mae_mean": float(np.mean(maes)),
        },
        int(np.mean(n_trains)),
        elapsed,
        holdout_rmse,
        holdout_r2,
    )


# ─────────────────────────────────────── orchestration ──

def temporal_holdout_index(n_samples: int, holdout_fraction: float = HOLDOUT_FRACTION) -> int:
    """Return the index where the final temporal holdout starts."""
    if n_samples <= 1:
        return n_samples
    split = int(n_samples * (1.0 - holdout_fraction))
    return min(max(split, 1), n_samples - 1)


def _input_features(station_df: pd.DataFrame) -> list[str]:
    """UVL-derived non-telemetry training inputs, matching the platform CSV contract."""
    return platform_input_columns(station_df)


def iter_station_frames(cfg: "RunConfig"):
    """
    Yield `(station, platform_df)` for each requested station.

    Two sources, selected by `cfg.use_training_csvs`:
    - False (default): rebuild each station from its raw 24 CSVs in `csvs/` via `prepare_station`.
    - True: read the per-treatment `entrenamiento_*.csv` and split by the `station` column.
      One series per parcela; parcels are never concatenated.
    """
    if cfg.use_training_csvs:
        frames = load_training_csv_frames()
        for station in cfg.stations:
            df = frames.get(station)
            if df is None:
                logger.error("Station %s not present in training CSVs; skipping", station)
                continue
            yield station, df
        return

    for station in cfg.stations:
        try:
            station_df_raw, prep_warnings = prepare_station(station)
        except Exception as exc:
            logger.error("Station %s failed to prepare: %s", station, exc)
            continue
        for w in prep_warnings:
            logger.info("[%s] %s", station, w)
        yield station, to_platform_training_frame(
            station_df_raw, targets=TARGETS, input_cols=PLATFORM_INPUTS_NO_TELEMETRY
        )


@dataclass
class RunConfig:
    quick: bool = False
    overnight: bool = False
    stations: list[str] = field(default_factory=lambda: list(STATIONS))
    targets: list[str] = field(default_factory=lambda: list(TARGETS))
    histgb_samples: int = 30
    rf_samples: int = 12
    extra_trees_samples: int = 12
    gradient_boosting_samples: int = 20
    knn_samples: int = 8
    svr_samples: int = 8
    elasticnet_samples: int = 8
    pls_samples: int = 8
    lightgbm_samples: int = 20
    xgboost_samples: int = 20
    catboost_samples: int = 20
    sequence_samples: int = 4
    window_sizes: list[int] = field(default_factory=lambda: list(WINDOW_SIZES))
    feature_variants: list[str] = field(default_factory=lambda: list(VARIANTS))
    skip_lstm: bool = False
    include_optional_boosters: bool = False
    enable_ensembles: bool = True
    seed: int = DEFAULT_RNG_SEED
    use_training_csvs: bool = False


def _quick_overrides(cfg: RunConfig) -> RunConfig:
    cfg.stations = cfg.stations[:1]
    cfg.targets = ["TasaBuenos"]
    cfg.histgb_samples = 2
    cfg.rf_samples = 1
    cfg.extra_trees_samples = 1
    cfg.gradient_boosting_samples = 1
    cfg.knn_samples = 1
    cfg.svr_samples = 1
    cfg.elasticnet_samples = 1
    cfg.pls_samples = 1
    cfg.lightgbm_samples = 0
    cfg.xgboost_samples = 0
    cfg.catboost_samples = 0
    cfg.sequence_samples = 0
    cfg.window_sizes = [3, 7]
    cfg.feature_variants = ["basic", "target_only"]
    cfg.enable_ensembles = False
    return cfg


def _medium_overrides(cfg: RunConfig) -> RunConfig:
    """Búsqueda media: explora bien (random search se aplana pasadas ~30 muestras/algo) en ~2h.
    Sin CatBoost (lento, no expresable en producción) ni secuenciales por defecto."""
    cfg.histgb_samples = 30
    cfg.rf_samples = 15
    cfg.extra_trees_samples = 15
    cfg.gradient_boosting_samples = 12
    cfg.knn_samples = 8
    cfg.svr_samples = 12
    cfg.elasticnet_samples = 12
    cfg.pls_samples = 10
    cfg.lightgbm_samples = 20
    cfg.xgboost_samples = 20
    cfg.catboost_samples = 0
    cfg.sequence_samples = 0
    cfg.window_sizes = list(WINDOW_SIZES)
    cfg.feature_variants = list(VARIANTS)
    cfg.enable_ensembles = True
    return cfg


def _overnight_overrides(cfg: RunConfig) -> RunConfig:
    cfg.overnight = True
    cfg.histgb_samples = 90
    cfg.rf_samples = 45
    cfg.extra_trees_samples = 45
    cfg.gradient_boosting_samples = 60
    cfg.knn_samples = 25
    cfg.svr_samples = 25
    cfg.elasticnet_samples = 25
    cfg.pls_samples = 20
    cfg.lightgbm_samples = 50
    cfg.xgboost_samples = 50
    cfg.catboost_samples = 40
    cfg.sequence_samples = 12
    cfg.window_sizes = list(WINDOW_SIZES)
    cfg.feature_variants = list(VARIANTS)
    cfg.enable_ensembles = True
    return cfg


def _candidate_score(candidate: TabularCandidate) -> float:
    return candidate.rmse_mean + 0.5 * candidate.rmse_std


def _candidate_passes_holdout(candidate: TabularCandidate) -> bool:
    if not np.isfinite(candidate.rmse_mean):
        return False
    if not np.isfinite(candidate.holdout_rmse):
        return True
    return candidate.holdout_rmse <= 1.3 * candidate.rmse_mean


def _holdout_pos_from_index(X: pd.DataFrame, holdout_start_idx: int) -> int:
    index_values = np.asarray(X.index)
    return int(np.searchsorted(index_values, holdout_start_idx, side="left"))


def _optional_importable(module_name: str) -> bool:
    try:
        __import__(module_name)
        return True
    except ImportError:
        return False


def _prediction_matrix(
    prepared: list[tuple[TabularCandidate, pd.DataFrame, pd.Series]],
    train_labels: list[int],
    pred_labels: list[int],
) -> np.ndarray:
    preds: list[np.ndarray] = []
    for candidate, X, y in prepared:
        scaler = MinMaxScaler()
        x_train = scaler.fit_transform(X.loc[train_labels].values)
        x_pred = scaler.transform(X.loc[pred_labels].values)
        estimator = _fit_estimator(candidate.build_fn, candidate.params, x_train, y.loc[train_labels].values)
        preds.append(_predict_1d(estimator, x_pred))
    return np.column_stack(preds)


def _common_index(prepared: list[tuple[TabularCandidate, pd.DataFrame, pd.Series]]) -> list[int]:
    if not prepared:
        return []
    common = set(prepared[0][1].index)
    for _candidate, X, _y in prepared[1:]:
        common &= set(X.index)
    return sorted(int(i) for i in common)


def _ensemble_members_payload(candidates: list[TabularCandidate], weights: np.ndarray | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "members": [
            {
                "algo": c.algo,
                "variant_id": c.variant_id,
                "window_size": c.window_size,
                "feature_variant": c.feature_variant,
                "params": c.params,
                "score": _candidate_score(c),
            }
            for c in candidates
        ]
    }
    if weights is not None:
        payload["weights"] = {
            c.variant_id: float(w)
            for c, w in zip(candidates, weights, strict=False)
        }
    return payload


def _stacking_meta_predictions(
    prepared: list[tuple[TabularCandidate, pd.DataFrame, pd.Series]],
    labels: list[int],
    n_splits: int = 3,
) -> tuple[RidgeCV | None, np.ndarray, np.ndarray]:
    if len(labels) < n_splits + 8:
        return None, np.empty((0, len(prepared))), np.empty(0)

    oof_pred_parts: list[np.ndarray] = []
    oof_true_parts: list[np.ndarray] = []
    for train_pos, val_pos in iter_temporal_splits(len(labels), n_splits=n_splits, max_train_size=MAX_TRAIN_SIZE_CV):
        train_labels = [labels[i] for i in train_pos]
        val_labels = [labels[i] for i in val_pos]
        if len(train_labels) < 5 or not val_labels:
            continue
        base_preds = _prediction_matrix(prepared, train_labels, val_labels)
        y_true = prepared[0][2].loc[val_labels].values
        oof_pred_parts.append(base_preds)
        oof_true_parts.append(y_true)

    if not oof_pred_parts:
        return None, np.empty((0, len(prepared))), np.empty(0)

    oof_preds = np.vstack(oof_pred_parts)
    oof_true = np.concatenate(oof_true_parts)
    if len(oof_true) < len(prepared) + 3:
        return None, oof_preds, oof_true

    meta = RidgeCV(alphas=[0.01, 0.1, 1.0, 10.0, 100.0])
    meta.fit(oof_preds, oof_true)
    return meta, oof_preds, oof_true


def _stacking_outer_predict(
    prepared: list[tuple[TabularCandidate, pd.DataFrame, pd.Series]],
    train_labels: list[int],
    val_labels: list[int],
) -> np.ndarray | None:
    inner_splits = min(3, max(2, len(train_labels) // 20))
    meta, _oof_preds, _oof_true = _stacking_meta_predictions(prepared, train_labels, n_splits=inner_splits)
    if meta is None:
        return None
    base_val = _prediction_matrix(prepared, train_labels, val_labels)
    return np.asarray(meta.predict(base_val), dtype=float).reshape(-1)


def _run_tabular_ensembles(
    candidates: list[TabularCandidate],
    station_df: pd.DataFrame,
    target: str,
    inputs: list[str],
    holdout_start_idx: int,
) -> list[ExperimentResult]:
    valid = [c for c in candidates if _candidate_passes_holdout(c)]
    valid.sort(key=_candidate_score)
    top = valid[:3]
    if len(top) < 3:
        return []

    scores = np.array([max(_candidate_score(c), 1e-9) for c in top], dtype=float)
    weights = (1.0 / scores) / np.sum(1.0 / scores)
    cv_df = station_df.iloc[:holdout_start_idx]
    prepared_cv = [
        (c, *_prepare_xy(cv_df, target, c.window_size, c.feature_variant, inputs))
        for c in top
    ]
    prepared_cv = [(c, X, y) for c, X, y in prepared_cv if not X.empty]
    common_cv_idx = _common_index(prepared_cv)
    if len(prepared_cv) != len(top) or len(common_cv_idx) < CV_SPLITS + 8:
        return []

    results: list[ExperimentResult] = []
    weighted_rmses: list[float] = []
    weighted_r2s: list[float] = []
    weighted_maes: list[float] = []
    stacking_rmses: list[float] = []
    stacking_r2s: list[float] = []
    stacking_maes: list[float] = []
    n_trains: list[int] = []
    t0 = time.perf_counter()

    for train_pos, val_pos in iter_temporal_splits(len(common_cv_idx), n_splits=CV_SPLITS, max_train_size=MAX_TRAIN_SIZE_CV):
        train_labels = [common_cv_idx[i] for i in train_pos]
        val_labels = [common_cv_idx[i] for i in val_pos]
        base_preds = _prediction_matrix(prepared_cv, train_labels, val_labels)
        y_true = prepared_cv[0][2].loc[val_labels].values

        weighted_pred = base_preds @ weights
        weighted_rmses.append(_rmse(y_true, weighted_pred))
        weighted_r2s.append(r2_score(y_true, weighted_pred))
        weighted_maes.append(mean_absolute_error(y_true, weighted_pred))

        stacking_pred = _stacking_outer_predict(prepared_cv, train_labels, val_labels)
        if stacking_pred is not None:
            stacking_rmses.append(_rmse(y_true, stacking_pred))
            stacking_r2s.append(r2_score(y_true, stacking_pred))
            stacking_maes.append(mean_absolute_error(y_true, stacking_pred))

        n_trains.append(len(train_labels))

    prepared_full = [
        (c, *_prepare_xy(station_df, target, c.window_size, c.feature_variant, inputs))
        for c in top
    ]
    prepared_full = [(c, X, y) for c, X, y in prepared_full if not X.empty]
    common_full_idx = _common_index(prepared_full)
    train_full_labels = [i for i in common_full_idx if i < holdout_start_idx]
    holdout_labels = [i for i in common_full_idx if i >= holdout_start_idx]

    weighted_holdout_rmse = float("nan")
    weighted_holdout_r2 = float("nan")
    stacking_holdout_rmse = float("nan")
    stacking_holdout_r2 = float("nan")
    if len(prepared_full) == len(top) and len(train_full_labels) > 5 and len(holdout_labels) > 1:
        holdout_base = _prediction_matrix(prepared_full, train_full_labels, holdout_labels)
        y_holdout = prepared_full[0][2].loc[holdout_labels].values

        weighted_holdout_pred = holdout_base @ weights
        weighted_holdout_rmse = _rmse(y_holdout, weighted_holdout_pred)
        weighted_holdout_r2 = float(r2_score(y_holdout, weighted_holdout_pred))

        meta, _oof_preds, _oof_true = _stacking_meta_predictions(prepared_cv, common_cv_idx, n_splits=CV_SPLITS)
        if meta is not None:
            stacking_holdout_pred = np.asarray(meta.predict(holdout_base), dtype=float).reshape(-1)
            stacking_holdout_rmse = _rmse(y_holdout, stacking_holdout_pred)
            stacking_holdout_r2 = float(r2_score(y_holdout, stacking_holdout_pred))

    elapsed = time.perf_counter() - t0
    if weighted_rmses:
        results.append(
            ExperimentResult(
                station=top[0].station,
                target=target,
                algo="WeightedTop3",
                variant_id="WeightedTop3#FINAL",
                window_size=top[0].window_size,
                feature_variant="ensemble",
                params=_ensemble_members_payload(top, weights),
                rmse_mean=float(np.mean(weighted_rmses)),
                rmse_std=float(np.std(weighted_rmses)),
                r2_mean=float(np.mean(weighted_r2s)),
                mae_mean=float(np.mean(weighted_maes)),
                holdout_rmse=weighted_holdout_rmse,
                holdout_r2=weighted_holdout_r2,
                n_train_avg=float(np.mean(n_trains)),
                n_folds=len(weighted_rmses),
                train_time_sec=float(elapsed),
            )
        )

    if stacking_rmses and np.isfinite(stacking_holdout_rmse):
        finite_member_holdouts = [c.holdout_rmse for c in top if np.isfinite(c.holdout_rmse)]
        best_member_holdout = min(finite_member_holdouts) if finite_member_holdouts else float("inf")
        if stacking_holdout_rmse < best_member_holdout:
            results.append(
                ExperimentResult(
                    station=top[0].station,
                    target=target,
                    algo="StackingTop3",
                    variant_id="StackingTop3#FINAL",
                    window_size=top[0].window_size,
                    feature_variant="ensemble",
                    params=_ensemble_members_payload(top),
                    rmse_mean=float(np.mean(stacking_rmses)),
                    rmse_std=float(np.std(stacking_rmses)),
                    r2_mean=float(np.mean(stacking_r2s)),
                    mae_mean=float(np.mean(stacking_maes)),
                    holdout_rmse=stacking_holdout_rmse,
                    holdout_r2=stacking_holdout_r2,
                    n_train_avg=float(np.mean(n_trains)),
                    n_folds=len(stacking_rmses),
                    train_time_sec=float(elapsed),
                )
            )

    return results


def run(cfg: RunConfig, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    out_csv = output_dir / "results.csv"
    rng = random.Random(cfg.seed)
    wmodule.filterwarnings("ignore", category=pd.errors.PerformanceWarning)
    wmodule.filterwarnings("ignore", category=ConvergenceWarning)

    optional_boosters: list[tuple[str, Callable[[random.Random], dict[str, Any]], Callable[[dict[str, Any]], Any], int]] = []
    if cfg.include_optional_boosters:
        optional_specs = [
            ("LightGBM", "lightgbm", _sample_lightgbm, _build_lightgbm, cfg.lightgbm_samples),
            ("XGBoost", "xgboost", _sample_xgboost, _build_xgboost, cfg.xgboost_samples),
            ("CatBoost", "catboost", _sample_catboost, _build_catboost, cfg.catboost_samples),
        ]
        for algo_name, module_name, sampler, builder, n_samples in optional_specs:
            if n_samples <= 0:
                continue
            if _optional_importable(module_name):
                optional_boosters.append((algo_name, sampler, builder, n_samples))
            else:
                logger.warning("%s not installed; skipping optional booster %s", module_name, algo_name)

    has_tf = False
    if not cfg.skip_lstm and cfg.sequence_samples > 0:
        try:
            import tensorflow  # noqa: F401
            has_tf = True
        except ImportError:
            logger.warning("tensorflow not installed; skipping sequential variants")

    rows_buffer: list[dict[str, Any]] = []

    def _flush() -> None:
        if not rows_buffer:
            return
        df_buf = pd.DataFrame(rows_buffer)
        if out_csv.exists():
            df_buf.to_csv(out_csv, mode="a", header=False, index=False)
        else:
            df_buf.to_csv(out_csv, index=False)
        rows_buffer.clear()

    for station, station_df in iter_station_frames(cfg):
        inputs = _input_features(station_df)
        n = len(station_df)
        holdout_idx_for_tabular = temporal_holdout_index(n, HOLDOUT_FRACTION)
        logger.info(
            "Station %s: rows=%d, holdout_idx=%d, platform_inputs=%s",
            station,
            n,
            holdout_idx_for_tabular,
            ",".join(inputs),
        )

        for target in cfg.targets:
            tabular_specs = [
                ("HistGB", _sample_histgb, _build_histgb, cfg.histgb_samples),
                ("RandomForest", _sample_rf, _build_rf, cfg.rf_samples),
                ("ExtraTrees", _sample_extra_trees, _build_extra_trees, cfg.extra_trees_samples),
                ("GradientBoosting", _sample_gradient_boosting, _build_gradient_boosting, cfg.gradient_boosting_samples),
                ("KNeighbors", _sample_knn, _build_knn, cfg.knn_samples),
                ("SVR", _sample_svr, _build_svr, cfg.svr_samples),
                ("ElasticNet", _sample_elasticnet, _build_elasticnet, cfg.elasticnet_samples),
                ("PLSRegression", _sample_pls, _build_pls, cfg.pls_samples),
            ]
            tabular_specs.extend(optional_boosters)

            baseline_params_by_algo = {
                "HistGB": BASELINE_HISTGB_PARAMS,
                "RandomForest": BASELINE_RF_PARAMS,
            }
            target_candidates: list[TabularCandidate] = []
            best_baseline_rmse: float | None = None

            for algo_name, sampler, builder, n_samples in tabular_specs:
                # Build the combo list: 1 baseline (if defined) + n_samples random.
                combos: list[tuple[str, dict[str, Any], int, str]] = []
                base_params = baseline_params_by_algo.get(algo_name)
                if base_params is not None:
                    combos.append((
                        f"{algo_name}#BASELINE",
                        dict(base_params),
                        BASELINE_WINDOW_SIZE,
                        BASELINE_FEATURE_VARIANT,
                    ))
                for combo_idx in range(n_samples):
                    combos.append((
                        f"{algo_name}#{combo_idx:03d}",
                        sampler(rng),
                        rng.choice(cfg.window_sizes),
                        rng.choice(cfg.feature_variants),
                    ))

                for variant_id, params, window, variant in combos:
                    res = ExperimentResult(
                        station=station,
                        target=target,
                        algo=algo_name,
                        variant_id=variant_id,
                        window_size=window,
                        feature_variant=variant,
                        params=params,
                    )
                    try:
                        cv_df = station_df.iloc[:holdout_idx_for_tabular]
                        X_cv, y_cv = _prepare_xy(cv_df, target, window, variant, inputs)
                        if X_cv.empty:
                            res.error = "cv_empty_after_features"
                        else:
                            with wmodule.catch_warnings():
                                wmodule.simplefilter("ignore")
                                abort_threshold = None
                                if best_baseline_rmse is not None and "#BASELINE" not in variant_id:
                                    abort_threshold = best_baseline_rmse * 1.8
                                metrics, n_train_avg, elapsed, n_folds_done, stop_reason = _eval_tabular(
                                    builder, params, X_cv, y_cv,
                                    n_splits=CV_SPLITS,
                                    max_train_size=MAX_TRAIN_SIZE_CV,
                                    abort_rmse_threshold=abort_threshold,
                                )
                            if not metrics:
                                res.error = stop_reason or "cv_too_short"
                                res.n_train_avg = float(n_train_avg)
                                res.n_folds = int(n_folds_done)
                                res.train_time_sec = float(elapsed)
                            else:
                                res.rmse_mean = metrics["rmse_mean"]
                                res.rmse_std = metrics["rmse_std"]
                                res.r2_mean = metrics["r2_mean"]
                                res.mae_mean = metrics["mae_mean"]
                                res.n_train_avg = float(n_train_avg)
                                res.n_folds = int(n_folds_done)
                                res.train_time_sec = float(elapsed)

                                # Holdout: build features on full station_df, then split
                                X_full, y_full = _prepare_xy(station_df, target, window, variant, inputs)
                                if not X_full.empty:
                                    ho_split = _holdout_pos_from_index(X_full, holdout_idx_for_tabular)
                                    if ho_split > 0 and ho_split < len(X_full):
                                        with wmodule.catch_warnings():
                                            wmodule.simplefilter("ignore")
                                            ho_rmse, ho_r2, importances = _eval_holdout_tabular(
                                                builder, params, X_full, y_full, ho_split
                                            )
                                        res.holdout_rmse = ho_rmse
                                        res.holdout_r2 = ho_r2
                                        res.feature_importances = importances

                                if variant_id.endswith("#BASELINE"):
                                    best_baseline_rmse = (
                                        res.rmse_mean
                                        if best_baseline_rmse is None
                                        else min(best_baseline_rmse, res.rmse_mean)
                                    )
                                target_candidates.append(
                                    TabularCandidate(
                                        station=station,
                                        target=target,
                                        algo=algo_name,
                                        variant_id=variant_id,
                                        window_size=window,
                                        feature_variant=variant,
                                        params=params,
                                        build_fn=builder,
                                        rmse_mean=res.rmse_mean,
                                        rmse_std=res.rmse_std,
                                        holdout_rmse=res.holdout_rmse,
                                    )
                                )
                    except Exception as exc:
                        res.error = f"{type(exc).__name__}: {exc}"

                    rows_buffer.append(res.to_row())
                    logger.info(
                        "%s | %s | %s | %s W=%d V=%s rmse=%.4f±%.4f ho=%.4f t=%.1fs %s",
                        station, target, algo_name, variant_id, window, variant,
                        res.rmse_mean, res.rmse_std, res.holdout_rmse, res.train_time_sec,
                        ("ERR " + res.error if res.error else "OK"),
                    )
                _flush()

            if cfg.enable_ensembles:
                for res in _run_tabular_ensembles(target_candidates, station_df, target, inputs, holdout_idx_for_tabular):
                    rows_buffer.append(res.to_row())
                    logger.info(
                        "%s | %s | %s | %s W=%d rmse=%.4f±%.4f ho=%.4f t=%.1fs %s",
                        station, target, res.algo, res.variant_id, res.window_size,
                        res.rmse_mean, res.rmse_std, res.holdout_rmse, res.train_time_sec,
                        ("ERR " + res.error if res.error else "OK"),
                    )
                _flush()

            if has_tf and cfg.sequence_samples > 0:
                sequence_combos: list[tuple[str, dict[str, Any], int]] = [
                    ("LSTM#BASELINE", dict(BASELINE_LSTM_PARAMS), BASELINE_WINDOW_SIZE),
                ]
                for combo_idx in range(cfg.sequence_samples):
                    params = _sample_sequence(rng)
                    model_label = {
                        "lstm": "LSTM",
                        "gru": "GRU",
                        "conv1d": "Conv1D",
                        "cnn_lstm": "CNN-LSTM",
                    }[params["model_type"]]
                    sequence_combos.append((
                        f"{model_label}#{combo_idx:03d}",
                        params,
                        rng.choice(cfg.window_sizes),
                    ))
                for variant_id, params, window in sequence_combos:
                    algo_name = {
                        "lstm": "LSTM",
                        "gru": "GRU",
                        "conv1d": "Conv1D",
                        "cnn_lstm": "CNN-LSTM",
                    }[params.get("model_type", "lstm")]
                    res = ExperimentResult(
                        station=station,
                        target=target,
                        algo=algo_name,
                        variant_id=variant_id,
                        window_size=window,
                        feature_variant="autoregressive",
                        params=params,
                    )
                    try:
                        with wmodule.catch_warnings():
                            wmodule.simplefilter("ignore")
                            metrics, n_train_avg, elapsed, ho_rmse, ho_r2 = _eval_lstm(
                                params, station_df, target, window, inputs, HOLDOUT_FRACTION, n_splits=SEQUENCE_CV_SPLITS
                            )
                        if not metrics:
                            res.error = "insufficient_rows"
                        else:
                            res.rmse_mean = metrics["rmse_mean"]
                            res.rmse_std = metrics["rmse_std"]
                            res.r2_mean = metrics["r2_mean"]
                            res.mae_mean = metrics["mae_mean"]
                            res.n_train_avg = float(n_train_avg)
                            res.n_folds = SEQUENCE_CV_SPLITS
                            res.train_time_sec = float(elapsed)
                            res.holdout_rmse = ho_rmse
                            res.holdout_r2 = ho_r2
                    except Exception as exc:
                        res.error = f"{type(exc).__name__}: {exc}"
                    rows_buffer.append(res.to_row())
                    logger.info(
                        "%s | %s | %s | %s W=%d rmse=%.4f±%.4f ho=%.4f t=%.1fs %s",
                        station, target, algo_name, variant_id, window,
                        res.rmse_mean, res.rmse_std, res.holdout_rmse, res.train_time_sec,
                        ("ERR " + res.error if res.error else "OK"),
                    )
                _flush()

    _flush()
    return out_csv


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ML experiments per station/target.")
    parser.add_argument("--quick", action="store_true", help="Tiny smoke run (1 station, 1 target, ~10 combos)")
    parser.add_argument("--overnight", action="store_true", help="Full nightly random search budget")
    parser.add_argument("--max", dest="max_flag", action="store_true", help="Maximum search: overnight + optional boosters + sequential NN + ensembles")
    parser.add_argument("--medium", dest="medium_flag", action="store_true", help="Medium search (~2h): reduced budgets, boosters on, no CatBoost/NN")
    parser.add_argument("--from-training-csvs", dest="from_training_csvs", action="store_true", help="Read data from entrenamiento_*.csv (split by station) instead of csvs/ raw files")
    parser.add_argument("--all", dest="all_flag", action="store_true", help="Run on all 6 stations (default)")
    parser.add_argument("--station", action="append", choices=STATIONS, help="Restrict to specific station(s)")
    parser.add_argument("--target", action="append", choices=TARGETS, help="Restrict to specific target(s)")
    parser.add_argument("--skip-lstm", action="store_true", help="Skip LSTM variants (faster)")
    parser.add_argument(
        "--include-optional-boosters",
        action="store_true",
        help="Try LightGBM/XGBoost/CatBoost when installed",
    )
    parser.add_argument("--no-ensembles", action="store_true", help="Skip final weighted/stacking ensembles")
    parser.add_argument("--no-catboost", dest="no_catboost", action="store_true", help="Drop CatBoost (slow, not production-expressible)")
    parser.add_argument("--seed", type=int, default=DEFAULT_RNG_SEED)
    parser.add_argument("--output-dir", type=Path, default=None, help="Override output dir (default: results/<timestamp>)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    cfg = RunConfig(
        seed=args.seed,
        skip_lstm=args.skip_lstm,
        include_optional_boosters=args.include_optional_boosters,
        enable_ensembles=not args.no_ensembles,
    )
    if args.station:
        cfg.stations = args.station
    if args.target:
        cfg.targets = args.target
    if args.medium_flag:
        cfg = _medium_overrides(cfg)
        cfg.include_optional_boosters = True
        cfg.skip_lstm = True
    elif args.max_flag:
        cfg = _overnight_overrides(cfg)
        cfg.include_optional_boosters = True
        cfg.skip_lstm = args.skip_lstm  # --skip-lstm wins even under --max
        cfg.enable_ensembles = True
    elif args.overnight:
        cfg = _overnight_overrides(cfg)
    if args.quick:
        cfg = _quick_overrides(cfg)
    if args.from_training_csvs:
        cfg.use_training_csvs = True
    if args.no_catboost:
        cfg.catboost_samples = 0

    if args.output_dir:
        out_dir = args.output_dir
    else:
        ts = time.strftime("%Y%m%d_%H%M%S")
        out_dir = Path(__file__).parent / "results" / ts

    out_csv = run(cfg, out_dir)
    print(f"\nResults written to: {out_csv}")
    print(f"Output dir: {out_dir}")


if __name__ == "__main__":
    main()
