from __future__ import annotations

import io
import logging
import math
import threading
import uuid
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.preprocessing import MinMaxScaler

from .storage_service import StorageService

logger = logging.getLogger(__name__)

try:
    import tensorflow as tf
    from tensorflow.keras.callbacks import Callback, EarlyStopping
    from tensorflow.keras.layers import Dense, Dropout, Input, LSTM
    from tensorflow.keras.losses import Huber
    from tensorflow.keras.models import Model

    TF_AVAILABLE = True

    class _ProgressCallback(Callback):
        def __init__(self, model_id: str, target: str) -> None:
            super().__init__()
            self._model_id = model_id
            self._target = target

        def on_epoch_end(self, epoch: int, logs: dict | None = None) -> None:
            val_loss = float((logs or {}).get("val_loss", 0.0))
            _update_registry(self._model_id, current_epoch=epoch + 1, val_loss=val_loss)

except ImportError:
    TF_AVAILABLE = False
    logger.warning("TensorFlow no disponible — se usará GradientBoosting.")

_registry: dict[str, dict] = {}
_lock = threading.Lock()

class ModelosServiceError(RuntimeError):
    pass


def get_training_status(model_id: str) -> dict | None:
    with _lock:
        return _registry.get(model_id)


def _update_registry(model_id: str, **kwargs: Any) -> None:
    with _lock:
        if model_id in _registry:
            _registry[model_id].update(kwargs)


