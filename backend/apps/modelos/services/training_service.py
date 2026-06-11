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

_registry: dict[str, dict] = {}
_lock = threading.Lock()

class ModelosServiceError(RuntimeError):
    pass


def get_training_status(model_id: str) -> dict | None:
    with _lock:
        entry = _registry.get(model_id)
        return dict(entry) if entry is not None else None


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
        is_validation: bool = True,
    ) -> str:
        model_id = str(uuid.uuid4())
        with _lock:
            _registry[model_id] = {
                "status": "training",
                "phase": "iniciando",
                "current_target": None,
                "user_id": user_id,
                "is_validation": is_validation,
            }
        threading.Thread(
            target=self._train,
            args=(model_id, targets, input_cols, treatment, csv_content, features or [], geo or {}, user_id, is_validation),
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
        is_validation: bool = True,
    ) -> None:
        try:
            self._run_pipeline(model_id, targets, input_cols, treatment, csv_content, features or [], geo or {}, user_id, is_validation)
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
        is_validation: bool = True,
    ) -> None:
        from apps.configurador.services.flamapy_service import FlamapyService

        _update_registry(model_id, phase="cargando datos")
        try:
            df = pd.read_csv(io.BytesIO(csv_content), sep=";", parse_dates=["date"])
        except Exception as exc:
            raise ModelosServiceError(f"Error leyendo CSV: {exc}") from exc

        if not targets:
            raise ModelosServiceError("Ninguna variable objetivo activada en la configuración.")

        input_features = [c for c in input_cols if c not in set(targets)]
        missing = [c for c in targets + input_features if c not in df.columns]
        if missing:
            raise ModelosServiceError(f"Columnas ausentes en CSV: {missing}")

        # Orden temporal (los lags/rolling dependen del orden por fecha) y despike de picos
        # aislados del dendrómetro (MCD) antes de cualquier feature.
        if "date" in df.columns:
            df = df.sort_values("date").reset_index(drop=True)
        for col in DESPIKE_COLUMNS:
            if col in df.columns:
                df[col], _ = _despike_isolated(df[col])

        # Build per-target profiles from UVL treatment attributes (algorithm,
        # window_size, feature_variant, hyperprofile). Every target trains with
        # its own sklearn estimator via _train_per_target.
        treatment_target_profiles: dict[str, dict] = {
            t: FlamapyService.get_treatment_target_profile(treatment, t)
            for t in targets
        }

        self._train_per_target(
            model_id, df, targets, input_features, treatment,
            treatment_target_profiles, [], features or [], geo or {}, user_id, is_validation,
        )

        self._create_db_record(model_id, user_id)

    # ---------------------------------------------------------------- per-target sklearn

    def _train_per_target(
        self,
        model_id: str,
        df: pd.DataFrame,
        targets: list[str],
        input_features: list[str],
        treatment: str,
        treatment_target_profiles: dict[str, dict],
        warnings: list[str],
        features: list[str],
        geo: dict,
        user_id: int | None,
        is_validation: bool = True,
    ) -> None:
        from apps.modelos.services.hyperprofile_registry import UnknownHyperprofileError, get_hyperprofile
        from apps.modelos.services.feature_engineering import add_features
        from apps.configurador.services.flamapy_service import FlamapyService

        _update_registry(model_id, phase="preparando datos por target")

        zero_fill_cols = FlamapyService.get_zero_fill_columns()

        sk_models: dict[str, Any] = {}
        sk_scalers: dict[str, MinMaxScaler] = {}
        metrics: dict[str, dict] = {}
        val_series_data: dict[str, dict] = {}
        feature_columns_by_target: dict[str, list[str]] = {}
        n_trains: list[int] = []
        n_vals: list[int] = []
        target_profiles_meta: dict[str, dict] = {}

        for t in targets:
            _update_registry(model_id, current_target=t, phase="entrenando")

            tp = treatment_target_profiles[t]
            algorithm: str = tp["algorithm"]
            window_size: int = tp["window_size"]
            feature_variant: str | None = tp.get("feature_variant")
            hyperprofile_name: str | None = tp.get("hyperprofile")

            hp_params: dict = {}
            max_samples: int | None = None

            if hyperprofile_name:
                try:
                    hp = get_hyperprofile(hyperprofile_name)
                except UnknownHyperprofileError as exc:
                    raise ModelosServiceError(str(exc)) from exc

                hp_params = hp.get("params", {})
                max_samples = hp.get("max_samples")
                required = hp.get("required_inputs", [])
                optional = hp.get("optional_inputs", [])

                missing_req = [c for c in required if c not in df.columns]
                if missing_req:
                    raise ModelosServiceError(
                        f"Perfil {hyperprofile_name!r} requiere columnas ausentes para '{t}': {missing_req}"
                    )
                missing_opt = [c for c in optional if c not in df.columns]
                if missing_opt:
                    warnings.append(
                        f"{t}: columnas opcionales ausentes para '{hyperprofile_name}': {missing_opt}. "
                        "Se omiten features derivadas de esas columnas."
                    )

            is_target_only = feature_variant == "target_only"
            lag_sources = [t] if is_target_only else ([t] + input_features)
            date_col = ["date"] if "date" in df.columns else []
            df_base = df[date_col + lag_sources].copy()
            if not is_target_only:
                df_base = _interpolate_sensor_gaps(df_base, input_features, zero_fill_cols)
            df_base = df_base.dropna(subset=lag_sources)

            if algorithm == "SVR" and len(df_base) > 500:
                warnings.append(
                    f"{t}: Algoritmo SVR con {len(df_base)} filas de entrenamiento. "
                    "El proceso puede tardar varios minutos."
                )

            # Apply features to full df_base before splitting so rolling windows
            # have enough history for val rows.
            # Shift(1) on all features guarantees no target leakage.
            if feature_variant and "date" in df_base.columns:
                df_aug = add_features(df_base, lag_sources, window_size, feature_variant)
            elif "date" in df_base.columns:
                df_aug = _add_temporal_features(df_base, lag_sources, window_size)
            else:
                df_aug = df_base.copy()

            df_aug = df_aug.drop(columns=["date"], errors="ignore").dropna()

            if df_aug.empty:
                raise ModelosServiceError(
                    f"Datos insuficientes para '{t}' tras aplicar ventana temporal {window_size}."
                )

            # Validación: split temporal 80/20 para medir precisión (métricas + serie val).
            # Operativo: se entrena con el 100% de los datos (sin hold-out); el objetivo es el
            # predictor, no medir precisión, así que no hay métricas de validación.
            if is_validation:
                split = int(len(df_aug) * 0.8)
                tr = df_aug.iloc[:split].copy()
                vl = df_aug.iloc[split:].copy()
                if tr.empty or vl.empty:
                    raise ModelosServiceError(
                        f"Datos insuficientes para '{t}' tras aplicar ventana temporal {window_size}."
                    )
            else:
                tr = df_aug.copy()
                vl = df_aug.iloc[0:0].copy()
                if tr.empty:
                    raise ModelosServiceError(
                        f"Datos insuficientes para '{t}' tras aplicar ventana temporal {window_size}."
                    )

            if max_samples and len(tr) > max_samples:
                tr = tr.sample(max_samples, random_state=42)

            feat_cols = [c for c in tr.columns if c != t]
            feature_columns_by_target[t] = feat_cols
            n_trains.append(len(tr))
            n_vals.append(len(vl))

            scaler = MinMaxScaler()
            tr_arr = scaler.fit_transform(tr[[t] + feat_cols])

            X_tr, y_tr = tr_arr[:, 1:], tr_arr[:, 0]

            est = _build_estimator(algorithm, hp_params, n_features=X_tr.shape[1], n_samples=X_tr.shape[0], warnings_out=warnings, target=t)

            est.fit(X_tr, y_tr)

            if is_validation:
                vl_arr = scaler.transform(vl[[t] + feat_cols])
                X_vl, y_vl = vl_arr[:, 1:], vl_arr[:, 0]
                y_pred_scaled = est.predict(X_vl)
                if hasattr(y_pred_scaled, "ndim") and y_pred_scaled.ndim > 1:
                    y_pred_scaled = y_pred_scaled.ravel()
                y_pred = _desescalar_parcial(scaler, y_pred_scaled.reshape(-1, 1), 0).ravel()
                y_true = _desescalar_parcial(scaler, y_vl.reshape(-1, 1), 0).ravel()
                metrics[t] = _compute_metrics(y_true, y_pred)
                val_series_data[t] = {"y_true": y_true[:100].tolist(), "y_pred": y_pred[:100].tolist()}
                _quality_warnings(t, metrics[t]["r2"], warnings)

            sk_models[t] = est
            sk_scalers[t] = scaler
            target_profiles_meta[t] = {
                "algorithm": algorithm,
                "window_size": window_size,
                "feature_variant": feature_variant,
                "hyperprofile": hyperprofile_name,
            }

        self._storage.save_sklearn(model_id, sk_models, sk_scalers)

        algorithms_used = {p["algorithm"] for p in target_profiles_meta.values()}
        top_algorithm = next(iter(algorithms_used)) if len(algorithms_used) == 1 else "Mixed"
        top_window = max(p["window_size"] for p in target_profiles_meta.values())
        n_tr = min(n_trains) if n_trains else 0
        n_vl = min(n_vals) if n_vals else 0

        self._storage.save_metadata(model_id, {
            "model_id": model_id,
            "user_id": user_id,
            "algorithm": top_algorithm,
            "treatment": treatment,
            "features": features,
            "geo": geo,
            "all_cols": targets + input_features,
            "targets": targets,
            "input_features": input_features,
            "window_size": top_window,
            "temporal_features": True,
            "feature_columns_by_target": feature_columns_by_target,
            "target_profiles": target_profiles_meta,
            "n_samples": n_tr + n_vl,
            "n_train": n_tr,
            "n_val": n_vl,
            "is_validation": is_validation,
            "metrics": metrics,
            "val_series": val_series_data,
            "warnings": warnings,
        })
        _update_registry(
            model_id,
            status="completed",
            algorithm=top_algorithm,
            metrics=metrics,
            val_series=val_series_data,
            warnings=warnings,
            n_train=n_tr,
            n_val=n_vl,
            is_validation=is_validation,
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
        n_estimators=600,
        max_depth=20,
        max_features=1.0,
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


def _build_estimator(
    algorithm: str,
    params: dict[str, Any],
    n_features: int | None = None,
    n_samples: int | None = None,
    warnings_out: list[str] | None = None,
    target: str = "",
) -> Any:
    """Build a sklearn-compatible estimator from algorithm name and hyperparameters."""
    if algorithm == "RandomForest":
        return _build_rf()

    if algorithm in ("GradientBoosting", "HistGB"):
        return _build_gb()

    if algorithm == "SVR":
        from sklearn.svm import SVR
        return SVR(**params)

    if algorithm == "PLSRegression":
        from sklearn.cross_decomposition import PLSRegression
        p = dict(params)
        if n_features is not None or n_samples is not None:
            max_comp = min(
                p.get("n_components", 2),
                *([n_features] if n_features is not None else []),
                *([n_samples] if n_samples is not None else []),
            )
            if max_comp < p.get("n_components", 2):
                msg = (
                    f"{target}: PLSRegression n_components reducido de "
                    f"{p['n_components']} a {max_comp} por datos insuficientes."
                )
                logger.warning(msg)
                if warnings_out is not None:
                    warnings_out.append(msg)
            p["n_components"] = max_comp
        return PLSRegression(**p)

    if algorithm == "ElasticNet":
        from sklearn.linear_model import ElasticNet
        return ElasticNet(**params)

    raise ModelosServiceError(f"Algoritmo no soportado: {algorithm!r}")


DESPIKE_K = 5.0
DESPIKE_NEIGHBOR_FACTOR = 0.5
# Columnas derivadas del dendrómetro con picos aislados de 1 día (errores de sensor) que se
# corrigen antes de entrenar. Lógica de dominio del dendrómetro (como dendroCalc.ts), hardcodeada.
DESPIKE_COLUMNS = ("MCD",)


def _despike_isolated(
    s: pd.Series, k: float = DESPIKE_K, neighbor_factor: float = DESPIKE_NEIGHBOR_FACTOR
) -> tuple[pd.Series, int]:
    """
    Corrige picos AISLADOS de 1 día (errores del dendrómetro) sustituyéndolos por la media de los
    vecinos. Un árbol no se contrae/ensancha cientos de µm y vuelve al día siguiente.

    Criterio conservador (no toca cambios reales de tendencia):
        |x − media(vecinos)| > k · MAD(diferencias diarias)  Y  |prev − next| < neighbor_factor · dev
    """
    x = s.astype(float).to_numpy()
    n = len(x)
    if n < 3:
        return s, 0
    diffs = np.abs(np.diff(x))
    diffs = diffs[~np.isnan(diffs)]
    if diffs.size == 0:
        return s, 0
    mad = 1.4826 * np.median(np.abs(diffs - np.median(diffs)))
    if mad <= 0:
        return s, 0
    thr = k * mad
    out = x.copy()
    count = 0
    for i in range(1, n - 1):
        a, b, v = x[i - 1], x[i + 1], x[i]
        if np.isnan(a) or np.isnan(b) or np.isnan(v):
            continue
        mid = (a + b) / 2.0
        dev = abs(v - mid)
        if dev > thr and abs(a - b) < neighbor_factor * dev:
            out[i] = round(mid, 4)
            count += 1
    return pd.Series(out, index=s.index), count


def _interpolate_sensor_gaps(
    df: pd.DataFrame,
    input_features: list[str],
    zero_fill_cols: set[str] | None = None,
) -> pd.DataFrame:
    """
    Fill short sensor outages before feature engineering.
    Only applied to input feature columns — never to target variables.

    zero_fill_cols (UVL fill_strategy='zero', e.g. riego/lluvia): event/cumulative sensors
        where a day without record means 0 (no irrigation/rain), not a gap to interpolate.
    humedad_*: linear interpolation, limit=5 days (slow-varying soil moisture).
    everything else: linear interpolation, limit=3 days.
    """
    zero_fill_cols = zero_fill_cols or set()
    df = df.copy()
    for col in input_features:
        if col not in df.columns:
            continue
        if col in zero_fill_cols:
            df[col] = df[col].fillna(0.0)
        elif col.startswith("humedad_"):
            df[col] = df[col].interpolate(method="linear", limit=5, limit_direction="both")
        else:
            df[col] = df[col].interpolate(method="linear", limit=3, limit_direction="both")
    return df


def _add_temporal_features(df: pd.DataFrame, input_features: list[str], window_size: int) -> pd.DataFrame:
    """
    Legacy feature engineering used by the RandomForest/HistGB path.
    Adds seasonal sin/cos, lags, short rolling mean, and EMAs (alpha=0.3/0.7).
    """
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
        df[f"{feat}_ema30"] = df[feat].shift(1).ewm(alpha=0.3, adjust=False).mean()
        df[f"{feat}_ema70"] = df[feat].shift(1).ewm(alpha=0.7, adjust=False).mean()
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
