from __future__ import annotations

import io
import json
import shutil
import uuid
import zipfile
from pathlib import Path
from typing import Any

import joblib


class StorageError(RuntimeError):
    pass


class StorageService:
    # ------------------------------------------------------------------ paths

    def _base(self) -> Path:
        from django.conf import settings

        path = Path(settings.MODELS_STORAGE_PATH)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _model_dir(self, model_id: str, create: bool = False) -> Path:
        d = self._base() / model_id
        if create:
            d.mkdir(parents=True, exist_ok=True)
        elif not d.exists():
            raise StorageError(f"Modelo '{model_id}' no encontrado.")
        return d

    # --------------------------------------------------------------- metadata

    def save_metadata(self, model_id: str, metadata: dict[str, Any]) -> None:
        path = self._model_dir(model_id, create=True) / "metadata.json"
        path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")

    def load_metadata(self, model_id: str) -> dict[str, Any]:
        path = self._model_dir(model_id) / "metadata.json"
        if not path.exists():
            raise StorageError(f"metadata.json no encontrado para '{model_id}'.")
        metadata = json.loads(path.read_text(encoding="utf-8"))
        if "treatment" not in metadata and "crop" in metadata:
            metadata["treatment"] = metadata["crop"]
        metadata.pop("crop", None)
        return metadata

    # ------------------------------------------------------------------ LSTM

    def save_lstm(self, model_id: str, models: dict, scalers: dict) -> None:
        d = self._model_dir(model_id, create=True)
        for target, model in models.items():
            model.save(d / f"lstm_{target}.keras")
        for name, scaler in scalers.items():
            joblib.dump(scaler, d / f"scaler_{name}.pkl")

    def load_lstm(self, model_id: str, targets: list[str]) -> tuple[dict, Any, dict]:
        from tensorflow.keras.models import load_model  # type: ignore

        d = self._model_dir(model_id)
        lstm_models = {t: load_model(d / f"lstm_{t}.keras") for t in targets}
        scaler_X = joblib.load(d / "scaler_X.pkl")
        scaler_Y = {t: joblib.load(d / f"scaler_{t}.pkl") for t in targets}
        return lstm_models, scaler_X, scaler_Y

    # --------------------------------------------------------------- sklearn

    def save_sklearn(self, model_id: str, models: dict[str, Any], scalers: dict[str, Any]) -> None:
        d = self._model_dir(model_id, create=True)
        for target, model in models.items():
            joblib.dump(model, d / f"model_{target}.pkl")
        for target, scaler in scalers.items():
            joblib.dump(scaler, d / f"scaler_{target}.pkl")

    def load_sklearn(self, model_id: str, targets: list[str]) -> tuple[dict[str, Any], dict[str, Any]]:
        d = self._model_dir(model_id)
        models = {t: joblib.load(d / f"model_{t}.pkl") for t in targets}
        scalers = {t: joblib.load(d / f"scaler_{t}.pkl") for t in targets}
        return models, scalers

    # ------------------------------------------------------------------- CRUD

    def list_models(self) -> list[dict[str, Any]]:
        results = []
        for d in sorted(self._base().iterdir()):
            if not d.is_dir():
                continue
            meta = d / "metadata.json"
            if meta.exists():
                try:
                    results.append(json.loads(meta.read_text(encoding="utf-8")))
                except Exception:
                    pass
        return results

    def delete_model(self, model_id: str) -> None:
        shutil.rmtree(self._model_dir(model_id))

    # ----------------------------------------------------------------- export

    def export_zip(self, model_id: str) -> bytes:
        d = self._model_dir(model_id)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in d.rglob("*"):
                if f.is_file():
                    zf.write(f, f.name)
        return buf.getvalue()

    def import_zip(self, zip_bytes: bytes) -> str:
        buf = io.BytesIO(zip_bytes)
        try:
            with zipfile.ZipFile(buf, "r") as zf:
                names = zf.namelist()
                if "metadata.json" not in names:
                    raise StorageError("El ZIP no contiene metadata.json.")

                new_id = str(uuid.uuid4())
                d = self._model_dir(new_id, create=True)
                zf.extractall(d)
        except zipfile.BadZipFile:
            raise StorageError("El archivo no es un ZIP válido.")

        # Actualizar model_id en metadata
        meta_path = d / "metadata.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["model_id"] = new_id
        if "treatment" not in meta and "crop" in meta:
            meta["treatment"] = meta["crop"]
        meta.pop("crop", None)
        meta["imported"] = True
        meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

        return new_id
