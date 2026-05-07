# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**agroTrain2** is a full-stack application implementing a **Software Product Line (SPL)** for configuring virtual digital sensors in olive agriculture. The UVL feature model (`agroTrain.uvl`) is the **single source of truth**: it defines the valid configuration space, drives the wizard UI, validates configurations, maps features to CSV columns, and parameterises ML model training. No domain-specific knowledge is hardcoded in Python or TypeScript — everything is derived at runtime from the UVL tree.

Users configure an olive parcel (irrigation treatment, soil type, location, geometry) and select sensor parameters via a step-by-step wizard. The system then:
1. Validates the configuration against the UVL using Flamapy (BDD satisfiability).
2. Optionally extracts vegetation indices (NDVI, EVI, SAVI, NDWI) from Sentinel-2 via Google Earth Engine.
3. Accepts sensor CSV files, fuses them with telemetry, and trains ML models (LSTM / GradientBoosting) to predict target variables.

The UI is a React + TypeScript wizard with JWT authentication. The backend is Django REST Framework with five apps: `accounts`, `configurador`, `geo`, `telemetria`, `modelos`.

---

## Commands

### Backend

```bash
cd backend

python manage.py runserver        # dev server (SQLite, settings/development.py)
python manage.py migrate
python manage.py makemigrations

pytest                            # all tests
pytest apps/configurador/         # single app
pytest -k test_validate           # single test by name
pytest -v --tb=short

python manage.py shell
```

`DJANGO_SETTINGS_MODULE` defaults to `config.settings.development` (set in `pytest.ini` and docker-compose).

### Frontend

```bash
cd frontend

npm run dev     # dev server on :8080
npm run build   # type-check + build
npm run lint
```

### Docker

```bash
docker compose up           # backend :8000, frontend :8080, postgres :5432
docker compose down -v      # destroy including DB volume
```

---

## The UVL Feature Model (`agroTrain.uvl`)

The UVL file is the core of the system. Every feature node can carry custom attributes:

| Attribute | Used by | Meaning |
|---|---|---|
| `label` | Frontend wizard, constraint messages | Human-readable Spanish name |
| `wizard_step` | Backend + frontend scope derivation | Which wizard step owns this subtree (`parcel`, `sensors`, `telemetry`, `objective`) |
| `csv_col` | Backend training, frontend CSV validation | Single CSV column name this feature maps to |
| `csv_cols` | Backend training, frontend CSV validation | Comma-separated CSV column names (e.g. `'tmax,tmin'`) |
| `window_size` | Backend LSTM/GB training | Lag window in days for this treatment |
| `preferred_algorithm` | Backend training | `'LSTM'` or `'GradientBoosting'` |
| `min_samples` | Backend training | Minimum CSV rows to use LSTM; falls back to GradientBoosting below this |
| `min_reject` | Frontend Results.tsx | Row count below which training is blocked |
| `min_warn` | Frontend Results.tsx | Row count below which a warning is shown |
| `min_good` | Frontend Results.tsx | Row count for "good quality" indicator |
| `quality_min` | Backend training_service | Minimum acceptable R² for this objective variable |
| `quality_good` | Backend training_service | Good R² threshold for this objective variable |

### Adding a new irrigation treatment

Add a child under `Tratamiento` with all treatment attributes, and add the appropriate humidity-depth constraint. No Python or TypeScript changes required.

### Adding a new sensor

Add a child node under `ParametrosEntrada` with `csv_col`. If it needs special calculation from raw data (like Dendrometro), add hardcoded handling in `dendroCalc.ts` and `Results.tsx`. Otherwise it is automatically picked up as a generic upload card in Results.

### Adding a new objective variable

Add a child under `VariableObjetivo`. The feature name **must equal the CSV column name** in the fused training CSV (this is the convention the training service relies on). Add `quality_min` and `quality_good` attributes, and a constraint requiring the corresponding sensor (`NuevoObjetivo => SuSensor`).

### Adding a new telemetry index

Add a child under `DatosTelemetria` with `csv_col`. The frontend automatically derives the list of indices. The backend GEE service must also be updated with the Sentinel-2 band formula (`telemetry_service.py`) — this is the only hardcoded part that can't be moved to the UVL (it's satellite physics, not configuration).

---

## UVL → Wizard UI: How the flow works

### 1. UVL serialisation to JSON

