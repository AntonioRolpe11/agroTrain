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


_REQUIRED_METADATA_TYPES = {
    "algorithm": str,
    "targets": list,
    "input_features": list,
    "all_cols": list,
    "metrics": dict,
    "window_size": int,
}


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

    def _validate_import_metadata(self, metadata: Any) -> dict[str, Any]:
        if not isinstance(metadata, dict):
            raise StorageError("metadata.json debe contener un objeto JSON.")

        normalized = dict(metadata)
        if "treatment" not in normalized and "crop" in normalized:
            normalized["treatment"] = normalized["crop"]
        normalized.pop("crop", None)

        required = {**_REQUIRED_METADATA_TYPES, "treatment": str}
        for field, expected_type in required.items():
            value = normalized.get(field)
            if not isinstance(value, expected_type):
                raise StorageError(f"metadata.json inválido: '{field}' debe ser {expected_type.__name__}.")

        for optional_list in ("features", "warnings"):
            value = normalized.get(optional_list, [])
            if not isinstance(value, list):
                raise StorageError(f"metadata.json inválido: '{optional_list}' debe ser list.")
            normalized[optional_list] = value

        for optional_int in ("n_samples", "n_train", "n_val"):
            value = normalized.get(optional_int, 0)
            if not isinstance(value, int):
                raise StorageError(f"metadata.json inválido: '{optional_int}' debe ser int.")
            normalized[optional_int] = value

        geo = normalized.get("geo", {})
        if not isinstance(geo, dict):
            raise StorageError("metadata.json inválido: 'geo' debe ser dict.")
        normalized["geo"] = geo

        return normalized

    @staticmethod
    def _safe_extract_zip(zf: zipfile.ZipFile, target_dir: Path) -> None:
        root = target_dir.resolve()
        for member in zf.infolist():
            member_path = Path(member.filename)
            if member_path.is_absolute() or ".." in member_path.parts:
                raise StorageError("ZIP contiene rutas no permitidas (ZipSlip).")
            target = (target_dir / member.filename).resolve()
            if root != target and root not in target.parents:
                raise StorageError("ZIP contiene rutas no permitidas (ZipSlip).")
        zf.extractall(target_dir)

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
        new_id = str(uuid.uuid4())
        d: Path | None = None
        try:
            with zipfile.ZipFile(buf, "r") as zf:
                names = zf.namelist()
                if "metadata.json" not in names:
                    raise StorageError("El ZIP no contiene metadata.json.")

                d = self._model_dir(new_id, create=True)
                self._safe_extract_zip(zf, d)
        except zipfile.BadZipFile:
            raise StorageError("El archivo no es un ZIP válido.")
        except Exception:
            if d is not None:
                shutil.rmtree(d, ignore_errors=True)
            raise

        # Actualizar model_id en metadata
        meta_path = d / "metadata.json"
        try:
            meta = self._validate_import_metadata(json.loads(meta_path.read_text(encoding="utf-8")))
        except json.JSONDecodeError as exc:
            shutil.rmtree(d, ignore_errors=True)
            raise StorageError("metadata.json no es JSON válido.") from exc
        except StorageError:
            shutil.rmtree(d, ignore_errors=True)
            raise
        meta["model_id"] = new_id
        meta["imported"] = True
        meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

        return new_id
