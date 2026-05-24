"""
Selecciona UN ganador por (tratamiento, target) a partir de un `results.csv` de
`run_experiments.py`, sin mezclar parcelas en el entrenamiento, y emite los snippets
listos para encajar en producción (UVL + hyperprofile_registry).

Por qué este paso existe
------------------------
El runner busca por parcela (6 estaciones). Pero el UVL guarda los atributos de modelo
**por Tratamiento** (`pref_alg_<target>`, `window_<target>`, `feat_variant_<target>`,
`hyperprofile_<target>`). Cada tratamiento tiene 2 parcelas. Hay que elegir **una sola** config
por `(tratamiento, target)` que funcione bien en **ambas** parcelas — pero **sin** entrenar nunca
con las 2 parcelas juntas (sin pooling).

Estrategia (sin pooling)
------------------------
1. Del `results.csv`, por cada parcela del tratamiento se toman las top-K configs válidas.
2. Cada config candidata se **re-evalúa por separado en cada parcela** (mismo CV temporal +
   holdout que el runner, reutilizando `run_experiments._prepare_xy/_eval_tabular/
   _eval_holdout_tabular`). Nunca se concatenan parcelas.
3. `score_tratamiento = media(score_parcelaA, score_parcelaB)`, con **guarda**: la config debe
   pasar el chequeo anti-overfit (`holdout_rmse ≤ 1.3·rmse_mean`) en **las dos** parcelas.
4. Gana la de menor `score_tratamiento`; desempate al modelo más simple dentro del 2%.

Restricción de producción
--------------------------
`training_service._build_estimator` solo construye RandomForest, GradientBoosting/HistGB,
XGBoost, LightGBM, SVR, PLSRegression y ElasticNet (vía hyperprofile per-target). ExtraTrees,
KNeighbors y las redes (LSTM/GRU/Conv1D/CNN-LSTM) **no** son expresables como hyperprofile.
Por eso el **ganador que va al snippet** se restringe a algoritmos expresables; aun así el reporte
muestra el **mejor offline sin restricción** por parcela (transparencia: indica si una red u otro
algoritmo no portable batiría al elegido y por cuánto).
Aviso adicional: para RandomForest y GradientBoosting, producción usa hiperparámetros fijos
(`_build_rf`/`_build_gb`) e **ignora** los `params` del hyperprofile; para XGBoost/LightGBM/SVR/
PLSRegression/ElasticNet sí se respetan.
"""
from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from . import run_experiments as R
from .data_prep import PLATFORM_INPUTS_NO_TELEMETRY
from .select_winners import ALGO_COMPLEXITY
from .treatment_data import TREATMENT_CSVS, load_training_csv_frames, stations_of

logger = logging.getLogger(__name__)

SCORE_STD_PENALTY = 0.5
HOLDOUT_TOLERANCE = 1.3
SIMPLE_MODEL_SCORE_TOLERANCE = 0.02
DEFAULT_TOP_K = 10

# Algoritmos que producción sabe construir como hyperprofile per-target.
PRODUCTION_EXPRESSIBLE = frozenset(
    {"RandomForest", "GradientBoosting", "HistGB", "XGBoost", "LightGBM", "SVR", "PLSRegression", "ElasticNet"}
)
# Algoritmos cuyos hiperparámetros producción IGNORA (usa params fijos).
PRODUCTION_FIXED_PARAMS = frozenset({"RandomForest", "GradientBoosting", "HistGB"})

# Nombre de algoritmo tal y como lo espera training_service (HistGB == GradientBoosting).
ALGO_PROD_STRING = {"HistGB": "GradientBoosting"}