class TrainingService:
    def __init__(self) -> None:
        self._storage = StorageService()

    def start_training(
        self,
        targets: list[str],
        input_cols: list[str],
        treatment: str,
        csv_content: bytes,
        features: list[str] | None = None,
        geo: dict | None = None,
        user_id: int | None = None,
    ) -> str:
        model_id = str(uuid.uuid4())
        with _lock:
            _registry[model_id] = {
                "status": "training",
                "phase": "iniciando",
                "current_epoch": None,
                "total_epochs": None,
                "current_target": None,
                "val_loss": None,
            }
        threading.Thread(
            target=self._train,
            args=(model_id, targets, input_cols, treatment, csv_content, features or [], geo or {}, user_id),
            daemon=True,
        ).start()
        return model_id

    def _train(
        self,
        model_id: str,
        targets: list[str],
        input_cols: list[str],
        treatment: str,
        csv_content: bytes,
        features: list[str],
        geo: dict,
        user_id: int | None,
    ) -> None:
        try:
            self._run_pipeline(model_id, targets, input_cols, treatment, csv_content, features, geo, user_id)
        except Exception as exc:
            logger.exception("Error entrenando modelo %s", model_id)
            _update_registry(model_id, status="error", detail=str(exc))

    def _run_pipeline(
        self,
        model_id: str,
        targets: list[str],
        input_cols: list[str],
        treatment: str,
        csv_content: bytes,
        features: list[str] | None = None,
        geo: dict | None = None,
        user_id: int | None = None,
    ) -> None:
        from apps.configurador.services.flamapy_service import FlamapyService

        _update_registry(model_id, phase="cargando datos")
        try:
            df = pd.read_csv(io.BytesIO(csv_content), sep=";", parse_dates=["date"])
        except Exception as exc:
            raise ModelosServiceError(f"Error leyendo CSV: {exc}") from exc

        if not targets:
            raise ModelosServiceError("Ninguna variable objetivo activada en la configuración.")

        missing = [c for c in targets + input_cols if c not in df.columns]
        if missing:
            raise ModelosServiceError(f"Columnas ausentes en CSV: {missing}")

        profile = FlamapyService.get_treatment_profile(treatment)
        window_size: int = profile["window_size"]
        preferred: str = profile["preferred_algorithm"]
        min_samples: int = profile["min_samples"]

        input_features = [c for c in input_cols if c not in set(targets)]
        all_cols = targets + input_features
        n_joint = int(df[all_cols].dropna().shape[0])
        algorithm = preferred
        warnings: list[str] = []

        if preferred == "LSTM":
            if not TF_AVAILABLE:
                algorithm = "GradientBoosting"
                warnings.append(
                    "TensorFlow no disponible; se ha utilizado GradientBoosting."
                )
            elif n_joint < min_samples:
                algorithm = "GradientBoosting"
                warnings.append(
                    f"Datos insuficientes para LSTM ({n_joint} filas; mínimo {min_samples}). "
                    "Se ha utilizado GradientBoosting con características temporales."
                )

        if algorithm == "LSTM":
            self._train_lstm(model_id, df, targets, input_features, window_size, treatment, all_cols, warnings, features or [], geo or {})
        else:
            self._train_sklearn(model_id, df, targets, input_features, window_size, treatment, all_cols, warnings, algorithm, features or [], geo or {})

        self._create_db_record(model_id, user_id)

    # ---------------------------------------------------------------- LSTM

    def _train_lstm(
        self,
        model_id: str,
        df: pd.DataFrame,
        targets: list[str],
        input_features: list[str],
        window_size: int,
        treatment: str,
        all_cols: list[str],
        warnings: list[str],
        features: list[str],
        geo: dict,
    ) -> None:
        # Approach: X windows include past target values (autoregressive, same as sensolive).
        # scaler_X and scaler_Y both fit on train partition only — no data leakage.
        _update_registry(model_id, phase="preparando datos LSTM", algorithm="LSTM")

        df_clean = df[all_cols].dropna().reset_index(drop=True)
        n = len(df_clean)
        split = int(n * 0.8)

        train_df = df_clean.iloc[:split]
        val_df   = df_clean.iloc[split:]

        scaler_X = MinMaxScaler()
        train_scaled = scaler_X.fit_transform(train_df[all_cols])
        val_scaled   = scaler_X.transform(val_df[all_cols])

        scaler_Y: dict[str, MinMaxScaler] = {}
        for t in targets:
            sc = MinMaxScaler()
            sc.fit(train_df[[t]])
            scaler_Y[t] = sc

        def make_windows(arr: np.ndarray) -> np.ndarray:
            return np.array(
                [arr[i:i + window_size] for i in range(len(arr) - window_size)],
                dtype="float32",
            )

        # X: windows over ALL cols (targets + features) — autoregressive
        X_tr = make_windows(train_scaled)
        X_vl = make_windows(val_scaled)

        lstm_models: dict[str, Any] = {}
        metrics: dict[str, dict] = {}
        total_epochs = 200
        _update_registry(model_id, total_epochs=total_epochs)
        n_tr = len(X_tr)
        n_vl = len(X_vl)

        for t in targets:
            _update_registry(model_id, phase="entrenando", current_target=t, current_epoch=0, val_loss=None)

            # Y: scaler_Y applied to raw target values, aligned with window offset
            y_tr = scaler_Y[t].transform(train_df[[t]].values[window_size:]).ravel().astype("float32")
            y_vl = scaler_Y[t].transform(val_df[[t]].values[window_size:]).ravel().astype("float32")

            inp = Input(shape=(window_size, len(all_cols)))
            x = LSTM(128, activation="tanh")(inp)
            x = Dropout(0.2)(x)
            x = Dense(64, activation="relu")(x)
            out = Dense(1)(x)
            model = Model(inp, out)
            model.compile(
                optimizer=tf.keras.optimizers.Adam(0.001),
                loss=Huber(),
            )

            model.fit(
                X_tr, y_tr,
                validation_data=(X_vl, y_vl),
                epochs=total_epochs,
                batch_size=32,
                callbacks=[
                    _ProgressCallback(model_id, t),
                    EarlyStopping(
                        monitor="val_loss",
                        patience=30,
                        restore_best_weights=True,
                        min_delta=1e-4,
                    ),
                ],
                verbose=0,
            )

            lstm_models[t] = model

            y_pred = scaler_Y[t].inverse_transform(model.predict(X_vl, verbose=0)).ravel()
            y_true = scaler_Y[t].inverse_transform(y_vl.reshape(-1, 1)).ravel()
            metrics[t] = _compute_metrics(y_true, y_pred)
            _quality_warnings(t, metrics[t]["r2"], warnings)

        scalers = {"X": scaler_X, **scaler_Y}
        self._storage.save_lstm(model_id, lstm_models, scalers)

        self._storage.save_metadata(model_id, {
            "model_id": model_id,
            "algorithm": "LSTM",
            "treatment": treatment,
            "features": features,
            "geo": geo,
            "all_cols": all_cols,
            "targets": targets,
            "input_features": input_features,
            "window_size": window_size,
            "temporal_features": False,
            "n_samples": n_tr + n_vl,
            "n_train": n_tr,
            "n_val": n_vl,
            "metrics": metrics,
            "warnings": warnings,
        })
        _update_registry(
            model_id,
            status="completed",
            algorithm="LSTM",
            metrics=metrics,
            warnings=warnings,
            n_train=n_tr,
            n_val=n_vl,
        )

    # --------------------------------------------------------------- RF / GB

    def _train_sklearn(
        self,
        model_id: str,
        df: pd.DataFrame,
        targets: list[str],
        input_features: list[str],
        window_size: int,
        treatment: str,
        all_cols: list[str],
        warnings: list[str],
        algorithm: str,
        features: list[str],
        geo: dict,
    ) -> None:
        _update_registry(model_id, phase="preparando datos", algorithm=algorithm)

        sk_models: dict[str, Any] = {}
        sk_scalers: dict[str, MinMaxScaler] = {}
        metrics: dict[str, dict] = {}
        feature_columns_by_target: dict[str, list[str]] = {}
        n_trains: list[int] = []
        n_vals: list[int] = []

        for t in targets:
            _update_registry(model_id, current_target=t, phase="entrenando")

            # Autoregressive: ALL targets (including t) + env features contribute lags
            # lag_sources already contains t (via targets), so base_cols = lag_sources avoids duplicates
            lag_sources = targets + input_features
            base_cols = lag_sources
            if "date" in df.columns:
                df_t = df[["date"] + base_cols].dropna(subset=base_cols).copy()
                df_t = _add_temporal_features(df_t, lag_sources, window_size)
                df_t = df_t.drop(columns=["date"], errors="ignore").dropna()
            else:
                df_t = df[base_cols].dropna(subset=base_cols).copy()

            feat_cols = [c for c in df_t.columns if c != t]
            feature_columns_by_target[t] = feat_cols
            split = int(len(df_t) * 0.8)
            tr = df_t.iloc[:split]
            vl = df_t.iloc[split:]
            n_trains.append(len(tr))
            n_vals.append(len(vl))

            scaler = MinMaxScaler()
            tr_arr = scaler.fit_transform(tr[[t] + feat_cols])
            vl_arr = scaler.transform(vl[[t] + feat_cols])

            X_tr, y_tr = tr_arr[:, 1:], tr_arr[:, 0]
            X_vl, y_vl = vl_arr[:, 1:], vl_arr[:, 0]

            est = _build_rf() if algorithm == "RandomForest" else _build_gb()
            est.fit(X_tr, y_tr)

            y_pred = _desescalar_parcial(scaler, est.predict(X_vl).reshape(-1, 1), 0).ravel()
            y_true = _desescalar_parcial(scaler, y_vl.reshape(-1, 1), 0).ravel()
            metrics[t] = _compute_metrics(y_true, y_pred)
            _quality_warnings(t, metrics[t]["r2"], warnings)

            sk_models[t] = est
            sk_scalers[t] = scaler

        self._storage.save_sklearn(model_id, sk_models, sk_scalers)

        n_tr = min(n_trains) if n_trains else 0
        n_vl = min(n_vals) if n_vals else 0
        self._storage.save_metadata(model_id, {  # type: ignore[arg-type]
            "model_id": model_id,
            "algorithm": algorithm,
            "treatment": treatment,
            "features": features,
            "geo": geo,
            "all_cols": all_cols,
            "targets": targets,
            "input_features": input_features,
            "window_size": window_size,
            "temporal_features": True,
            "feature_columns_by_target": feature_columns_by_target,
            "n_samples": n_tr + n_vl,
            "n_train": n_tr,
            "n_val": n_vl,
            "metrics": metrics,
            "warnings": warnings,
        })
        _update_registry(
            model_id,
            status="completed",
            algorithm=algorithm,
            metrics=metrics,
            warnings=warnings,
            n_train=n_tr,
            n_val=n_vl,
        )

    def _create_db_record(self, model_id: str, user_id: int | None) -> None:
        try:
            from apps.modelos.models import ModeloGuardado

            meta = self._storage.load_metadata(model_id)
            ModeloGuardado.objects.get_or_create(
                model_id=model_id,
                defaults={
                    "user_id": user_id,
                    "algorithm": meta.get("algorithm", ""),
                    "treatment": meta.get("treatment") or meta.get("crop", ""),
                    "features": meta.get("features", []),
                    "geo": meta.get("geo", {}),
                    "targets": meta.get("targets", []),
                    "input_features": meta.get("input_features", []),
                    "all_cols": meta.get("all_cols", []),
                    "metrics": meta.get("metrics", {}),
                    "warnings": meta.get("warnings", []),
                    "n_samples": meta.get("n_samples", 0),
                    "n_train": meta.get("n_train", 0),
                    "n_val": meta.get("n_val", 0),
                    "window_size": meta.get("window_size", 0),
                    "imported": False,
                },
            )
        except Exception:
            logger.exception("No se pudo crear registro DB para modelo %s", model_id)


