from __future__ import annotations

import io
from typing import Any

import numpy as np
import pandas as pd

from .storage_service import StorageService
from .training_service import _add_temporal_features, _desescalar_parcial


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

        if algorithm == "LSTM":
            predictions = self._predict_lstm(model_id, df, targets, all_cols, window_size)
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

    def _predict_lstm(
        self,
        model_id: str,
        df: pd.DataFrame,
        targets: list[str],
        all_cols: list[str],
        window_size: int,
    ) -> dict[str, float]:
        df_clean = df[all_cols].dropna().reset_index(drop=True)
        if len(df_clean) < window_size:
            raise PredictionServiceError(
                f"Datos insuficientes para predecir: se necesitan al menos {window_size} filas completas."
            )

        lstm_models, scaler_X, scaler_Y = self._storage.load_lstm(model_id, targets)
        window = df_clean[all_cols].tail(window_size)
        X = scaler_X.transform(window[all_cols]).astype("float32").reshape(1, window_size, len(all_cols))

        predictions: dict[str, float] = {}
        for target in targets:
            y_scaled = lstm_models[target].predict(X, verbose=0)
            value = scaler_Y[target].inverse_transform(y_scaled).ravel()[0]
            predictions[target] = float(value)
        return predictions

    def _predict_sklearn(
        self,
        model_id: str,
        df: pd.DataFrame,
        metadata: dict[str, Any],
        targets: list[str],
        input_features: list[str],
        window_size: int,
        algorithm: str,
        predicted_for_date,
    ) -> dict[str, float]:
        base_cols = targets + input_features
        df_hist = df[["date", *base_cols]].dropna(subset=base_cols).copy()
        if len(df_hist) < window_size:
            raise PredictionServiceError(
                f"Datos insuficientes para predecir: se necesitan al menos {window_size} filas completas."
            )

        # One-step inference: create a synthetic "now" row. Environmental inputs and
        # non-target current values use the last observed values; target lags still
        # come from the real historical window via shift().
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