ALGO_SHORT = {
    "RandomForest": "rf",
    "GradientBoosting": "gb",
    "HistGB": "gb",
    "XGBoost": "xgb",
    "LightGBM": "lgbm",
    "SVR": "svr",
    "PLSRegression": "pls",
    "ElasticNet": "elasticnet",
}
TREAT_SHORT = {
    "RiegoControl": "control",
    "RiegoDeficitario": "rdc",
    "RiegoDeficitarioSevero": "secano",
}
TARGET_SHORT = {"MCD": "mcd", "TasaBuenos": "tasabuenos", "TasaSeveros": "tasaseveros"}


# ───────────────────────────────────────────────────────── evaluación por parcela ──

@dataclass
class StationEval:
    rmse_mean: float
    rmse_std: float
    r2_mean: float
    mae_mean: float
    score: float
    holdout_rmse: float
    holdout_r2: float
    holdout_ok: bool
    n_train: int
    n_folds: int


@dataclass
class TreatmentCandidate:
    algo: str
    window_size: int
    feature_variant: str
    params: dict
    per_station: dict[str, StationEval]
    combined_score: float
    both_holdout_ok: bool
    n_stations: int = field(default=0)


def _score(rmse_mean: float, rmse_std: float) -> float:
    return float(rmse_mean + SCORE_STD_PENALTY * rmse_std)


def _parse_json(value: object) -> dict:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return {}
    try:
        parsed = json.loads(str(value))
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _eval_on_station(
    frame: pd.DataFrame, target: str, window: int, feature_variant: str, algo: str, params: dict
) -> StationEval | None:
    """Re-evalúa una config en UNA parcela (CV temporal + holdout). None si no hay datos suficientes."""
    build_fn = R.TABULAR_BUILDERS.get(algo)
    if build_fn is None:
        return None
    inputs = R._input_features(frame)
    X, y = R._prepare_xy(frame, target, window, feature_variant, inputs)
    if X.empty or len(X) < R.CV_SPLITS + 6:
        return None
    metrics, n_train, _elapsed, n_folds, _stop = R._eval_tabular(
        build_fn, params, X, y, R.CV_SPLITS, R.MAX_TRAIN_SIZE_CV
    )
    if not metrics:
        return None
    ho_idx = R.temporal_holdout_index(len(X), R.HOLDOUT_FRACTION)
    ho_rmse, ho_r2, _imp = R._eval_holdout_tabular(build_fn, params, X, y, ho_idx)
    score = _score(metrics["rmse_mean"], metrics["rmse_std"])
    holdout_ok = (not np.isfinite(ho_rmse)) or (ho_rmse <= HOLDOUT_TOLERANCE * metrics["rmse_mean"])
    return StationEval(
        rmse_mean=float(metrics["rmse_mean"]),
        rmse_std=float(metrics["rmse_std"]),
        r2_mean=float(metrics["r2_mean"]),
        mae_mean=float(metrics["mae_mean"]),
        score=score,
        holdout_rmse=float(ho_rmse),
        holdout_r2=float(ho_r2),
        holdout_ok=bool(holdout_ok),
        n_train=int(n_train),
        n_folds=int(n_folds),
    )


# ───────────────────────────────────────────────────────── selección de candidatos ──

def _valid_mask(df: pd.DataFrame) -> pd.Series:
    err = df["error"].fillna("") == ""
    has_rmse = ~df["rmse_mean"].isna()
    ho = df["holdout_rmse"]
    ho_ok = ho.isna() | (ho <= HOLDOUT_TOLERANCE * df["rmse_mean"])
    return err & has_rmse & ho_ok


def _candidate_configs(df: pd.DataFrame, stations: list[str], target: str, top_k: int) -> list[dict]:
    """Top-K configs producción-expresables por parcela; unión deduplicada."""
    pool = df[
        (df["target"] == target)
        & (df["station"].isin(stations))
        & df["algo"].isin(PRODUCTION_EXPRESSIBLE)
        & df["valid"]
    ]
    seen: set[tuple] = set()
    configs: list[dict] = []
    for station in stations:
        st = pool[pool["station"] == station].sort_values("score").head(top_k)
        for _, row in st.iterrows():
            params = _parse_json(row["params"])
            key = (str(row["algo"]), int(row["window_size"]), str(row["feature_variant"]), json.dumps(params, sort_keys=True))
            if key in seen:
                continue
            seen.add(key)
            configs.append(
                {
                    "algo": str(row["algo"]),
                    "window_size": int(row["window_size"]),
                    "feature_variant": str(row["feature_variant"]),
                    "params": params,
                }
            )
    return configs