`GET /api/v1/configurator/feature-model` calls `FlamapyService.to_dict()` which serialises the entire feature tree recursively into a JSON structure matching `FeatureModelNode` in `frontend/src/types/api.ts`. Each node contains `name`, `relations` (with `type`: MANDATORY / OPTIONAL / ALTERNATIVE / OR), `attributes` (all UVL attributes), and the top-level `constraints` array with AST representations.

### 2. Feature tree rendering

`frontend/src/components/feature-model/FeatureNode.tsx` receives a `FeatureModelNode` and renders it recursively:
- **ALTERNATIVE** relations → radio group (only one child selectable)
- **OR** relations → checkbox group (one or more)
- **OPTIONAL** relations → individual checkboxes
- **MANDATORY** relations → rendered but not togglable

The component reads `attributes.label` for display names. Selection state lives in `FeatureTreesContext` (`trees[0].features: string[]` — list of active UVL feature names).

### 3. Wizard steps

`DigitalSensorCreation.tsx` controls a four-step unlocking flow:

| Step | Component | Scope | Unlocks after |
|---|---|---|---|
| 0 — Parcela | `ParcelDataCard` | `DatosParcela` subtree | Treatment + soil + province + municipality |
| 1 — Sensores | `StepSensores` | `ParametrosEntrada` subtree | Server validation pass |
| 2 — Telemetría | `StepTelemetria` | `DatosTelemetria` subtree | Server validation pass |
| 3 — Objetivo | `StepObjetivo` | `VariableObjetivo` subtree | Server validation + generate |

On "Listo" the frontend calls `POST /api/v1/configurator/validate-features` with `{ features, is_full: false, step }`. The backend pins in-scope unselected features to False and leaves out-of-scope features free in the BDD, so constraints are only enforced at the appropriate step.

### 4. Inline constraint hints

Each step component computes two sets of violated constraints:

- **intraViolations** (`getViolations`): constraints where ALL features are within the current subtree and the constraint is violated. Blocks the "Listo" button.
- **incomingHints** (`getIncomingRequirements`): IMPLIES constraints where the antecedent is fully active, the constraint is violated, and at least one consequent feature is in the accumulated scope (all steps up to and including current). Shown as amber info boxes via `ConstraintHints`. Blocks "Listo" for current and earlier steps; shown as warning-only in StepObjetivo (server catches them at `is_full: true`).

Both use generic AST evaluation (`evalAST`, `collectASTFeatures`, `formatConstraintAST` in `constraintEvaluator.ts`) — no hardcoded feature names.

The accumulated scope is derived at runtime by `buildAccumulatedScope(model, step)` in `featureModel.ts`, which reads `wizard_step` attributes from the UVL tree.

---

## UVL → Backend Validation: How the flow works

`FlamapyService` (singleton, initialised at startup via `apps.py`) pre-builds the BDD from the UVL once. All subsequent validations reuse it.

### Step-aware BDD validation (`validate_features`)

```
features (selected) ∪ in-scope-unselected → pin False
out-of-scope features → free (BDD can satisfy them freely)
→ BDD satisfiability check
→ if unsatisfiable: generate constraint violation messages from AST evaluation
```

This means: a constraint between parcel and telemetry (e.g. `LomasCalizasAlbariza => SAVI & NDWI`) is NOT checked at the parcel step (SAVI/NDWI are out of scope), but IS checked at the telemetry step (both sides now in scope, SAVI/NDWI pinned False if unselected).

### Constraint violation messages

`_get_violated_constraint_messages` evaluates each IMPLIES constraint generically:
- Checks if antecedent feature is selected
- Checks if consequent is not satisfied
- Formats the message using `_format_ast` which recursively converts the AST to Spanish using `get_label(feature_name)` — labels read from UVL `label` attributes at startup.

No domain-specific strings in the validation code.

### Scope derivation (`_derive_partial_scope_features`)

At startup, traverses the UVL tree looking for `wizard_step` attributes. When found, collects all feature names in that subtree and assigns them to the step. Features without a `wizard_step` ancestor (e.g. root `Entrada`) go to the first step. This mirrors `buildAccumulatedScope` on the frontend.

---

## UVL → ML Training: How the flow works

### 1. Feature selection to training parameters

`POST /api/v1/modelos/train` calls `_features_to_training_params(features)`:

