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
        "optional_inputs": ["dpv"],
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
        "optional_inputs": ["dpv"],
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
        "optional_inputs": ["dpv"],
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
        "optional_inputs": ["NDVI", "EVI", "SAVI", "NDWI"],
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
    # ── v2 (experimentación olivos, results/20260605_051135, 2026-06-05) ──────
    # Solo los target que baten a v1 en head-to-head: RDC y Secano TasaBuenos/TasaSeveros.
    # Ver docs/experimentacion_olivos_v2.md.
    "rdc_tasabuenos_pls_v2": {
        "algorithm": "PLSRegression",
        "feature_variant": "target_only",
        "required_inputs": [],
        "optional_inputs": [],
        "params": {"n_components": 8, "scale": False},
    },
    "rdc_tasaseveros_elasticnet_v2": {
        "algorithm": "ElasticNet",
        "feature_variant": "target_only",
        "required_inputs": [],
        "optional_inputs": [],
        "params": {"alpha": 0.01, "l1_ratio": 0.5, "max_iter": 20000},
    },
    "secano_tasabuenos_pls_v2": {
        "algorithm": "PLSRegression",
        "feature_variant": "target_only",
        "required_inputs": [],
        "optional_inputs": [],
        "params": {"n_components": 8, "scale": False},
    },
    "secano_tasaseveros_svr_v2": {
        "algorithm": "SVR",
        "feature_variant": "stress_indices",
        "required_inputs": [],
        "optional_inputs": ["humedad_Hd05", "humedad_Hd15", "humedad_Hd25", "humedad_Hd35",
                            "humedad_Hd45", "humedad_Hd55", "humedad_Hd65", "humedad_Hd75",
                            "tmax", "tmin", "dpv"],
        "params": {"C": 100.0, "epsilon": 0.01, "gamma": "scale", "kernel": "linear"},
        "max_samples": 2000,
    },
    # ── v3 (sensores riego+lluvia, búsqueda buscar_config_sensores.py, 2026-06-08) ────────────
    # TasaBuenos y TasaSeveros pasan de target_only a modelos que usan riego/lluvia como entrada
    # (decisión de diseño del usuario: preferir variables físicas frente a autorregresión pura).
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