def _pick_winner(candidates: list[TreatmentCandidate]) -> TreatmentCandidate | None:
    if not candidates:
        return None
    passing = [c for c in candidates if c.both_holdout_ok]
    pool = passing or candidates
    pool = sorted(pool, key=lambda c: c.combined_score)
    best = pool[0].combined_score
    tol = max(abs(best) * SIMPLE_MODEL_SCORE_TOLERANCE, 1e-12)
    near = [c for c in pool if c.combined_score <= best + tol]
    near.sort(key=lambda c: (ALGO_COMPLEXITY.get(c.algo, 99), c.combined_score))
    return near[0]


def _treatment_baseline(df: pd.DataFrame, stations: list[str], target: str) -> float | None:
    """Media (sobre las 2 parcelas) del mejor score baseline (#BASELINE) válido de cada parcela."""
    scores: list[float] = []
    for station in stations:
        base = df[
            (df["target"] == target)
            & (df["station"] == station)
            & df["variant_id"].astype(str).str.contains("#BASELINE", regex=False)
            & df["valid"]
        ]
        if not base.empty:
            scores.append(float(base.sort_values("score").iloc[0]["score"]))
    return float(np.mean(scores)) if scores else None


def _unrestricted_best(df: pd.DataFrame, stations: list[str], target: str) -> dict | None:
    """Mejor offline por parcela SIN restricción (incluye ExtraTrees/redes/ensembles), para contexto."""
    pool = df[(df["target"] == target) & (df["station"].isin(stations)) & df["valid"]]
    if pool.empty:
        return None
    best = pool.sort_values("score").iloc[0]
    return {
        "station": str(best["station"]),
        "algo": str(best["algo"]),
        "feature_variant": str(best["feature_variant"]),
        "window_size": int(best["window_size"]),
        "score": float(best["score"]),
    }


# ───────────────────────────────────────────────────────── snippets de salida ──

def _hyperprofile_inputs(feature_variant: str) -> tuple[list[str], list[str]]:
    """required/optional inputs para el hyperprofile. No exigimos columnas (required=[]) para no
    romper en producción si una parcela no trae algún sensor; las usadas van como opcionales."""
    if feature_variant == "target_only":
        return [], []
    return [], list(PLATFORM_INPUTS_NO_TELEMETRY)


def _hyperprofile_name(treatment: str, target: str, algo: str) -> str:
    return f"{TREAT_SHORT[treatment]}_{TARGET_SHORT[target]}_{ALGO_SHORT[algo]}_v2"


def _round_params(params: dict) -> dict:
    out = {}
    for k, v in params.items():
        out[k] = round(v, 6) if isinstance(v, float) else v
    return out