```python
target_names = FlamapyService.get_subtree_feature_names("VariableObjetivo")
treatment_names = FlamapyService.get_subtree_feature_names("Tratamiento")

targets    = [f for f in features if f in target_names]
# Convention: target feature name == CSV column name (e.g. TasaBuenos → column 'TasaBuenos')

input_cols = []
for feature in features:
    if feature not in targets and feature not in treatment_names:
        input_cols += FlamapyService.get_csv_columns(feature)
# get_csv_columns reads csv_col / csv_cols UVL attributes

treatment = first feature in features that is in treatment_names
```

### 2. Algorithm selection (from UVL treatment attributes)

`FlamapyService.get_treatment_profile(treatment_name)` reads `window_size`, `preferred_algorithm`, `min_samples` from the UVL treatment feature node's attributes. No hardcoded profile file exists — this comes from UVL attributes.

### 3. Quality thresholds (from UVL objective attributes)

`FlamapyService.get_quality_thresholds(target_name)` reads `quality_min` and `quality_good` from the UVL objective feature node. If attributes are absent, no quality warning is generated (graceful degradation).

### 4. Algorithm selection logic

Fallback chain in `training_service.py`:

```
preferred = UVL treatment attribute preferred_algorithm
if preferred == "LSTM":
    if TensorFlow not installed  →  GradientBoosting + warning
    elif n_joint < min_samples   →  GradientBoosting + warning
    else                         →  LSTM
else                             →  GradientBoosting
```

`n_joint` = complete rows where ALL of `targets + input_features` are non-null. Default fallbacks when UVL attributes absent: `window_size=5`, `preferred_algorithm='GradientBoosting'`, `min_samples=80`.

### 5. Training algorithms

**LSTM** (TensorFlow):
- Drops rows with any missing value in `all_cols`
- 80/20 train/val split
- Autoregressive: X windows cover `all_cols` (targets serve as lag inputs too), Y = current target value
- Separate scalers: `scaler_X` for feature windows, `scaler_Y[target]` for each target — both fitted on train partition only
- Architecture per target: 128-unit LSTM → Dropout(0.2) → Dense(64, relu) → Dense(1)
- Optimizer: Adam(lr=0.001), Loss: Huber, 200 epochs max, EarlyStopping(patience=30, min_delta=1e-4)
- Progress updates pushed to `_registry` via `_ProgressCallback` for frontend polling

**GradientBoosting** (`HistGradientBoostingRegressor`, params: `max_depth=5, learning_rate=0.05, max_iter=300, early_stopping=True`):
- Temporal features added via `_add_temporal_features`:
  - Day-of-year: `sin(2π·DOY/365)` and `cos(2π·DOY/365)`
  - Lag features: `{feat}_lag1` … `{feat}_lag{window_size}` for every column
  - Rolling mean: `{feat}_roll7d` (7-day, capped at `window_size`)
- Features added before 80/20 split; per-target `scaler_{target}.pkl` fitted on train only
- One model per target

**RandomForest** (`RandomForestRegressor`, params: `n_estimators=300, max_features='sqrt', min_samples_split=4, min_samples_leaf=2`): code path exists but no UVL treatment currently uses it.

### 6. Storage structure

Files saved under `backend/model_storage/{model_id}/`:

| File | Algorithm | Purpose |
|---|---|---|
| `metadata.json` | Both | targets, input_features, features, geo, window_size, algorithm, metrics, warnings, n_samples, n_train, n_val, feature_columns_by_target, created_at |
| `lstm_{target}.keras` | LSTM | TF saved model per target |
| `scaler_X.pkl` | LSTM | MinMaxScaler for all feature windows |
| `scaler_{target}.pkl` | Both | MinMaxScaler for target output |
| `model_{target}.pkl` | Sklearn | HistGB/RF model per target |

DB models: `ModeloGuardado` (full metadata + user FK) and `PrediccionModelo` (FK to model, per-inference predictions JSON + warnings).

---

## UVL → Value Generation (Inference): How the flow works

After a model is trained, users generate predictions in `frontend/src/pages/GenerarValorModelo.tsx`. The backend exposes two new endpoints.

### 1. Inference endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/modelos/<id>/predict` | Single inference on fused CSV → 201 with predictions dict |
| GET | `/api/v1/modelos/<id>/predictions` | List all past predictions for a model |

