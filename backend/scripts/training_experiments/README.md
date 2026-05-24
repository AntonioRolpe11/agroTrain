# Training Experiments

Offline harness to search optimal ML hyperparameters per station for the agroTrain2 olive sensor models. This is an experimental workflow only; it does not modify Sensolive or production training code.

## Layout

```
training_experiments/
├── data_prep.py          # Load 24 sensors per station, normalize, aggregate daily
├── dendro_calc.py        # Python port of frontend/src/lib/dendroCalc.ts (MCD/TB/TS)
├── features.py           # Feature engineering variants
├── make_training_csvs.py # Consolida los 3 CSV entrenamiento_{tratamiento}.csv (dendro+humedad+temp+dpv)
├── treatment_data.py     # Carga esos CSV y los divide por estación (fuente --from-training-csvs)
├── run_experiments.py    # Cross-station × target × variant runner with TimeSeriesSplit(5) + 15% holdout
├── select_winners.py     # Pick best per (station, target), emit winners.json + report.md
├── treatment_winners.py  # Pick best per (treatment, target) sin pooling, emit snippets UVL/hyperprofiles
├── tests/                # Unit tests (dendro_calc parity, naming normalization)
└── results/              # Experiment outputs (gitignored)
```

## CSV source

Dos fuentes de datos, seleccionables por flag:

- **Por defecto** (`csvs/` crudo): reconstruye cada estación desde sus 24 CSV sueltos. Las 6 prefijos
  (`Control_59_3-3_O`, `Control_60_4-3_O`, `RDC_49_5-1_O`, `RDC_62_6-3_O`, `Secano_46_2-1_O`,
  `Secano_53_3-2_O`) se normalizan ortográficamente (`Tª_↔Ta_`, `Pluviómetro/…` → `Pluviometro`).
- **`--from-training-csvs`**: lee `csvs/entrenamiento_{tratamiento}.csv` (generados por
  `make_training_csvs.py`) y los **divide por la columna `station`** → una serie por parcela.

**One model per station** — files from different stations are never combined (tampoco con `--from-training-csvs`: las parcelas de un mismo tratamiento nunca se concatenan en el entrenamiento).

## Targets

Three targets per station: `MCD`, `TasaBuenos`, `TasaSeveros`. Computed from sub-daily dendrometry via `dendro_calc.py`.

## Feature variants

- `basic`: production-like lags and rolling means.
- `long_lags`, `multi_roll`, `ema`, `full`: extended temporal memory.
- `calendar`: day/month/week/agronomic season signals.
- `irrigation_memory`: accumulated rain/irrigation memory over 3/7/14/30 days.
- `soil_profile`: depth means, shallow/deep gaps and gradients.
- `stress_indices`: DPV/temperature/water interaction proxies.
- `robust_smoothing`: shifted rolling medians and day-to-day differences.
- `target_only`: autoregressive target history only, for measuring external sensor value.

All lag/rolling/EMA/difference features use `shift(1)` so they do not read the current or future target value.

## Algorithms

- Baselines: `HistGB`, `RandomForest`, `LSTM`.
- Tabular search: `ExtraTrees`, `GradientBoosting`, `KNeighbors`, `SVR`, `ElasticNet`, `PLSRegression`.
- Optional boosters with `--include-optional-boosters`: `LightGBM`, `XGBoost`, `CatBoost` if installed.
- Sequential TensorFlow search: `LSTM`, `GRU`, `Conv1D`, `CNN-LSTM`.
- Final tabular ensembles: weighted top-3 and simple ridge stacking when enabled.

## Metrics

- **Primary**: `score = rmse_mean + 0.5 × rmse_std` over 5-fold `TimeSeriesSplit`.
- **Secondary**: R², MAE, holdout RMSE/R² (last 15% of each station never seen during CV).
- **Sanity check**: discard winners where `holdout_rmse > 1.3 × rmse_mean` (overfit guard).
- **Tie break**: when a simpler model is within 2% of the best score, prefer the simpler candidate.

## Telemetry caveat

GEE indices (NDVI/EVI/SAVI/NDWI) are NOT available offline (require Earth Engine API + parcel polygon). Experiments use sensor data only. Winners are validated against a real fused CSV before applying to production.

## Usage

```bash
# Smoke test one station, one target, no neural/ensemble step
python -m backend.scripts.training_experiments.run_experiments --quick --station Control_59_3-3_O

# Normal run (all stations/targets, moderate random search)
python -m backend.scripts.training_experiments.run_experiments --all --skip-lstm

# Full nightly run (background recommended, several hours)
python -m backend.scripts.training_experiments.run_experiments --overnight --include-optional-boosters

# Máxima calidad sobre los 3 CSV de entrenamiento (overnight + boosters + secuenciales + ensembles)
python -m backend.scripts.training_experiments.run_experiments --max --from-training-csvs

# Generate winners + report (diagnóstico por parcela)
python -m backend.scripts.training_experiments.select_winners --results results/<timestamp>/results.csv

# Ganador por tratamiento + snippets UVL/hyperprofiles (salida principal)
python -m backend.scripts.training_experiments.treatment_winners --results results/<timestamp>/results.csv

# Debug one station/target
python -m backend.scripts.training_experiments.run_experiments --station RDC_62_6-3_O --target MCD --quick

# Tests
pytest backend/scripts/training_experiments/tests/
```

`--max` = `--overnight` + `--include-optional-boosters` + secuenciales (sin `--skip-lstm`) + ensembles.
`--from-training-csvs` cambia la fuente de datos a los CSV consolidados por tratamiento.

Outputs:

- `results.csv`: every candidate with CV, holdout and optional feature importances.
- `winners.json` / `report.md`: best accepted candidate per `(station, target)` (diagnóstico por parcela).
- `treatment_winners.json` / `treatment_report.md`: **un ganador por `(tratamiento, target)`** (re-evaluado en
  ambas parcelas por separado, sin pooling), con score combinado y mejora vs baseline.
- `uvl_snippets.md`: atributos por tratamiento listos para pegar en el UVL activo.
- `hyperprofiles_v2.py`: entradas para `HYPERPROFILE_REGISTRY`.

## Producción → ganadores

`treatment_winners.py` ya restringe el ganador a algoritmos expresables como hyperprofile per-target
(RandomForest, GradientBoosting/HistGB, XGBoost, LightGBM, SVR, PLSRegression, ElasticNet) y genera los
snippets. Para aplicarlos:

1. Pegar los atributos de `uvl_snippets.md` en los nodos de `Tratamiento` de
   `backend/uvl_versions/v2_olivos_tratamientos.uvl` (`pref_alg_<target>`, `window_<target>`,
   `feat_variant_<target>`, `hyperprofile_<target>`).
2. Añadir las entradas de `hyperprofiles_v2.py` a `HYPERPROFILE_REGISTRY` en
   `backend/apps/modelos/services/hyperprofile_registry.py`.
3. Activar la versión UVL editada desde `UvlEditor.tsx`.

Nota: para RandomForest y GradientBoosting/HistGB producción usa hiperparámetros fijos
(`_build_rf`/`_build_gb`) e ignora los `params` del hyperprofile; XGBoost/LightGBM/SVR/PLSRegression/
ElasticNet sí los respetan. El `treatment_report.md` indica además el mejor offline **sin** restricción
(p. ej. una red), por si compensa soportarlo en producción.
