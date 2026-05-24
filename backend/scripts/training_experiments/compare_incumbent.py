"""
Head-to-head: config v1 (incumbente, la que ya está en el UVL/registry activos) vs config v2
(ganador de treatment_winners) por (tratamiento, target), con el MISMO eval que el resto del harness
(re-evaluación en cada parcela por separado, sin pooling; score combinado = media de las 2 parcelas).

La "mejora vs baseline" de treatment_winners es contra los baselines naive del harness, NO contra v1.
Este script responde la pregunta correcta: ¿el ganador v2 bate de verdad a lo que ya hay (v1)?

Regla: se adopta v2 solo si su score combinado es ESTRICTAMENTE menor que el de v1; en caso contrario
se mantiene v1 (el incumbente gana empates → evita churn). Emite:
  - incumbent_comparison.md  (tabla v1 vs v2 + decisión)
  - uvl_snippets_final.md     (atributos UVL solo de los target que mejoran)
  - hyperprofiles_final.py    (entradas de registry solo de los target que mejoran)
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import numpy as np

from . import treatment_winners as TWmod
from .treatment_data import TREATMENT_CSVS, load_training_csv_frames, stations_of

logger = logging.getLogger(__name__)

# Config v1 actual (la del UVL activo + params del hyperprofile_registry). Hardcodeada porque es estable
# y mantiene este script Django-free. algo/window/feature_variant del UVL; params del registry v1.
V1_CONFIGS: dict[str, dict[str, dict]] = {
    "RiegoControl": {
        "MCD": {"algo": "PLSRegression", "window_size": 3, "feature_variant": "stress_indices",
                "params": {"n_components": 8, "scale": False}},
        "TasaBuenos": {"algo": "SVR", "window_size": 28, "feature_variant": "target_only",
                       "params": {"C": 100.0, "epsilon": 0.1, "gamma": "auto", "kernel": "linear"}},
        "TasaSeveros": {"algo": "LightGBM", "window_size": 3, "feature_variant": "soil_profile",
                        "params": {"learning_rate": 0.03, "max_depth": -1, "min_data_in_leaf": 5,
                                   "n_estimators": 1200, "num_leaves": 127, "reg_lambda": 0.1}},
    },
    "RiegoDeficitario": {
        "MCD": {"algo": "PLSRegression", "window_size": 3, "feature_variant": "stress_indices",
                "params": {"n_components": 8, "scale": False}},
        "TasaBuenos": {"algo": "PLSRegression", "window_size": 10, "feature_variant": "target_only",
                       "params": {"n_components": 5, "scale": False}},
        "TasaSeveros": {"algo": "LightGBM", "window_size": 7, "feature_variant": "soil_profile",
                        "params": {"learning_rate": 0.03, "max_depth": -1, "min_data_in_leaf": 5,
                                   "n_estimators": 1200, "num_leaves": 127, "reg_lambda": 0.1}},
    },
    "RiegoDeficitarioSevero": {
        "MCD": {"algo": "PLSRegression", "window_size": 3, "feature_variant": "stress_indices",
                "params": {"n_components": 8, "scale": False}},
        "TasaBuenos": {"algo": "ElasticNet", "window_size": 2, "feature_variant": "target_only",
                       "params": {"alpha": 0.001, "l1_ratio": 0.9, "max_iter": 20000}},
        "TasaSeveros": {"algo": "SVR", "window_size": 7, "feature_variant": "ema",
                        "params": {"C": 10.0, "epsilon": 0.2, "gamma": "auto", "kernel": "linear"}},
    },
}


def _combined_score(frames: dict, stations: list[str], target: str, cfg: dict) -> float:
    """Media del score de las 2 parcelas evaluadas por separado. inf si no evalúa en alguna."""
    scores: list[float] = []
    for station in stations:
        res = TWmod._eval_on_station(
            frames[station], target, cfg["window_size"], cfg["feature_variant"], cfg["algo"], cfg["params"]
        )
        if res is None:
            return float("inf")
        scores.append(res.score)
    return float(np.mean(scores)) if scores else float("inf")


def compare(winners_json: Path, output_dir: Path) -> dict:
    winners = json.loads(winners_json.read_text(encoding="utf-8"))
    frames = load_training_csv_frames()

    rows: list[dict] = []
    for treatment in TREATMENT_CSVS:
        stations = [s for s in stations_of(treatment) if s in frames]
        for target in TWmod.R.TARGETS:
            v1 = V1_CONFIGS.get(treatment, {}).get(target)
            v2_raw = winners.get(treatment, {}).get(target)
            if v1 is None or v2_raw is None:
                continue
            v2 = {"algo": v2_raw["algo"], "window_size": v2_raw["window_size"],
                  "feature_variant": v2_raw["feature_variant"], "params": v2_raw["params"]}
            s1 = _combined_score(frames, stations, target, v1)
            s2 = float(v2_raw.get("combined_score")) if v2_raw.get("combined_score") is not None else _combined_score(frames, stations, target, v2)
            decision = "v2" if s2 < s1 else "v1"
            delta = ((s1 - s2) / s1 * 100.0) if np.isfinite(s1) and s1 > 0 else None
            rows.append({
                "treatment": treatment, "target": target,
                "v1_algo": v1["algo"], "v1_variant": v1["feature_variant"], "v1_window": v1["window_size"], "v1_score": s1,
                "v2_algo": v2["algo"], "v2_variant": v2["feature_variant"], "v2_window": v2["window_size"], "v2_score": s2,
                "delta_pct": delta, "decision": decision, "v2_full": v2_raw,
            })
            logger.info("%s / %s: v1(%s)=%.4f vs v2(%s)=%.4f Δ=%s → %s",
                        treatment, target, v1["algo"], s1, v2["algo"], s2,
                        f"{delta:.1f}%" if delta is not None else "n/d", decision)

    _emit(rows, output_dir)
    return {"rows": rows, "applied": [r for r in rows if r["decision"] == "v2"]}


def _emit(rows: list[dict], output_dir: Path) -> None:
    cmp_md = ["# v1 (incumbente) vs v2 (ganador) — head-to-head", "",
              "Mismo eval que el harness: score combinado de las 2 parcelas (sin pooling).",
              "Se adopta v2 solo si su score combinado es estrictamente menor que el de v1.", ""]
    uvl = ["# Snippets UVL FINALES — solo los target donde v2 bate a v1", ""]
    hp = ['"""Entradas FINALES para HYPERPROFILE_REGISTRY — solo mejoras (v2 > v1)."""', "", "HYPERPROFILES_FINAL = {"]

    by_treatment: dict[str, list[dict]] = {}
    for r in rows:
        by_treatment.setdefault(r["treatment"], []).append(r)

    for treatment, trows in by_treatment.items():
        cmp_md.append(f"## {treatment}")
        cmp_md.append("")
        cmp_md.append("| Target | v1 (algo/var/W) | score v1 | v2 (algo/var/W) | score v2 | Δ% | Decisión |")
        cmp_md.append("|---|---|---|---|---|---|---|")
        applied = [r for r in trows if r["decision"] == "v2"]
        if applied:
            uvl.append(f"// ── {treatment} ──")
        for r in trows:
            d = f"{r['delta_pct']:.1f}%" if r["delta_pct"] is not None else "n/d"
            mark = "**v2**" if r["decision"] == "v2" else "v1 (mantener)"
            cmp_md.append(
                f"| {r['target']} | {r['v1_algo']}/{r['v1_variant']}/W{r['v1_window']} | {r['v1_score']:.4f} | "
                f"{r['v2_algo']}/{r['v2_variant']}/W{r['v2_window']} | {r['v2_score']:.4f} | {d} | {mark} |"
            )
            if r["decision"] == "v2":
                prod_algo = TWmod.ALGO_PROD_STRING.get(r["v2_algo"], r["v2_algo"])
                hp_name = TWmod._hyperprofile_name(treatment, r["target"], r["v2_algo"])
                uvl.append(
                    f"  pref_alg_{r['target']} '{prod_algo}', window_{r['target']} {r['v2_window']}, "
                    f"feat_variant_{r['target']} '{r['v2_variant']}', hyperprofile_{r['target']} '{hp_name}',"
                )
                req, opt = TWmod._hyperprofile_inputs(r["v2_variant"])
                hp.append(f'    "{hp_name}": {{')
                hp.append(f'        "algorithm": "{prod_algo}",')
                hp.append(f'        "feature_variant": "{r["v2_variant"]}",')
                hp.append(f'        "required_inputs": {req!r},')
                hp.append(f'        "optional_inputs": {opt!r},')
                hp.append(f'        "params": {TWmod._round_params(r["v2_full"]["params"])!r},')
                hp.append("    },")
        cmp_md.append("")
        if applied:
            uvl.append("")
    hp.append("}")

    n_applied = sum(1 for r in rows if r["decision"] == "v2")
    cmp_md.append(f"**Resumen:** se aplican {n_applied}/{len(rows)} (v2 bate a v1); el resto mantiene v1.")

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "incumbent_comparison.md").write_text("\n".join(cmp_md), encoding="utf-8")
    (output_dir / "uvl_snippets_final.md").write_text("\n".join(uvl), encoding="utf-8")
    (output_dir / "hyperprofiles_final.py").write_text("\n".join(hp), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Compara config v1 vs v2 y emite solo las mejoras.")
    parser.add_argument("--winners", type=Path, required=True, help="Ruta a treatment_winners.json")
    parser.add_argument("--output-dir", type=Path, default=None, help="Dir salida (def: dir de winners)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    out_dir = args.output_dir or args.winners.parent
    res = compare(args.winners, out_dir)
    applied = res["applied"]
    print(f"\nAplicar v2 en {len(applied)}: " + ", ".join(f"{r['treatment']}/{r['target']}" for r in applied))
    print(f"incumbent_comparison.md / uvl_snippets_final.md / hyperprofiles_final.py → {out_dir}")


if __name__ == "__main__":
    main()