`POST /predict` request: multipart `csv_file` (fused sensor + telemetry, `;`-separated with BOM).
Response: `{ prediction_id, model_id, generated_at, predicted_for_date, predictions: {target: value}, input_row_count, warnings }`.

Validation guards: model must have `geo.punto` saved (required to know location context); CSV must contain all columns from `metadata.json`; CSV must have ≥ `window_size` complete rows.

### 2. Backend inference logic (`prediction_service.py`)

**LSTM** (`_predict_lstm`):
1. Load `lstm_{target}.keras` and scalers from disk
2. Take last `window_size` rows of all columns, scale with `scaler_X`
3. Reshape to `(1, window_size, n_features)` → `model.predict()` → inverse-scale with `scaler_Y[target]`

**Sklearn** (`_predict_sklearn`):
1. Load `model_{target}.pkl` and `scaler_{target}.pkl`
2. Reconstruct feature set per target using `feature_columns_by_target` from metadata
3. Add temporal features (same `_add_temporal_features` as training) on a synthetic "future row" built from last observed values
4. `model.predict(X_scaled)` → inverse-scale

**One-step-ahead only**: no recursive prediction. Environmental inputs use last observed value; target lags come from real historical window via `shift()`. Avoids error accumulation.

### 3. Frontend inference flow (`GenerarValorModelo.tsx`)

Prerequisites: model must have `geo.punto` (validated on page load).

| Step | Action | Details |
|---|---|---|
| 1 — Historical data | Upload sensor files | Dendrómetro → `calculateDendroParams`; generic sensors; temperature |
| 2 — Telemetry | "Extraer telemetría" | Calls `POST /api/v1/telemetry/extract` with saved `geo.punto`; date range auto-derived from sensor files |
| 3 — Fusion | "Fusionar datos" | `mergeSensorFiles()` → `fuseSensorAndTelemetry()`; validates `rowCount ≥ window_size` |
| 4 — Predict | "Generar valor" | Converts FusionResult to CSV (BOM+`;`) → `POST /predict` → displays per-target values |
| 5 — History | Auto-loaded | `GET /predictions` → last 5 predictions shown |

---

## UVL → Frontend Results: How the flow works

`Results.tsx` derives everything from the feature model query and the active feature list:

- **`buildCsvColumnInfo(model, "DatosTelemetria")`** → aliases + dataColumns for telemetry CSV parsing. NDVI/EVI/SAVI/NDWI derived automatically; adding a new index to UVL picks it up with no code change.
- **`collectCsvFeatures(model, features, HARDCODED_SENSOR_IDS)`** → list of `{featureName, csvCol, label}` for all active sensors in `ParametrosEntrada` that aren't hardcoded (humedad depths, pluviómetro, future sensors). Renders a `SensorFileCard` upload for each automatically.
- **`buildTreatmentTrainingThresholds(model)`** → `min_reject / min_warn / min_good` per treatment from UVL attributes. Controls the training data quality indicator.
- **`buildAccumulatedScope` / `buildLabelMap`** → used in step components for constraint hints.

### Hardcoded sensor handling (legitimately, by design)

- **Dendrómetro**: raw dendrometer data → `dendroCalc.ts` computes MCD, TasaBuenos, TasaSeveros from trunk diameter variation. Domain-specific calculation that cannot be expressed in UVL.
- **TemperaturaAire**: single file → split into `tmin`/`tmax` via min/max aggregation in the sensor merger.
- **GEE band formulas** (`telemetry_service.py`): NDVI = (B8−B4)/(B8+B4), etc. Sentinel-2 satellite physics — cannot be configuration.

---

## What is and is not hardcoded (SPL invariant)

### Legitimately hardcoded (not moveable to UVL)

| Location | What | Why |
|---|---|---|
| `telemetry_service.py:183-199` | GEE band formulas per index | Sentinel-2 physics |
| `dendroCalc.ts` | MCD / TasaBuenos / TasaSeveros calculation | Domain calculation logic |
| `Results.tsx` | Dendrómetro + TemperaturaAire upload sections | Special aggregation logic |
| `flamapy_service.py` | `PARTIAL_STEP_ORDER` tuple | UI ordering, not derivable from UVL alone |
| `serializers.py` | `PARTIAL_STEP_CHOICES` | Validation of the same step order |
| `defaultConfig.ts` | `cloudThreshold: 20` | Trivial UI default |

### Everything else is UVL-driven

