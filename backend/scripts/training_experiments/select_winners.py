"""
Selects the best variant per (station, target) from a results.csv produced by
`run_experiments.py`, applies the holdout overfit sanity check, and emits both
`winners.json` (machine-readable) and `report.md` (human-readable summary).

Selection metric: `score = rmse_mean + 0.5 × rmse_std` (lower is better).
Sanity check: `holdout_rmse ≤ 1.3 × rmse_mean`. Violators are skipped in favor
of the next-best valid candidate.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

SCORE_STD_PENALTY = 0.5
HOLDOUT_TOLERANCE = 1.3
SIMPLE_MODEL_SCORE_TOLERANCE = 0.02
ALGO_COMPLEXITY = {
    "ElasticNet": 1,
    "PLSRegression": 1,
    "KNeighbors": 2,
    "SVR": 2,
    "HistGB": 3,
    "GradientBoosting": 3,
    "RandomForest": 4,
    "ExtraTrees": 4,
    "LightGBM": 5,
    "XGBoost": 5,
    "CatBoost": 5,
    "LSTM": 6,
    "GRU": 6,
    "Conv1D": 6,
    "CNN-LSTM": 7,
    "WeightedTop3": 8,
    "StackingTop3": 9,
}


def _score(row: pd.Series) -> float:
    if pd.isna(row["rmse_mean"]) or pd.isna(row["rmse_std"]):
        return float("inf")
    return float(row["rmse_mean"] + SCORE_STD_PENALTY * row["rmse_std"])


def _is_valid(row: pd.Series) -> bool:
    if not row["error"]:
        ok = True
    else:
        return False
    if pd.isna(row["rmse_mean"]):
        return False
    if pd.isna(row["holdout_rmse"]):
        return ok  # accept if holdout couldn't be computed (small dataset edge case)
    return row["holdout_rmse"] <= HOLDOUT_TOLERANCE * row["rmse_mean"]


def _complexity(row: pd.Series) -> int:
    return ALGO_COMPLEXITY.get(str(row.get("algo", "")), 99)


def _choose_winner(valid: pd.DataFrame) -> pd.Series:
    ranked = valid.sort_values("score")
    best_score = float(ranked.iloc[0]["score"])
    tolerance = max(abs(best_score) * SIMPLE_MODEL_SCORE_TOLERANCE, 1e-12)
    near_best = ranked[ranked["score"] <= best_score + tolerance].copy()
    near_best["complexity"] = near_best.apply(_complexity, axis=1)
    return near_best.sort_values(["complexity", "score"]).iloc[0]


def _baseline_score(target_df: pd.DataFrame) -> float | None:
    baselines = target_df[target_df["variant_id"].astype(str).str.contains("#BASELINE", regex=False)]
    baselines = baselines[baselines["valid"]].sort_values("score")
    if baselines.empty:
        return None
    return float(baselines.iloc[0]["score"])


def _parse_json_cell(value: object) -> dict:
    if pd.isna(value):
        return {}
    try:
        parsed = json.loads(str(value))
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def select(results_csv: Path, output_dir: Path) -> tuple[Path, Path]:
    df = pd.read_csv(results_csv)
    if df.empty:
        raise ValueError(f"{results_csv} is empty")

    df["error"] = df["error"].fillna("")
    if "feature_importances" not in df.columns:
        df["feature_importances"] = "{}"
    df["score"] = df.apply(_score, axis=1)
    df["valid"] = df.apply(_is_valid, axis=1)

    winners: dict[str, dict[str, dict]] = {}
    report_lines: list[str] = [
        "# Reporte de experimentos ML",
        "",
        f"Fuente: `{results_csv.name}`",
        f"Filas totales: {len(df)}",
        f"Filas válidas (sanity check OK): {int(df['valid'].sum())}",
        "",
        "Métrica de selección: `score = rmse_mean + 0.5 × rmse_std` (menor es mejor).",
        f"Sanity check anti-overfit: `holdout_rmse ≤ {HOLDOUT_TOLERANCE} × rmse_mean`.",
        "",
    ]

    for station, station_df in df.groupby("station"):
        report_lines.append(f"## Estación `{station}`")
        report_lines.append("")
        report_lines.append("| Target | Algo | Variante | W | Features | RMSE_mean ± std | R² | MAE | Holdout RMSE | Score | Mejora vs baseline |")
        report_lines.append("|---|---|---|---|---|---|---|---|---|---|---|")

        for target, target_df in station_df.groupby("target"):
            valid = target_df[target_df["valid"]].sort_values("score")
            if valid.empty:
                report_lines.append(f"| {target} | — | sin variante válida | — | — | — | — | — | — | — | — |")
                continue
            best = _choose_winner(valid)

            algo = best["algo"]
            variant = best["variant_id"]
            w = int(best["window_size"])
            fv = best["feature_variant"]
            params = _parse_json_cell(best["params"])
            importances = _parse_json_cell(best.get("feature_importances", "{}"))

            score = best["score"]
            baseline = _baseline_score(target_df)
            improvement_pct = None
            improvement_label = "n/d"
            if baseline and baseline > 0:
                improvement_pct = (baseline - float(score)) / baseline * 100.0
                improvement_label = f"{improvement_pct:.1f}%"

            report_lines.append(
                f"| {target} | {algo} | `{variant}` | {w} | {fv} | "
                f"{best['rmse_mean']:.4f} ± {best['rmse_std']:.4f} | "
                f"{best['r2_mean']:.3f} | {best['mae_mean']:.3f} | "
                f"{best['holdout_rmse']:.4f} | {score:.4f} | {improvement_label} |"
            )

            winners.setdefault(station, {})[target] = {
                "algo": algo,
                "variant_id": variant,
                "window_size": w,
                "feature_variant": fv,
                "params": params,
                "rmse_mean": float(best["rmse_mean"]),
                "rmse_std": float(best["rmse_std"]),
                "r2_mean": float(best["r2_mean"]),
                "mae_mean": float(best["mae_mean"]),
                "holdout_rmse": float(best["holdout_rmse"]) if not pd.isna(best["holdout_rmse"]) else None,
                "holdout_r2": float(best["holdout_r2"]) if not pd.isna(best["holdout_r2"]) else None,
                "score": float(score),
                "baseline_score": baseline,
                "improvement_vs_baseline_pct": improvement_pct,
                "feature_importances": importances,
                "n_train_avg": float(best["n_train_avg"]),
                "n_folds": int(best["n_folds"]),
            }

        # Top-3 per target for context
        report_lines.append("")
        report_lines.append("<details><summary>Top 3 candidatos por target</summary>")
        report_lines.append("")
        for target, target_df in station_df.groupby("target"):
            valid = target_df[target_df["valid"]].sort_values("score").head(3)
            if valid.empty:
                continue
            report_lines.append(f"**{target}**")
            report_lines.append("")
            report_lines.append("| # | Algo | Variant | W | Feat | Score | RMSE_mean | RMSE_std | Holdout |")
            report_lines.append("|---|---|---|---|---|---|---|---|---|")
            for i, (_, r) in enumerate(valid.iterrows(), 1):
                report_lines.append(
                    f"| {i} | {r['algo']} | `{r['variant_id']}` | {int(r['window_size'])} | "
                    f"{r['feature_variant']} | {r['score']:.4f} | {r['rmse_mean']:.4f} | "
                    f"{r['rmse_std']:.4f} | {r['holdout_rmse']:.4f} |"
                )
            report_lines.append("")
        report_lines.append("</details>")
        report_lines.append("")

        report_lines.append("<details><summary>Importancias de features en ganadores</summary>")
        report_lines.append("")
        for target, target_winner in winners.get(station, {}).items():
            importances = target_winner.get("feature_importances") or {}
            if not importances:
                continue
            report_lines.append(f"**{target}**")
            report_lines.append("")
            top_features = sorted(importances.items(), key=lambda kv: -float(kv[1]))[:10]
            report_lines.append(", ".join(f"`{name}`:{float(value):.3f}" for name, value in top_features))
            report_lines.append("")
        report_lines.append("</details>")
        report_lines.append("")

    # Aggregate summary across stations
    report_lines.append("## Resumen agregado")
    report_lines.append("")
    if winners:
        algo_counter: dict[str, int] = {}
        feat_counter: dict[str, int] = {}
        window_counter: dict[int, int] = {}
        target_algo_counter: dict[str, dict[str, int]] = {}
        target_window_counter: dict[str, dict[int, int]] = {}
        improvements: list[float] = []
        for st_winners in winners.values():
            for target, w in st_winners.items():
                algo_counter[w["algo"]] = algo_counter.get(w["algo"], 0) + 1
                feat_counter[w["feature_variant"]] = feat_counter.get(w["feature_variant"], 0) + 1
                window_counter[w["window_size"]] = window_counter.get(w["window_size"], 0) + 1
                target_algo_counter.setdefault(target, {})[w["algo"]] = target_algo_counter.setdefault(target, {}).get(w["algo"], 0) + 1
                target_window_counter.setdefault(target, {})[w["window_size"]] = target_window_counter.setdefault(target, {}).get(w["window_size"], 0) + 1
                if w.get("improvement_vs_baseline_pct") is not None:
                    improvements.append(float(w["improvement_vs_baseline_pct"]))

        report_lines.append("**Algoritmos ganadores (frecuencia)**: " + ", ".join(
            f"{a}:{c}" for a, c in sorted(algo_counter.items(), key=lambda kv: -kv[1])
        ))
        report_lines.append("")
        report_lines.append("**Feature variants (frecuencia)**: " + ", ".join(
            f"{f}:{c}" for f, c in sorted(feat_counter.items(), key=lambda kv: -kv[1])
        ))
        report_lines.append("")
        report_lines.append("**Window sizes (frecuencia)**: " + ", ".join(
            f"W={w}:{c}" for w, c in sorted(window_counter.items(), key=lambda kv: -kv[1])
        ))
        report_lines.append("")

        if improvements:
            improved = sum(1 for value in improvements if value > 0)
            report_lines.append(
                f"**Mejora vs baseline**: {improved}/{len(improvements)} targets mejoran "
                f"({improved / len(improvements) * 100:.1f}%), media {np.mean(improvements):.1f}%."
            )
            report_lines.append("")

        report_lines.append("**Mejor algoritmo por target**: " + ", ".join(
            f"{target}:{max(counts.items(), key=lambda kv: kv[1])[0]}"
            for target, counts in sorted(target_algo_counter.items())
        ))
        report_lines.append("")
        report_lines.append("**Mejor ventana por target**: " + ", ".join(
            f"{target}:W={max(counts.items(), key=lambda kv: kv[1])[0]}"
            for target, counts in sorted(target_window_counter.items())
        ))
        report_lines.append("")

    output_dir.mkdir(parents=True, exist_ok=True)
    winners_path = output_dir / "winners.json"
    report_path = output_dir / "report.md"
    winners_path.write_text(json.dumps(winners, indent=2, ensure_ascii=False), encoding="utf-8")
    report_path.write_text("\n".join(report_lines), encoding="utf-8")

    return winners_path, report_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate winners.json + report.md from results.csv.")
    parser.add_argument("--results", type=Path, required=True, help="Path to results.csv")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output dir for winners.json and report.md (default: same dir as results.csv)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    out_dir = args.output_dir or args.results.parent
    winners_path, report_path = select(args.results, out_dir)
    print(f"winners → {winners_path}")
    print(f"report  → {report_path}")


if __name__ == "__main__":
    main()
