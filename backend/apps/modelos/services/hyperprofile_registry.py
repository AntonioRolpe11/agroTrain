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
    # ── RiegoControl ─────────────────────────────────────────────────────────
    "control_mcd_xgb_v1": {
        "algorithm": "XGBoost",
        "feature_variant": "irrigation_memory",
        "required_inputs": ["tmax"],
        "optional_inputs": ["dpv", "pluv", "riego", "hd_riego"],
        "params": {
            "colsample_bytree": 1.0,
            "learning_rate": 0.08,
            "max_depth": 5,
            "min_child_weight": 7,
            "n_estimators": 600,
            "reg_lambda": 1.0,
            "subsample": 1.0,
        },
    },
    "control_tasabuenos_svr_v1": {
        "algorithm": "SVR",
        "feature_variant": "target_only",
        "required_inputs": [],
        "optional_inputs": [],
        "params": {"C": 100.0, "epsilon": 0.1, "gamma": "auto", "kernel": "linear"},
        # linear kernel + target_only (~28 features); warn above 500 training rows
        "max_samples": 2000,
    },
    "control_tasaseveros_lgbm_v1": {
        "algorithm": "LightGBM",
        "feature_variant": "soil_profile",
        "required_inputs": ["tmax", "tmin"],
        "optional_inputs": ["dpv", "pluv"],
        "params": {
            "learning_rate": 0.03,
            "max_depth": -1,
            "min_data_in_leaf": 5,
            "n_estimators": 1200,
            "num_leaves": 127,
            "reg_lambda": 0.1,
            "verbose": -1,
        },
    },
    # ── RiegoDeficitario ─────────────────────────────────────────────────────
    "rdc_mcd_pls_v1": {
        "algorithm": "PLSRegression",
        "feature_variant": "irrigation_memory",
        "required_inputs": [],
        "optional_inputs": ["dpv", "pluv"],
        "params": {"n_components": 3, "scale": False},
    },
    "rdc_tasabuenos_pls_v1": {
        "algorithm": "PLSRegression",
        "feature_variant": "target_only",
        "required_inputs": [],
        "optional_inputs": [],
        "params": {"n_components": 5, "scale": False},
    },
    "rdc_tasaseveros_svr_v1": {
        "algorithm": "SVR",
        "feature_variant": "target_only",
        "required_inputs": [],
        "optional_inputs": [],
        "params": {"C": 100.0, "epsilon": 0.2, "gamma": "auto", "kernel": "rbf"},
        # holdout_r2=0.0 (constant-zero holdout); quality_min check warns at runtime
        "max_samples": 2000,
    },
    # ── RiegoDeficitarioSevero (Secano) ───────────────────────────────────────
    "secano_mcd_pls_v1": {
        "algorithm": "PLSRegression",
        "feature_variant": "stress_indices",
        "required_inputs": ["tmax", "tmin", "dpv"],
        "optional_inputs": ["pluv", "NDVI", "EVI", "SAVI", "NDWI"],
        "params": {"n_components": 8, "scale": False},
    },
    "secano_tasabuenos_elasticnet_v1": {
        "algorithm": "ElasticNet",
        "feature_variant": "target_only",
        "required_inputs": [],
        "optional_inputs": [],
        "params": {"alpha": 0.001, "l1_ratio": 0.9, "max_iter": 20000},
    },
    "secano_tasaseveros_svr_v1": {
        "algorithm": "SVR",
        "feature_variant": "ema",
        "required_inputs": [],
        "optional_inputs": ["dpv"],
        "params": {"C": 10.0, "epsilon": 0.2, "gamma": "auto", "kernel": "linear"},
        # holdout_r2=0.0 (constant-zero holdout); quality_min check warns at runtime
        "max_samples": 2000,
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
