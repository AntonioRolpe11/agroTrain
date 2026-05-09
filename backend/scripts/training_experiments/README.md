# Training Experiments

Offline harness to search optimal ML hyperparameters per station for the agroTrain2 olive sensor models. This is an experimental workflow only; it does not modify Sensolive or production training code.

## Layout

```
training_experiments/
├── data_prep.py          # Load 24 sensors per station, normalize, aggregate daily
├── dendro_calc.py        # Python port of frontend/src/lib/dendroCalc.ts (MCD/TB/TS)
├── features.py           # Feature engineering variants
├── run_experiments.py    # Cross-station × target × variant runner with TimeSeriesSplit(5) + 15% holdout
├── select_winners.py     # Pick best per (station, target), emit winners.json + report.md
├── tests/                # Unit tests (dendro_calc parity, naming normalization)
└── results/              # Experiment outputs (gitignored)
```

## CSV source

Reads from `<repo_root>/csvs/`. Stations are detected by filename prefix; the 6 known prefixes (`Control_59_3-3_O`, `Control_60_4-3_O`, `RDC_49_5-1_O`, `RDC_62_6-3_O`, `Secano_46_2-1_O`, `Secano_53_3-2_O`) are normalized for orthographic variants (`Tª_↔Ta_`, `Pluviómetro/Pluvómetro/PLuviómetro` → `Pluviometro`).

**One model per station** — files from different stations are never combined.

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

# Generate winners + report
python -m backend.scripts.training_experiments.select_winners --results results/<timestamp>/results.csv

# Debug one station/target
python -m backend.scripts.training_experiments.run_experiments --station RDC_62_6-3_O --target MCD --quick

# Tests
pytest backend/scripts/training_experiments/tests/
```

Outputs:

- `results.csv`: every candidate with CV, holdout and optional feature importances.
- `winners.json`: best accepted candidate per `(station, target)`.
- `report.md`: ranking, improvement vs baseline, top candidates and aggregate summaries.

## Producción → ganadores

Tras revisar `report.md`, aplicar manualmente a:

- `_build_gb()` y `_build_rf()` en `backend/apps/modelos/services/training_service.py`
- LSTM arch en `_train_lstm` (líneas ~226-235)
- `_add_temporal_features` (línea ~441) si gana variante distinta de `basic`
- Atributos `window_size` / `preferred_algorithm` en UVL activa (`backend/uvl_versions/`)