Treatment names, soil names, sensor names, objective variables, telemetry indices, CSV column mappings, algorithm parameters, quality thresholds, training data thresholds, constraint messages, wizard scope, constraint hints — all derived at runtime from `agroTrain.uvl`.

---

## Architecture

### Backend (`backend/`)

```
config/
  settings/base.py       # UVL_MODEL_PATH = backend/agroTrain.uvl
                         # MODELS_STORAGE_PATH = backend/model_storage/
                         # AUTH_USER_MODEL = accounts.CustomUser
                         # JWT access token lifetime = 15 min
  settings/development.py
  settings/docker.py
  settings/production.py
  urls.py                # /api/v1/{auth,configurator,geo,telemetry,modelos}/
                         # /schema/ OpenAPI, /docs/ Swagger UI
apps/
  accounts/              # CustomUser, JWT auth, user management, admin permissions
  configurador/          # Flamapy BDD validation + feature model serialisation
  geo/                   # Province/municipality catalog (hardcoded) + Shapely geometry
  telemetria/            # GEE Sentinel-2 extraction
  modelos/               # Async ML training (LSTM / GradientBoosting / RandomForest)
```

**configurador / FlamapyService** — class with class-level BDD cache. Initialised at startup via `apps.py:ready()`. Key methods:
- `warm_up(path)` — builds BDD, collects labels, derives step scopes, all from UVL
- `validate_features(features, is_full, step)` — step-aware BDD validation
- `get_subtree_feature_names(parent)` — all feature names under a node
- `get_csv_columns(feature)` — csv_col/csv_cols for a feature
- `get_treatment_profile(treatment)` — window_size, preferred_algorithm, min_samples from UVL
- `get_quality_thresholds(target)` — quality_min, quality_good from UVL
- `to_dict()` — full feature tree serialised to JSON with constraints

**modelos / training flow**: `start_training` spawns daemon thread → `_run_pipeline` → reads treatment profile from UVL → loads CSV → selects algorithm (LSTM / GradientBoosting) → trains per-target model → saves via `StorageService`. Status polled via in-memory `_registry`. Models stored as UUID-named dirs under `backend/model_storage/` with `metadata.json` + `.pkl` / `.keras` artifacts.

**modelos / inference flow**: `prediction_service.py` loads artifacts from disk → reconstructs feature set from `metadata.json` → runs one-step-ahead inference → saves `PrediccionModelo` DB record → returns predictions dict.

### Frontend (`frontend/src/`)

```
App.tsx                           # Router + QueryClient + GeoProvider + FeatureTreesProvider
                                  # Protected routes via RequireAuth / RequireAdmin
contexts/
  AuthContext.tsx                 # JWT login state (access token, user role)
  FeatureTreesContext.tsx         # trees[0].features: string[] — active UVL feature names
lib/geoContext.tsx                # Parcel/geo state (GeoProvider)
pages/
  Landing.tsx                     # Home page
  Login.tsx                       # JWT login form
  DigitalSensorCreation.tsx       # 4-step wizard
  Results.tsx                     # Sensor upload, telemetry, fusion, training
  MisModelos.tsx                  # List of user's saved models
  GenerarValorModelo.tsx          # Inference page: upload sensors → extract GEE → fuse → predict
  UserManagement.tsx              # Admin: user CRUD
  Architecture.tsx                # Feature model visualisation
  NotFound.tsx                    # 404
components/
  RequireAuth.tsx                 # Protected route wrapper
  RequireAdmin.tsx                # Admin-only route wrapper
  feature-model/FeatureNode.tsx   # Recursive UVL tree renderer
  steps/ConstraintHints.tsx       # Amber inline constraint violation hints
  steps/StepSensores.tsx          # Step 2 with intra + incoming constraint hints
  steps/StepTelemetria.tsx        # Step 3 with intra + incoming constraint hints
  steps/StepObjetivo.tsx          # Step 4 with incoming constraint warnings
  steps/SectionTitle.tsx          # UI heading helper
  config/ParcelDataCard.tsx       # Step 1 (parcela + geo selects)
  config/ParcelMap.tsx            # Leaflet + Geoman polygon drawing
  config/SensorFileCard.tsx       # CSV upload + preview card
  results/CsvUploadSection.tsx    # Dataset upload section in Results
  results/TelemetryPreview.tsx    # NDVI/EVI chart preview in Results
  ui/                             # Shadcn/Radix components (button, input, checkbox, …)
hooks/
  useConfiguraciones.ts           # Configurator API bindings
  useConfiguratorApi.ts           # Feature model API service layer
  useFeatureTrees.ts              # Feature model state
  useGeo.ts                       # Geographic data
  useModelos.ts                   # User's models list
  useModelosApi.ts                # Modelos API bindings
services/
  api.ts                          # Base axios instance (JWT header injection)
  configuratorApi.ts              # Configurador endpoints
  modelosApi.ts                   # Modelos endpoints
utils/
  featureModel.ts                 # buildLabelMap, buildAccumulatedScope, collectCsvFeatures,
                                  # buildCsvColumnInfo, buildTreatmentTrainingThresholds
  constraintEvaluator.ts          # evalAST, getViolations, getIncomingRequirements,
                                  # formatConstraintAST, collectASTFeatures
lib/
  csvDataset.ts                   # parseCsvFile(file, kind, aliases, dataColumns, required)
  dendroCalc.ts                   # MCD / TasaBuenos / TasaSeveros from raw dendrometer data
  dataFusion.ts                   # fuseSensorAndTelemetry
  sensorMerger.ts                 # mergeSensorFiles (daily aggregation)
  defaultConfig.ts                # cloudThreshold: 20 (trivial UI default)
  utils.ts                        # General utilities
types/
  api.ts                          # API response DTOs (FeatureModelNode, etc.)
  config.ts                       # Configuration types
```

