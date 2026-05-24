"""
Compare RiegoControl MCD profiles using the real TrainingService.

Config A (current):  control_mcd_xgb_v1  — XGBoost + irrigation_memory + window=3
Config B (candidate): PLS + stress_indices + window=3 (no dpv required)

Runs _run_pipeline() directly on Control_59 and Control_60 CSV data.
Reports R² from saved metadata.json.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

import django
django.setup()

import io
import uuid
import json

import pandas as pd

from scripts.training_experiments.data_prep import (
    PLATFORM_INPUTS_NO_TELEMETRY,
    prepare_station,
    to_platform_training_frame,
)
from apps.modelos.services.training_service import TrainingService
from apps.modelos.services.storage_service import StorageService
from apps.modelos.services import hyperprofile_registry as hp_reg

# ── Inject test profile for candidate config ──────────────────────────────────
# PLS + stress_indices adapted for Control data: no dpv required,
# pluv/riego in optional (present in Control), tmax/tmin required.
hp_reg.HYPERPROFILE_REGISTRY["control_mcd_pls_stress_v1_TEST"] = {
    "algorithm": "PLSRegression",
    "feature_variant": "stress_indices",
    "required_inputs": ["tmax", "tmin"],
    "optional_inputs": ["pluv", "riego", "hd_riego", "NDVI", "EVI", "SAVI", "NDWI"],
    "params": {"n_components": 8, "scale": False},
}

# ── Two UVL-derived feature lists ─────────────────────────────────────────────
# Both use same sensors available in Control CSV: tmax/tmin, pluv, Hd35/45/55.
# Only the treatment differs → different hyperprofile loaded by FlamapyService.

FEATURES_CONTROL = [
    "Entrada", "DatosParcela", "Tratamiento", "RiegoControl",
    "TipoSuelo", "Calcisoles",
    "ParametrosEntrada", "Dendrometro", "DatoMCD",
    "HumedadSuelo", "Hd35", "Hd45", "Hd55",
    "TemperaturaAire", "Pluviometro", "DPV", "Riego", "HumedadRiego",
    "DatosTelemetria",
    "VariableObjetivo", "MCD",
]

# Reproduces user's 86% experiment: RiegoDeficitarioSevero config + Control data.
# DPV mandatory (no Pluviometro), activates dpv_x_tmax and dpv_x_temp_range.
FEATURES_SEVERO_ON_CONTROL = [
    "Entrada", "DatosParcela", "Tratamiento", "RiegoDeficitarioSevero",
    "TipoSuelo", "Calcisoles",
    "ParametrosEntrada", "Dendrometro", "DatoMCD",
    "HumedadSuelo", "Hd35", "Hd45", "Hd55",
    "TemperaturaAire", "DPV",
    "DatosTelemetria",
    "VariableObjetivo", "MCD",
]

# For candidate: inject test hyperprofile into a fake treatment.
# Easiest: reuse RiegoControl treatment but temporarily override its hyperprofile_MCD.
# We do this by monkey-patching FlamapyService.get_treatment_target_profile.

STATIONS = ["Control_59_3-3_O", "Control_60_4-3_O"]


def df_to_csv_bytes(df: pd.DataFrame) -> bytes:
    """Convert to semicolon-separated CSV with BOM, matching platform format."""
    buf = io.StringIO()
    df.to_csv(buf, sep=";", index=False)
    return ("﻿" + buf.getvalue()).encode("utf-8")


def run_training(service: TrainingService, storage: StorageService,
                 targets, input_cols, treatment, csv_bytes, features, label):
    model_id = str(uuid.uuid4())
    print(f"    [{label}] model_id={model_id[:8]}…  treatment={treatment}")
    try:
        service._run_pipeline(
            model_id=model_id,
            targets=targets,
            input_cols=input_cols,
            treatment=treatment,
            csv_content=csv_bytes,
            features=features,
            geo={},
            user_id=None,
        )
        meta = storage.load_metadata(model_id)
        metrics = meta.get("metrics", {})
        warnings = meta.get("warnings", [])
        algo = meta.get("algorithm", "?")
        n_train = meta.get("n_train", "?")
        n_val = meta.get("n_val", "?")
        print(f"    [{label}] algo={algo}  n_train={n_train}  n_val={n_val}")
        for tgt, m in metrics.items():
            r2 = m.get("r2", float("nan"))
            mae = m.get("mae", float("nan"))
            print(f"      {tgt}: R²={r2:+.4f}  MAE={mae:.4f}")
        for w in warnings:
            print(f"      WARN: {w}")
        return metrics
    except Exception as exc:
        print(f"    [{label}] ERROR: {exc}")
        return None


def main():
    from apps.modelos.views import _features_to_training_params
    from apps.configurador.services.flamapy_service import FlamapyService

    service = TrainingService()
    storage = StorageService()

    # Derive input_cols from UVL for FEATURES_CONTROL
    targets_ctrl, input_cols_ctrl, treatment_ctrl = _features_to_training_params(FEATURES_CONTROL)
    print(f"\nControl features derived:")
    print(f"  targets={targets_ctrl}  treatment={treatment_ctrl}")
    print(f"  input_cols={input_cols_ctrl}\n")

    print("=" * 72)
    print("  RiegoControl MCD: XGBoost+irrigation_memory  vs  PLS+stress_indices")
    print("=" * 72)

    # Patch FlamapyService for candidate run
    _orig_get_ttp = FlamapyService.get_treatment_target_profile.__func__

    def _patched_get_ttp(cls, treatment, target):
        if treatment == "RiegoControl" and target == "MCD":
            return {
                "algorithm": "PLSRegression",
                "window_size": 3,
                "feature_variant": "stress_indices",
                "hyperprofile": "control_mcd_pls_stress_v1_TEST",
            }
        return _orig_get_ttp(cls, treatment, target)

    for station in STATIONS:
        print(f"\n── Station: {station} ──")
        try:
            raw, warns = prepare_station(station)
        except Exception as e:
            print(f"  ERROR: {e}")
            continue
        for w in warns:
            print(f"  WARN: {w}")

        df = to_platform_training_frame(
            raw,
            targets=["MCD", "TasaBuenos", "TasaSeveros"],
            input_cols=list(PLATFORM_INPUTS_NO_TELEMETRY) + ["riego", "hd_riego"],
        )
        print(f"  rows={len(df)}  cols={list(df.columns)}")
        csv_bytes = df_to_csv_bytes(df)

        print()
        # Config A: current production profile
        run_training(service, storage, targets_ctrl, input_cols_ctrl,
                     treatment_ctrl, csv_bytes, FEATURES_CONTROL, "A current XGB")

        print()
        # Config B: candidate PLS (RiegoControl treatment, patched profile)
        FlamapyService.get_treatment_target_profile = classmethod(
            lambda cls, treatment, target, _fn=_patched_get_ttp: _fn(cls, treatment, target)
        )
        try:
            run_training(service, storage, targets_ctrl, input_cols_ctrl,
                         treatment_ctrl, csv_bytes, FEATURES_CONTROL, "B PLS/ctrl-patched")
        finally:
            FlamapyService.get_treatment_target_profile = classmethod(
                lambda cls, treatment, target, _fn=_orig_get_ttp: _fn(cls, treatment, target)
            )

        print()
        # Config C: reproduce user's 86% — RiegoDeficitarioSevero config on Control data
        # Uses real secano_mcd_pls_v1 profile: dpv required, no pluv/riego in input_cols
        targets_sev, input_cols_sev, treatment_sev = _features_to_training_params(FEATURES_SEVERO_ON_CONTROL)
        run_training(service, storage, targets_sev, input_cols_sev,
                     treatment_sev, csv_bytes, FEATURES_SEVERO_ON_CONTROL, "C PLS/severo-on-ctrl (real)")

    print("\nDone.")


if __name__ == "__main__":
    main()
