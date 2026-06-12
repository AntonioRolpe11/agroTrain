from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest

from apps.modelos.services.storage_service import StorageError, StorageService


@pytest.fixture
def storage(tmp_path, settings):
    settings.MODELS_STORAGE_PATH = tmp_path
    return StorageService()


METADATA_OK = {
    "model_id": "x",
    "algorithm": "RandomForest",
    "treatment": "Secano",
    "targets": ["MCD"],
    "input_features": ["tmax"],
    "all_cols": ["MCD", "tmax"],
    "metrics": {},
    "window_size": 5,
    "n_samples": 10,
    "n_train": 8,
    "n_val": 2,
    "warnings": [],
    "features": [],
    "geo": {},
}


class TestMetadata:
    def test_save_then_load_roundtrip(self, storage):
        storage.save_metadata("m1", METADATA_OK)
        loaded = storage.load_metadata("m1")
        assert loaded["model_id"] == "x"
        assert loaded["algorithm"] == "RandomForest"

    def test_load_metadata_normalises_legacy_crop_to_treatment(self, storage, tmp_path):
        model_dir = tmp_path / "legacy"
        model_dir.mkdir()
        legacy = {"algorithm": "RF", "targets": [], "input_features": [], "all_cols": [], "metrics": {},
                  "window_size": 5, "crop": "OldName"}
        (model_dir / "metadata.json").write_text(json.dumps(legacy), encoding="utf-8")
        loaded = storage.load_metadata("legacy")
        assert loaded["treatment"] == "OldName"
        assert "crop" not in loaded

    def test_load_missing_model_raises(self, storage):
        with pytest.raises(StorageError, match="no encontrado"):
            storage.load_metadata("does-not-exist")


class TestListModels:
    def test_list_includes_saved_metadata(self, storage):
        storage.save_metadata("m1", METADATA_OK)
        storage.save_metadata("m2", METADATA_OK)
        result = storage.list_models()
        assert len(result) == 2


class TestDeleteModel:
    def test_delete_removes_model_directory(self, storage, tmp_path):
        storage.save_metadata("to-del", METADATA_OK)
        assert (tmp_path / "to-del").exists()
        storage.delete_model("to-del")
        assert not (tmp_path / "to-del").exists()

    def test_delete_unknown_raises(self, storage):
        with pytest.raises(StorageError):
            storage.delete_model("nope")


class TestExportImport:
    def test_export_zip_round_trips(self, storage):
        storage.save_metadata("orig", METADATA_OK)
        zip_bytes = storage.export_zip("orig")
        new_id = storage.import_zip(zip_bytes)
        meta = storage.load_metadata(new_id)
        assert meta["model_id"] == new_id
        assert meta["imported"] is True

    def test_import_rejects_zipslip(self, storage):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("metadata.json", json.dumps(METADATA_OK))
            zf.writestr("../escape.txt", "bad")
        with pytest.raises(StorageError, match="ZipSlip"):
            storage.import_zip(buf.getvalue())

    def test_import_rejects_zip_without_metadata(self, storage):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("just_a_file.txt", "no metadata")
        with pytest.raises(StorageError, match="metadata.json"):
            storage.import_zip(buf.getvalue())

    def test_import_rejects_invalid_json(self, storage):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("metadata.json", "{ broken")
        with pytest.raises(StorageError, match="JSON"):
            storage.import_zip(buf.getvalue())

    def test_import_rejects_bad_zip(self, storage):
        with pytest.raises(StorageError, match="ZIP"):
            storage.import_zip(b"not a zip")

    def test_import_validates_required_fields(self, storage):
        incomplete = {"algorithm": "RF", "targets": []}  # missing input_features, etc.
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("metadata.json", json.dumps(incomplete))
        with pytest.raises(StorageError):
            storage.import_zip(buf.getvalue())