### API routes

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/auth/login/` | JWT login → access + refresh tokens |
| POST | `/api/v1/auth/token/refresh/` | Refresh access token |
| GET/POST | `/api/v1/auth/users/` | List / create users (admin) |
| GET/PUT/DELETE | `/api/v1/auth/users/<id>/` | User detail / edit / delete (admin) |
| GET | `/api/v1/configurator/feature-model` | Full UVL tree as JSON |
| POST | `/api/v1/configurator/validate-features` | Step-aware BDD validation |
| GET | `/api/v1/geo/provinces` | Province list |
| GET | `/api/v1/geo/municipalities/<id>` | Municipalities for province |
| POST | `/api/v1/telemetry/extract` | GEE Sentinel-2 extraction |
| POST | `/api/v1/modelos/train` | Start async training (multipart: features JSON + csv_file) |
| GET | `/api/v1/modelos/<id>/status` | Poll training status |
| GET | `/api/v1/modelos/` | List saved models |
| GET/DELETE | `/api/v1/modelos/<id>/` | Model detail / delete |
| GET | `/api/v1/modelos/<id>/download` | Export model as ZIP |
| POST | `/api/v1/modelos/import` | Import model ZIP |
| POST | `/api/v1/modelos/<id>/predict` | One-step-ahead inference (multipart: csv_file) → predictions dict |
| GET | `/api/v1/modelos/<id>/predictions` | List all past predictions for a model |
| GET | `/schema/` | OpenAPI schema |
| GET | `/docs/` | Swagger UI |

Dev: backend `http://localhost:8000`, frontend `http://localhost:8080`. Frontend reads `VITE_BACKEND_URL` from `.env` (root level).

---

## Environment Setup

**Backend** (`backend/.env`):
- `DJANGO_SECRET_KEY` — required in all environments
- `EE_SERVICE_ACCOUNT`, `EE_PRIVATE_KEY_FILE`, `EE_PROJECT` — GEE credentials (telemetry fails without them)
- Production: `POSTGRES_*`, `DJANGO_ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`

**Frontend** (`.env` at repo root — read by Vite via root `docker-compose.yml`):
- `VITE_BACKEND_URL=http://localhost:8000`

**Docker** uses `settings/docker.py` (separate from `development.py`). GEE key file (`eeproject-*.json`) lives at repo root; path referenced in docker-compose env vars.

---

## Dependencies

```bash
pip install -r backend/requirements/development.txt
```

Flamapy requires Python < 3.13 (PySAT does not support 3.13+). TensorFlow is optional — if absent, all treatments fall back to GradientBoosting regardless of UVL `preferred_algorithm`.

---

## Tests

No test files exist yet. Place at `backend/apps/<app>/tests/test_*.py`. Use `factory-boy`. Integration tests must hit the real SQLite DB — do not mock the database layer.
