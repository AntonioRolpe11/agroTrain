"""
Versioned hyperparameter profiles for olive ML models.

Each profile is identified by a stable string key referenced in the UVL via
hyperprofile_<target> attributes on treatment nodes.  Adding a new profile
never modifies existing keys — models trained with an older profile remain
reproducible on reload.

Derived from offline experimentation (full_platform_no_telemetry run,
docs/experimentacion_modelos.md, 2026-05-08).
"""
from __future__ import annotations

import copy
from typing import Any


HYPERPROFILE_REGISTRY: dict[str, dict[str, Any]] = {
    # ── MCD (todos los tratamientos) ─────────────────────────────────────────
    "secano_mcd_pls_v1": {
        "algorithm": "PLSRegression",
        "feature_variant": "stress_indices",
        "required_inputs": ["tmax", "tmin", "dpv"],
        "optional_inputs": ["NDVI", "EVI", "SAVI", "NDWI"],
        "params": {"n_components": 8, "scale": False},
    },
    # ── v3 (sensores riego+lluvia, búsqueda buscar_config_sensores.py, 2026-06-08) ────────────
    # TasaBuenos y TasaSeveros usan riego/lluvia como entrada (decisión de diseño del
    # usuario: preferir variables físicas frente a autorregresión pura).
    # required_inputs=[] a propósito: riego/lluvia no están en todas las parcelas (graceful).
    "control_tasabuenos_elasticnet_v3": {
        "algorithm": "ElasticNet",
        "feature_variant": "full",
        "required_inputs": [],
        "optional_inputs": ["riego", "lluvia", "tmax", "tmin", "dpv", "humedad_Hd35"],
        "params": {"alpha": 0.01, "l1_ratio": 0.5, "max_iter": 20000},
    },
    "control_tasaseveros_gb_v3": {
        "algorithm": "GradientBoosting",
        "feature_variant": "basic",
        "required_inputs": [],
        "optional_inputs": ["riego", "lluvia", "tmax", "tmin", "dpv", "humedad_Hd35"],
        "params": {},
    },
    "rdc_tasabuenos_rf_v3": {
        "algorithm": "RandomForest",
        "feature_variant": "full",
        "required_inputs": [],
        "optional_inputs": ["riego", "lluvia", "tmax", "tmin", "dpv", "humedad_Hd35"],
        "params": {},
    },
    "rdc_tasaseveros_gb_v3": {
        "algorithm": "GradientBoosting",
        "feature_variant": "full",
        "required_inputs": [],
        "optional_inputs": ["riego", "lluvia", "tmax", "tmin", "dpv", "humedad_Hd35"],
        "params": {},
    },
    "secano_tasabuenos_svr_v3": {
        "algorithm": "SVR",
        "feature_variant": "stress_indices",
        "required_inputs": [],
        "optional_inputs": ["riego", "lluvia", "tmax", "tmin", "dpv", "humedad_Hd35"],
        "params": {"C": 100.0, "epsilon": 0.1, "gamma": "auto", "kernel": "linear"},
        "max_samples": 2000,
    },
    "secano_tasaseveros_gb_v3": {
        "algorithm": "GradientBoosting",
        "feature_variant": "full",
        "required_inputs": [],
        "optional_inputs": ["riego", "lluvia", "tmax", "tmin", "dpv", "humedad_Hd35"],
        "params": {},
    },
}


class UnknownHyperprofileError(ValueError):
    pass


def get_hyperprofile(profile_name: str) -> dict[str, Any]:
    """Return a copy of the named hyperparameter profile."""
    if profile_name not in HYPERPROFILE_REGISTRY:
        raise UnknownHyperprofileError(
            f"Perfil desconocido: {profile_name!r}. "
            f"Disponibles: {sorted(HYPERPROFILE_REGISTRY)}"
        )
    return copy.deepcopy(HYPERPROFILE_REGISTRY[profile_name])