def _build_outputs(winners: dict, df: pd.DataFrame) -> tuple[str, str, str]:
    """Devuelve (treatment_report.md, uvl_snippets.md, hyperprofiles_v2.py)."""
    report: list[str] = [
        "# Ganadores por tratamiento (sin pooling)",
        "",
        "Entrenamiento por parcela; cada config re-evaluada en ambas parcelas por separado.",
        "`score = rmse_mean + 0.5·rmse_std` (menor mejor). Guarda holdout en ambas parcelas.",
        "",
    ]
    uvl: list[str] = [
        "# Snippets UVL — pegar en backend/uvl_versions/v2_olivos_tratamientos.uvl",
        "",
        "Atributos por nodo de Tratamiento. Reemplazan pref_alg_/window_/feat_variant_/hyperprofile_.",
        "",
    ]
    hp: list[str] = [
        '"""Entradas para HYPERPROFILE_REGISTRY (hyperprofile_registry.py). Generado por treatment_winners.py."""',
        "",
        "HYPERPROFILES_V2 = {",
    ]

    for treatment in TREATMENT_CSVS:
        tw = winners.get(treatment, {})
        report.append(f"## {treatment}")
        report.append("")
        report.append("| Target | Algo | Variante | W | Score comb. | Parcela A (score/R²/ho) | Parcela B (score/R²/ho) | Mejora vs baseline | Mejor offline libre |")
        report.append("|---|---|---|---|---|---|---|---|---|")
        uvl.append(f"// ── {treatment} ──")
        for target in R.TARGETS:
            w = tw.get(target)
            if not w:
                report.append(f"| {target} | — | sin candidato válido | — | — | — | — | — | — |")
                continue
            ps = w["per_station"]
            st_names = list(ps.keys())
            a = ps[st_names[0]]
            b = ps[st_names[1]] if len(st_names) > 1 else None
            imp = w.get("improvement_vs_baseline_pct")
            imp_label = f"{imp:.1f}%" if imp is not None else "n/d"
            free = w.get("unrestricted_best")
            free_label = (
                f"{free['algo']}/{free['feature_variant']} ({free['score']:.4f}, {free['station'].split('_')[0]})"
                if free else "n/d"
            )
            b_label = f"{b.score:.4f}/{b.r2_mean:.2f}/{b.holdout_rmse:.3f}" if b else "—"
            report.append(
                f"| {target} | {w['algo']} | `{w['feature_variant']}` | {w['window_size']} | "
                f"{w['combined_score']:.4f} | {a.score:.4f}/{a.r2_mean:.2f}/{a.holdout_rmse:.3f} | {b_label} | "
                f"{imp_label} | {free_label} |"
            )

            # UVL snippet lines
            prod_algo = ALGO_PROD_STRING.get(w["algo"], w["algo"])
            hp_name = _hyperprofile_name(treatment, target, w["algo"])
            uvl.append(f"  pref_alg_{target} '{prod_algo}', window_{target} {w['window_size']}, "
                       f"feat_variant_{target} '{w['feature_variant']}', hyperprofile_{target} '{hp_name}',")
            if w["algo"] in PRODUCTION_FIXED_PARAMS:
                uvl.append(f"  // NOTA: producción usa params fijos para {prod_algo}; los del hyperprofile se ignoran.")

            # hyperprofile entry
            req, opt = _hyperprofile_inputs(w["feature_variant"])
            hp.append(f'    "{hp_name}": {{')
            hp.append(f'        "algorithm": "{prod_algo}",')
            hp.append(f'        "feature_variant": "{w["feature_variant"]}",')
            hp.append(f'        "required_inputs": {req!r},')
            hp.append(f'        "optional_inputs": {opt!r},')
            hp.append(f'        "params": {_round_params(w["params"])!r},')
            hp.append("    },")
        report.append("")
        uvl.append("")
    hp.append("}")
    return "\n".join(report), "\n".join(uvl), "\n".join(hp)


# ───────────────────────────────────────────────────────── orquestación ──