# ------------------------------------------------------------------ helpers

def _build_rf() -> RandomForestRegressor:
    return RandomForestRegressor(
        n_estimators=300,
        max_features="sqrt",
        min_samples_split=4,
        min_samples_leaf=2,
        oob_score=True,
        n_jobs=-1,
        random_state=42,
    )


def _build_gb() -> HistGradientBoostingRegressor:
    return HistGradientBoostingRegressor(
        max_depth=5,
        learning_rate=0.05,
        max_iter=300,
        early_stopping=True,
        random_state=42,
    )


def _add_temporal_features(df: pd.DataFrame, input_features: list[str], window_size: int) -> pd.DataFrame:
    df = df.copy()
    day_of_year = df["date"].dt.dayofyear
    df["day_sin"] = np.sin(2 * np.pi * day_of_year / 365.0)
    df["day_cos"] = np.cos(2 * np.pi * day_of_year / 365.0)
    roll_w = min(7, window_size)
    for feat in input_features:
        if feat not in df.columns:
            continue
        for lag in range(1, window_size + 1):
            df[f"{feat}_lag{lag}"] = df[feat].shift(lag)
        df[f"{feat}_roll{roll_w}d"] = df[feat].shift(1).rolling(roll_w).mean()
    return df


def _desescalar_parcial(scaler: MinMaxScaler, values: np.ndarray, col_idx: int) -> np.ndarray:
    dummy = np.zeros((len(values), scaler.n_features_in_))
    dummy[:, col_idx] = values.ravel()
    return scaler.inverse_transform(dummy)[:, col_idx].reshape(-1, 1)


def _compute_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    return {
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "rmse": float(math.sqrt(mean_squared_error(y_true, y_pred))),
        "r2": float(r2_score(y_true, y_pred)),
    }


def _quality_warnings(target: str, r2: float, warnings: list[str]) -> None:
    from apps.configurador.services.flamapy_service import FlamapyService
    thresholds = FlamapyService.get_quality_thresholds(target)
    if thresholds is None:
        return
    if r2 < thresholds["min"]:
        warnings.append(
            f"{target}: R²={r2:.3f} por debajo del umbral mínimo ({thresholds['min']}). "
            "Se recomienda ampliar el dataset."
        )
    elif r2 < thresholds["good"]:
        warnings.append(
            f"{target}: R²={r2:.3f} aceptable pero por debajo del umbral óptimo ({thresholds['good']})."
        )
