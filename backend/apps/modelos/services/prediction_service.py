from __future__ import annotations

import io
from typing import Any

import numpy as np
import pandas as pd

from .storage_service import StorageService
from .training_service import DESPIKE_COLUMNS, _add_temporal_features, _despike_isolated, _desescalar_parcial


class PredictionServiceError(RuntimeError):
    pass


class PredictionService:
    def __init__(self) -> None:
        self._storage = StorageService()

    def predict_one(self, model_id: str, csv_content: bytes) -> dict[str, Any]:
        metadata = self._storage.load_metadata(model_id)
        geo = metadata.get("geo") or {}
        if not isinstance(geo, dict) or not geo.get("punto"):
            raise PredictionServiceError(
                "El modelo no tiene ubicación guardada; no se puede extraer telemetría GEE para predecir."
            )

        try:
            df = pd.read_csv(io.BytesIO(csv_content), sep=";", parse_dates=["date"], encoding="utf-8-sig")
        except Exception as exc:
            raise PredictionServiceError(f"Error leyendo CSV de predicción: {exc}") from exc

        if "date" not in df.columns:
            raise PredictionServiceError("El CSV fusionado debe contener la columna 'date'.")

        df = df.sort_values("date").reset_index(drop=True)
        algorithm = str(metadata.get("algorithm", ""))
        targets = list(metadata.get("targets") or [])
        input_features = list(metadata.get("input_features") or [])
        all_cols = list(metadata.get("all_cols") or (targets + input_features))
        window_size = int(metadata.get("window_size") or 0)

        if not targets:
            raise PredictionServiceError("El modelo no define variables objetivo.")
        if window_size <= 0:
            raise PredictionServiceError("El modelo no define una ventana temporal válida.")

        missing = [c for c in ["date", *all_cols] if c not in df.columns]
        if missing:
            raise PredictionServiceError(f"Columnas ausentes en CSV: {missing}")

        predicted_for_date = (df["date"].max() + pd.Timedelta(days=1)).date()

        # Route: per-target profiles (new path) vs legacy single-algorithm sklearn path
        if metadata.get("target_profiles"):
            predictions = self._predict_per_target(
                model_id, df, metadata, targets, input_features, predicted_for_date
            )
        else:
            predictions = self._predict_sklearn(
                model_id, df, metadata, targets, input_features, window_size, algorithm, predicted_for_date
            )

        return {
            "model_id": model_id,
            "predicted_for_date": predicted_for_date,
            "predictions": predictions,
            "input_row_count": int(len(df)),
            "warnings": [],
        }

    # ---------------------------------------------------------------- per-target (new path)

    def _predict_per_target(
        self,
        model_id: str,
        df: pd.DataFrame,
        metadata: dict[str, Any],
        targets: list[str],
        input_features: list[str],
        predicted_for_date: Any,
    ) -> dict[str, float]:
        from apps.modelos.services.feature_engineering import add_features
        from apps.configurador.services.flamapy_service import FlamapyService

        models, scalers = self._storage.load_sklearn(model_id, targets)
        feature_columns_by_target = metadata.get("feature_columns_by_target") or {}
        target_profiles_meta: dict[str, dict] = metadata.get("target_profiles") or {}
        predictions: dict[str, float] = {}

        # Coherencia con el entrenamiento: sensores de evento (riego/lluvia) con día sin dato = 0,
        # y despike de picos aislados del dendrómetro (MCD) antes de construir características.
        df = df.copy()
        if "date" in df.columns:
            df = df.sort_values("date").reset_index(drop=True)
        for col in FlamapyService.get_zero_fill_columns():
            if col in df.columns:
                df[col] = df[col].fillna(0.0)
        for col in DESPIKE_COLUMNS:
            if col in df.columns:
                df[col], _ = _despike_isolated(df[col])

        for target in targets:
            tp = target_profiles_meta.get(target) or {}
            window_size = int(tp.get("window_size") or metadata.get("window_size") or 0)
            if window_size <= 0:
                raise PredictionServiceError(f"Ventana temporal inválida para '{target}'.")

            feature_variant: str | None = tp.get("feature_variant")
            is_target_only = feature_variant == "target_only"
            base_cols = [target] if is_target_only else (targets + input_features)

            df_hist = df[["date", *base_cols]].dropna(subset=base_cols).copy()
            if len(df_hist) < window_size:
                raise PredictionServiceError(
                    f"Datos insuficientes para predecir '{target}': "
                    f"se necesitan al menos {window_size} filas completas."
                )

            last = df_hist.iloc[-1]
            generated_date = pd.Timestamp(predicted_for_date)
            future_row: dict[str, Any] = {"date": generated_date}
            for col in base_cols:
                future_row[col] = last[col]

            df_future = pd.concat([df_hist, pd.DataFrame([future_row])], ignore_index=True)

            if feature_variant:
                df_aug = add_features(df_future, base_cols, window_size, feature_variant)
            else:
                df_aug = _add_temporal_features(df_future, base_cols, window_size)

            df_aug = df_aug.drop(columns=["date"], errors="ignore").dropna()
            if df_aug.empty:
                raise PredictionServiceError(
                    f"No se pudieron construir características temporales para '{target}'."
                )

            row = df_aug.iloc[[-1]]
            feat_cols = feature_columns_by_target.get(target) or [c for c in df_aug.columns if c != target]
            missing = [c for c in [target, *feat_cols] if c not in row.columns]
            if missing:
                raise PredictionServiceError(f"Columnas internas ausentes para '{target}': {missing}")

            scaler = scalers[target]
            arr = scaler.transform(row[[target, *feat_cols]])

            pred_scaled = models[target].predict(arr[:, 1:])
            if hasattr(pred_scaled, "ndim") and pred_scaled.ndim > 1:
                pred_scaled = pred_scaled.ravel()
            pred = _desescalar_parcial(scaler, pred_scaled.reshape(-1, 1), 0).ravel()[0]
            predictions[target] = float(pred)

        return predictions

    # ---------------------------------------------------------------- legacy sklearn

    def _predict_sklearn(
        self,
        model_id: str,
        df: pd.DataFrame,
        metadata: dict[str, Any],
        targets: list[str],
        input_features: list[str],
        window_size: int,
        algorithm: str,
        predicted_for_date: Any,
    ) -> dict[str, float]:
        base_cols = targets + input_features
        df_hist = df[["date", *base_cols]].dropna(subset=base_cols).copy()
        if len(df_hist) < window_size:
            raise PredictionServiceError(
                f"Datos insuficientes para predecir: se necesitan al menos {window_size} filas completas."
            )

        last = df_hist.iloc[-1]
        generated_date = pd.Timestamp(predicted_for_date)
        future_row: dict[str, Any] = {"date": generated_date}
        for col in base_cols:
            future_row[col] = last[col]

        df_future = pd.concat([df_hist, pd.DataFrame([future_row])], ignore_index=True)
        df_aug = _add_temporal_features(df_future, base_cols, window_size)
        df_aug = df_aug.drop(columns=["date"], errors="ignore").dropna()
        if df_aug.empty:
            raise PredictionServiceError("No se pudieron construir características temporales para la predicción.")

        row = df_aug.iloc[[-1]]
        models, scalers = self._storage.load_sklearn(model_id, targets)
        feature_columns_by_target = metadata.get("feature_columns_by_target") or {}
        predictions: dict[str, float] = {}

        for target in targets:
            feat_cols = feature_columns_by_target.get(target)
            if not feat_cols:
                feat_cols = [c for c in df_aug.columns if c != target]
            missing = [c for c in [target, *feat_cols] if c not in row.columns]
            if missing:
                raise PredictionServiceError(f"Columnas internas ausentes para {target}: {missing}")

            scaler = scalers[target]
            arr = scaler.transform(row[[target, *feat_cols]])
            pred_scaled = models[target].predict(arr[:, 1:]).reshape(-1, 1)
            pred = _desescalar_parcial(scaler, pred_scaled, 0).ravel()[0]
            predictions[target] = float(pred)

        return predictions