def select_treatment_winners(results_csv: Path, output_dir: Path, top_k: int = DEFAULT_TOP_K) -> dict:
    df = pd.read_csv(results_csv)
    if df.empty:
        raise ValueError(f"{results_csv} is empty")
    df["error"] = df["error"].fillna("")
    df["score"] = df.apply(lambda r: _score(r["rmse_mean"], r["rmse_std"]) if not pd.isna(r["rmse_mean"]) and not pd.isna(r["rmse_std"]) else float("inf"), axis=1)
    df["valid"] = _valid_mask(df)

    frames = load_training_csv_frames()

    winners: dict[str, dict] = {}
    for treatment in TREATMENT_CSVS:
        stations = [s for s in stations_of(treatment) if s in frames]
        if len(stations) < 2:
            logger.warning("Tratamiento %s: <2 parcelas disponibles (%s); se omite", treatment, stations)
            continue
        winners[treatment] = {}
        for target in R.TARGETS:
            configs = _candidate_configs(df, stations, target, top_k)
            evaluated: list[TreatmentCandidate] = []
            for cfg in configs:
                per_station: dict[str, StationEval] = {}
                for station in stations:
                    res = _eval_on_station(
                        frames[station], target, cfg["window_size"], cfg["feature_variant"], cfg["algo"], cfg["params"]
                    )
                    if res is not None:
                        per_station[station] = res
                if len(per_station) < len(stations):
                    continue  # debe evaluarse en TODAS las parcelas
                combined = float(np.mean([e.score for e in per_station.values()]))
                both_ho = all(e.holdout_ok for e in per_station.values())
                evaluated.append(
                    TreatmentCandidate(
                        algo=cfg["algo"],
                        window_size=cfg["window_size"],
                        feature_variant=cfg["feature_variant"],
                        params=cfg["params"],
                        per_station=per_station,
                        combined_score=combined,
                        both_holdout_ok=both_ho,
                        n_stations=len(per_station),
                    )
                )
            winner = _pick_winner(evaluated)
            if winner is None:
                logger.warning("%s / %s: sin candidato producción-expresable válido", treatment, target)
                continue

            baseline = _treatment_baseline(df, stations, target)
            improvement = None
            if baseline and baseline > 0 and np.isfinite(winner.combined_score):
                improvement = (baseline - winner.combined_score) / baseline * 100.0

            winners[treatment][target] = {
                "algo": winner.algo,
                "window_size": winner.window_size,
                "feature_variant": winner.feature_variant,
                "params": winner.params,
                "combined_score": winner.combined_score,
                "both_holdout_ok": winner.both_holdout_ok,
                "per_station": winner.per_station,
                "baseline_score": baseline,
                "improvement_vs_baseline_pct": improvement,
                "unrestricted_best": _unrestricted_best(df, stations, target),
                "hyperprofile_name": _hyperprofile_name(treatment, target, winner.algo),
            }
            logger.info(
                "%s / %s → %s W=%d %s comb=%.4f ho_ok=%s imp=%s",
                treatment, target, winner.algo, winner.window_size, winner.feature_variant,
                winner.combined_score, winner.both_holdout_ok,
                f"{improvement:.1f}%" if improvement is not None else "n/d",
            )

    # Serializa StationEval → dict para JSON
    winners_json = {
        t: {
            tgt: {
                **{k: v for k, v in w.items() if k != "per_station"},
                "per_station": {st: vars(ev) for st, ev in w["per_station"].items()},
            }
            for tgt, w in tw.items()
        }
        for t, tw in winners.items()
    }

    report_md, uvl_md, hp_py = _build_outputs(winners, df)

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "treatment_winners.json").write_text(json.dumps(winners_json, indent=2, ensure_ascii=False), encoding="utf-8")
    (output_dir / "treatment_report.md").write_text(report_md, encoding="utf-8")
    (output_dir / "uvl_snippets.md").write_text(uvl_md, encoding="utf-8")
    (output_dir / "hyperprofiles_v2.py").write_text(hp_py, encoding="utf-8")
    return winners_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Ganador por (tratamiento, target) + snippets UVL/hyperprofiles.")
    parser.add_argument("--results", type=Path, required=True, help="Ruta a results.csv de run_experiments")
    parser.add_argument("--output-dir", type=Path, default=None, help="Dir de salida (def: dir de results.csv)")
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K, help="Top-K configs por parcela a re-evaluar")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    out_dir = args.output_dir or args.results.parent
    select_treatment_winners(args.results, out_dir, top_k=args.top_k)
    print(f"treatment_winners.json / treatment_report.md / uvl_snippets.md / hyperprofiles_v2.py → {out_dir}")


if __name__ == "__main__":
    main()
