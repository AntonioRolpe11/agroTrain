# Generación de modelos predictivos y generación de valores en agroTrain2

## 1. Introducción

El módulo de modelos de **agroTrain2** constituye la parte predictiva del sistema. Su objetivo es transformar una configuración agronómica definida por el usuario, junto con datos históricos de sensores y telemetría, en un **sensor digital predictivo** capaz de estimar una o varias variables objetivo. Posteriormente, ese modelo entrenado puede reutilizarse para generar nuevos valores a partir de datos históricos recientes.

Desde el punto de vista de la memoria del TFG, este módulo es relevante porque integra tres ideas principales:

1. **Configuración dirigida por una línea de producto software (SPL)**: las variables disponibles, sensores, Tratamientos, restricciones y parámetros de entrenamiento no se definen de forma aislada en el código, sino que se derivan del modelo de características UVL.
2. **Entrenamiento automático de modelos de aprendizaje automático**: el sistema decide cómo construir el conjunto de entrenamiento y qué algoritmo aplicar en función de la configuración seleccionada y de la cantidad de datos disponible.
3. **Reutilización operacional del modelo**: una vez entrenado, el modelo queda persistido, se muestra en la pantalla “Mis modelos” y puede utilizarse para generar valores futuros de la variable objetivo.

El flujo completo puede resumirse así:

```text
Configuración UVL
      ↓
Selección de Tratamiento, sensores, telemetría y variable objetivo
      ↓
Carga y fusión de CSV de sensores + datos GEE
      ↓
Entrenamiento del modelo predictivo
      ↓
Persistencia en disco y base de datos
      ↓
Reutilización desde “Mis modelos”
      ↓
Generación de un valor de la variable objetivo
```

Este documento describe en profundidad tanto la **generación de modelos** como la **generación de valores**, explicando las decisiones de diseño, los endpoints utilizados, la preparación de los datos, los algoritmos de aprendizaje y la persistencia de resultados.

---

## 2. Papel del modelo UVL en la generación predictiva

agroTrain2 se apoya en un modelo de características UVL como fuente de verdad de la configuración. Esto significa que la lógica del módulo de modelos no parte de listas fijas de sensores o variables objetivo, sino de los atributos declarados en el modelo de características.

En términos prácticos, cuando el usuario finaliza el configurador, el frontend dispone de una lista de *features* activas. Esa lista contiene información como:

- Tratamiento seleccionado;
- tipo de suelo;
- sensores de entrada;
- índices de telemetría;
- variable objetivo;
- restricciones satisfechas durante el wizard.

El backend recibe esas *features* y las transforma en parámetros de entrenamiento mediante la función `_features_to_training_params`, definida en `backend/apps/modelos/views.py`.

```python
def _features_to_training_params(features: list[str]) -> tuple[list[str], list[str], str]:
    features_set = set(features)
    target_names = set(FlamapyService.get_subtree_feature_names("VariableObjetivo"))
    treatment_names = set(FlamapyService.get_subtree_feature_names("Tratamiento")) - {"Tratamiento"}

    targets = [f for f in features_set if f in target_names]

    seen: set[str] = set()
    input_cols: list[str] = []
    for feature_name in features_set:
        if feature_name in target_names or feature_name in treatment_names:
            continue
        for col in FlamapyService.get_csv_columns(feature_name):
            if col not in seen:
                seen.add(col)
                input_cols.append(col)

    treatment = next((f for f in features_set if f in treatment_names), "")
    return targets, input_cols, treatment
```

La función realiza tres operaciones fundamentales:

1. Obtiene las variables objetivo desde el subárbol `VariableObjetivo`.
2. Obtiene el Tratamiento desde el subárbol `Tratamiento`.
3. Convierte las *features* de entrada en columnas reales de CSV usando los atributos `csv_col` y `csv_cols` del UVL.

Esta decisión reduce el acoplamiento entre el código y el dominio agrícola. Por ejemplo, si en el futuro se añade un nuevo sensor al UVL con su atributo `csv_col`, el backend puede incorporarlo al entrenamiento sin modificar manualmente una lista de columnas en Python.

---

## 3. Generación del modelo predictivo

### 3.1. Preparación de datos en el frontend

La generación de modelos comienza en la página de validación y resultados del frontend (`frontend/src/pages/Results.tsx`). El usuario carga los CSV correspondientes a los sensores seleccionados y, si la configuración incluye índices de telemetría, puede extraerlos desde Google Earth Engine.

El frontend trabaja con tres tipos de datos:

| Tipo de dato | Origen | Ejemplos |
|---|---|---|
| Sensores de parcela | CSV cargados por el usuario | humedad, temperatura, dendrómetro |
| Telemetría satelital | Google Earth Engine o CSV | NDVI, EVI, SAVI, NDWI |
| Variable objetivo histórica | CSV de sensores o cálculo derivado | MCD, TasaBuenos, TasaSeveros |

Antes de entrenar, estos datos se fusionan en una única tabla temporal. El resultado es un CSV con una columna `date` y las columnas necesarias para el modelo:

```text
date;MCD;TasaBuenos;humedad_Hd35;tmin;tmax;NDVI
2025-04-01;0.41;0.78;18.4;10.2;24.6;0.64
2025-04-02;0.43;0.81;18.1;11.0;25.1;0.65
...
```

Cuando el usuario pulsa “Generar sensor”, el frontend convierte el resultado de la fusión en un `Blob` CSV y lo envía al backend:

```typescript
const csvContent = fusionResultToCsv(fusionResult, ";");
const csvBlob = new Blob(["\uFEFF" + csvContent], {
  type: "text/csv;charset=utf-8;",
});

const result = await trainMutation.mutateAsync({
  features,
  csvBlob,
  geo,
});
```

La inclusión de `geo` es importante porque el modelo guardado conserva la ubicación de la parcela. Esa ubicación se reutiliza posteriormente al generar valores, ya que permite extraer de nuevo la telemetría necesaria para el mismo emplazamiento.

### 3.2. Endpoint de entrenamiento

El entrenamiento se inicia mediante:

```http
POST /api/v1/modelos/train
```

La petición se envía como `multipart/form-data` e incluye:

| Campo | Descripción |
|---|---|
| `features` | Array JSON con las *features* UVL seleccionadas |
| `geo` | Objeto JSON con la información de parcela y ubicación |
| `csv_file` | CSV fusionado con sensores, telemetría y variable objetivo |

La vista `train_model` valida la entrada, deriva los parámetros del entrenamiento y delega en `TrainingService`:

```python
targets, input_cols, treatment = _features_to_training_params(features)

model_id = _training_service.start_training(
    targets,
    input_cols,
    treatment,
    csv_content,
    features=features,
    geo=geo,
    user_id=request.user.pk,
)
```

El endpoint responde inmediatamente con estado `202 Accepted`:

```json
{
  "model_id": "1a2b3c4d-0000-0000-0000-000000000000",
  "status": "training"
}
```

El entrenamiento no se ejecuta de forma bloqueante dentro de la propia petición HTTP. En su lugar, se lanza en un hilo en segundo plano. Esto evita que el navegador quede esperando durante varios minutos y permite consultar el progreso mediante otro endpoint.

### 3.3. Registro de progreso

El servicio mantiene un registro en memoria con el estado del entrenamiento:

```python
_registry[model_id] = {
    "status": "training",
    "phase": "iniciando",
    "current_epoch": None,
    "total_epochs": None,
    "current_target": None,
    "val_loss": None,
}
```

La consulta del estado se realiza mediante:

```http
GET /api/v1/modelos/{model_id}/status
```

Durante el entrenamiento, el frontend muestra:

- fase actual;
- algoritmo usado;
- variable objetivo entrenada;
- época actual y total de épocas, cuando el algoritmo es LSTM;
- valor de `val_loss`;
- número de muestras de entrenamiento y validación;
- métricas finales si el entrenamiento ha terminado.

Esta separación entre inicio del entrenamiento y consulta del estado mejora la experiencia de usuario y permite representar procesos largos sin bloquear la interfaz.

---

## 4. Selección del algoritmo de entrenamiento

agroTrain2 implementa **dos rutas de entrenamiento** que coexisten en `training_service.py`. La ruta activa se determina en función de si el UVL incluye atributos `hyperprofile_<target>` en el nodo de tratamiento.

### 4.1. Ruta hyperprofile (activa en el modelo v2)

El modelo UVL de referencia inspeccionado en el repositorio define para cada par *tratamiento × variable objetivo* un perfil de hiperparámetros identificado por una clave estable. En ejecución, el backend toma estos atributos de la versión UVL activa registrada en base de datos:

```uvl
RiegoControl {
    window_size 7, min_samples 730,
    hyperprofile_MCD 'secano_mcd_pls_v1',
    pref_alg_MCD 'PLSRegression', window_MCD 3, feat_variant_MCD 'stress_indices',
    hyperprofile_TasaBuenos 'control_tasabuenos_svr_v1',
    pref_alg_TasaBuenos 'SVR', window_TasaBuenos 28, feat_variant_TasaBuenos 'target_only',
    hyperprofile_TasaSeveros 'control_tasaseveros_lgbm_v1',
    pref_alg_TasaSeveros 'LightGBM', window_TasaSeveros 3, feat_variant_TasaSeveros 'soil_profile'
}
```

`FlamapyService.get_treatment_target_profile(treatment, target)` lee estos atributos y devuelve el perfil completo. Si algún target tiene `hyperprofile`, el pipeline usa `_train_per_target`, que entrena cada variable objetivo de forma independiente con su propio algoritmo, ventana e ingeniería de características:

```python
has_hyperprofiles = any(p.get("hyperprofile") for p in treatment_target_profiles.values())
if has_hyperprofiles:
    self._train_per_target(...)  # ruta hyperprofile
else:
    ...  # ruta legacy (sección 4.2)
```

Los perfiles son inmutables y versionados en `hyperprofile_registry.py`. Cada clave referencia un diccionario con `algorithm`, `feature_variant`, `required_inputs`, `optional_inputs` y `params`. Esta inmutabilidad garantiza reproducibilidad: un modelo entrenado con `control_mcd_xgb_v1` sigue siendo predecible con la misma clave en el futuro, aunque se añadan nuevos perfiles al registro.

La versión UVL activa puede dejar de referenciar perfiles históricos sin eliminarlos del registro. En el estado actual del proyecto, `Pluviometro`, `Riego` y `HumedadRiego` se han retirado del contrato productivo; los perfiles vigentes trabajan con humedad, temperatura, DPV, dendrómetro y telemetría opcional.

Los algoritmos disponibles en la ruta hyperprofile son: **XGBoost**, **LightGBM**, **PLSRegression**, **SVR** y **ElasticNet**. Si XGBoost o LightGBM no están instalados, el sistema realiza un *fallback* a `HistGradientBoostingRegressor` con un aviso en los metadatos del modelo.

### 4.2. Ruta legacy (LSTM / RandomForest / GradientBoosting)

Cuando el UVL no declara `hyperprofile_<target>`, el pipeline usa la ruta clásica. La preferencia se obtiene del tratamiento y, opcionalmente, de la variable objetivo:

```python
profile = FlamapyService.get_treatment_profile(treatment)
target_profile = _merge_target_profiles([FlamapyService.get_target_profile(t) for t in targets])
preferred = target_profile.get("preferred_algorithm", profile["preferred_algorithm"])
```

La selección sigue esta cadena de decisión:

1. Si `preferred == "LSTM"` y TensorFlow no está disponible → `RandomForest` + aviso.
2. Si `preferred == "LSTM"` y filas completas < `min_samples` → `RandomForest` + aviso.
3. Si `preferred == "LSTM"` y datos suficientes → LSTM.
4. En cualquier otro caso → el algoritmo preferido directamente (`GradientBoosting` o `RandomForest`).

Esta ruta ejecuta todos los targets con el mismo algoritmo y la misma ventana, a diferencia de la ruta hyperprofile que los individualiza.

### 4.3. Justificación del diseño de doble ruta

La ruta hyperprofile nace de la fase de experimentación offline documentada en `docs/experimentacion_modelos.md`. Los experimentos demostraron que la combinación óptima de algoritmo, ventana e ingeniería de características varía significativamente entre pares tratamiento×objetivo. Esa evidencia justifica que el UVL pueda escoger perfiles distintos por target y que el registro conserve versiones históricas aunque el modelo activo evolucione: por ejemplo, MCD puede pasar de un perfil XGBoost experimental a un perfil PLSRegression con `stress_indices` sin romper modelos ya entrenados con la clave anterior.

La ruta legacy se mantiene por compatibilidad con modelos ya entrenados y para tratamientos o configuraciones que no requieran precisión en la selección de hiperparámetros.

---

## 5. Entrenamiento con LSTM

### 5.1. Motivación

Las redes LSTM (*Long Short-Term Memory*) son un tipo de red neuronal recurrente diseñada para trabajar con secuencias. En este proyecto se emplean cuando el Tratamiento seleccionado requiere capturar dependencias temporales entre días consecutivos.

La idea principal es que la predicción de la variable objetivo no depende únicamente del valor actual de los sensores, sino también de su evolución reciente.

Por ejemplo, para una ventana de 7 días:

```text
Entrada X:
  día t-7 → [objetivo, humedad, temperatura, NDVI, ...]
  día t-6 → [objetivo, humedad, temperatura, NDVI, ...]
  ...
  día t-1 → [objetivo, humedad, temperatura, NDVI, ...]

Salida y:
  día t → variable objetivo
```

El enfoque es **autoregresivo**, porque los valores históricos de la propia variable objetivo forman parte de la entrada del modelo.

### 5.2. Construcción de ventanas temporales

El entrenamiento LSTM comienza limpiando filas incompletas:

```python
df_clean = df[all_cols].dropna().reset_index(drop=True)
```

Después se divide el conjunto en entrenamiento y validación:

```python
n = len(df_clean)
split = int(n * 0.8)

train_df = df_clean.iloc[:split]
val_df = df_clean.iloc[split:]
```

La división es temporal: se usa el primer 80 % para entrenar y el 20 % final para validar. Esto es más adecuado que una división aleatoria, ya que en una serie temporal interesa comprobar si el modelo generaliza hacia datos posteriores.

Posteriormente se normalizan los datos con `MinMaxScaler`. El escalador de entrada se ajusta solo con la partición de entrenamiento:

```python
scaler_X = MinMaxScaler()
train_scaled = scaler_X.fit_transform(train_df[all_cols])
val_scaled = scaler_X.transform(val_df[all_cols])
```

Esto evita fuga de información (*data leakage*), ya que las estadísticas de validación no se utilizan para escalar el entrenamiento.

Las ventanas se construyen con:

```python
def make_windows(arr: np.ndarray) -> np.ndarray:
    return np.array(
        [arr[i:i + window_size] for i in range(len(arr) - window_size)],
        dtype="float32",
    )
```

Cada ventana contiene `window_size` filas consecutivas y todas las columnas de entrada (`all_cols`). El modelo recibe tensores con forma:

```text
(n_muestras, window_size, n_columnas)
```

### 5.3. Arquitectura de la red

La arquitectura implementada es compacta y adecuada para un TFG, ya que equilibra expresividad y coste computacional:

```python
inp = Input(shape=(window_size, len(all_cols)))
x = LSTM(128, activation="tanh")(inp)
x = Dropout(0.2)(x)
x = Dense(64, activation="relu")(x)
out = Dense(1)(x)
model = Model(inp, out)
```

La red se compone de:

- una capa LSTM de 128 unidades;
- una capa `Dropout` para reducir sobreajuste;
- una capa densa intermedia de 64 neuronas;
- una salida escalar, correspondiente al valor de la variable objetivo.

El modelo se compila con optimizador Adam y función de pérdida Huber:

```python
model.compile(
    optimizer=tf.keras.optimizers.Adam(0.001),
    loss=Huber(),
)
```

La pérdida Huber es una elección razonable en problemas de regresión con posibles valores atípicos, porque combina propiedades del error cuadrático y del error absoluto.

### 5.4. Parada temprana

El entrenamiento contempla hasta 200 épocas:

```python
total_epochs = 200
```

No obstante, se utiliza `EarlyStopping`:

```python
EarlyStopping(
    monitor="val_loss",
    patience=30,
    restore_best_weights=True,
    min_delta=1e-4,
)
```

Esto significa que el entrenamiento se detiene si la pérdida de validación no mejora durante 30 épocas. Además, se restauran los mejores pesos encontrados. Esta estrategia evita entrenamientos innecesariamente largos y reduce el riesgo de sobreajuste.

### 5.5. Métricas

Una vez entrenado el modelo, se predice sobre validación y se deshace la normalización:

```python
y_pred = scaler_Y[t].inverse_transform(model.predict(X_vl, verbose=0)).ravel()
y_true = scaler_Y[t].inverse_transform(y_vl.reshape(-1, 1)).ravel()
metrics[t] = _compute_metrics(y_true, y_pred)
```

Las métricas calculadas son:

| Métrica | Significado |
|---|---|
| MAE | Error absoluto medio |
| RMSE | Raíz del error cuadrático medio |
| R² | Coeficiente de determinación |

Además, se comparan los valores de R² con los umbrales de calidad definidos en el UVL para la variable objetivo.

---

## 6. Entrenamiento tabular legacy

### 6.1. Motivación

Cuando no hay suficientes datos para entrenar una LSTM, o TensorFlow no está disponible, la ruta legacy utiliza un modelo tabular de scikit-learn. En la implementación actual el fallback desde LSTM es `RandomForest`; la ruta tambien conserva soporte para `HistGradientBoostingRegressor` cuando la preferencia legacy es `GradientBoosting`.

Este algoritmo no procesa secuencias directamente como una red recurrente. Por ello, el sistema transforma la serie temporal en un problema tabular de regresión, añadiendo características temporales explícitas:

- retardos (*lags*);
- medias móviles;
- variables cíclicas del día del año.

El resultado es un conjunto de columnas que permite a un modelo tabular capturar información temporal.

### 6.2. Generación de características temporales

La función `_add_temporal_features` crea las variables adicionales:

```python
def _add_temporal_features(df: pd.DataFrame, input_features: list[str], window_size: int) -> pd.DataFrame:
    df = df.copy()
    day_of_year = df["date"].dt.dayofyear
    df["day_sin"] = np.sin(2 * np.pi * day_of_year / 365.0)
    df["day_cos"] = np.cos(2 * np.pi * day_of_year / 365.0)
    roll_w = min(7, window_size)

    for feat in input_features:
        for lag in range(1, window_size + 1):
            df[f"{feat}_lag{lag}"] = df[feat].shift(lag)
        df[f"{feat}_roll{roll_w}d"] = df[feat].shift(1).rolling(roll_w).mean()

    return df
```

Para cada variable se generan:

- `variable_lag1`, `variable_lag2`, ..., `variable_lagN`;
- `variable_rollXd`, donde `X` es como máximo 7 días;
- `day_sin` y `day_cos`, que representan la estacionalidad anual.

La codificación seno/coseno evita representar el día del año como un número lineal. Esto es importante porque el día 365 y el día 1 son temporalmente cercanos, aunque numéricamente estén alejados.

### 6.3. Entrenamiento tabular

Para cada variable objetivo se entrena un estimador independiente:

```python
feat_cols = [c for c in df_t.columns if c != t]
scaler = MinMaxScaler()

tr_arr = scaler.fit_transform(tr[[t] + feat_cols])
vl_arr = scaler.transform(vl[[t] + feat_cols])

X_tr, y_tr = tr_arr[:, 1:], tr_arr[:, 0]
X_vl, y_vl = vl_arr[:, 1:], vl_arr[:, 0]

est = _build_rf() if algorithm == "RandomForest" else _build_gb()
est.fit(X_tr, y_tr)
```

Se guarda también la lista exacta de columnas usadas para cada objetivo:

```python
feature_columns_by_target[t] = feat_cols
```

Esto es esencial para la inferencia, ya que el modelo debe recibir las columnas en el mismo orden y con la misma estructura con la que fue entrenado.

---

## 6b. Ingeniería de características modular (`feature_engineering.py`)

La ruta hyperprofile utiliza un módulo de ingeniería de características (`backend/apps/modelos/services/feature_engineering.py`) que implementa **variantes** nombradas. Cada variante combina un conjunto específico de transformaciones temporales:

| Variante | Transformaciones incluidas | Orientación |
|---|---|---|
| `basic` | Lags 1-5 + día del año cíclico | Uso general |
| `long_lags` | Lags hasta ventana + medias móviles largas | Series con memoria larga |
| `multi_roll` | Múltiples ventanas móviles (3, 7, 14, 30 d) | Tendencia a distintas escalas |
| `ema` | Medias exponenciales (α = 0.3, 0.7) + lags cortos | Respuesta a eventos recientes |
| `calendar` | Variables cíclicas de mes, semana, estación agronómica | Estacionalidad |
| `irrigation_memory` | Nombre heredado; lags + medias móviles + día del año cíclico, sin acumulados de riego/lluvia en la implementación actual | Compatibilidad de perfiles antiguos |
| `soil_profile` | Gradiente entre profundidades de humedad + lags | Suelos con perfil hídrico complejo |
| `stress_indices` | Rango térmico e interacciones DPV-temperatura, combinables con telemetría opcional | Estrés hídrico severo |
| `target_only` | Solo lags y suavizado del target (sin sensores externos) | Variables con alta autocorrelación |
| `full` | Unión de todas las transformaciones anteriores | Experimentación exhaustiva |

El atributo UVL `feat_variant_<target>` selecciona la variante apropiada para cada par tratamiento×objetivo. La función de entrada es:

```python
df_aug = add_features(df, feature_cols, window_size, feat_variant)
```

Todos los lags y medias móviles se aplican con `shift(≥1)`, garantizando que no hay fuga de información del día actual hacia las características de entrada (no data leakage).

> **Sugerencia de figura ML-B.1**: tabla comparativa de variantes con el número de características adicionales que genera cada una para un dataset típico de 3 sensores de entrada, ventana 7 días. Ilustra el trade-off entre expresividad y sobreajuste.

## 7. Persistencia de modelos

Al terminar el entrenamiento, el modelo se guarda en dos niveles:

1. **Sistema de ficheros**, mediante `StorageService`.
2. **Base de datos**, mediante el modelo Django `ModeloGuardado`.

### 7.1. Persistencia en disco

La carpeta base de modelos se define en la configuración de Django mediante `MODELS_STORAGE_PATH`. Para cada modelo se crea un directorio identificado por `model_id`.

En el caso de LSTM se guardan:

```text
model_storage/{model_id}/
  metadata.json
  lstm_TasaBuenos.keras
  scaler_X.pkl
  scaler_TasaBuenos.pkl
```

En el caso de scikit-learn se guardan:

```text
model_storage/{model_id}/
  metadata.json
  model_TasaBuenos.pkl
  scaler_TasaBuenos.pkl
```

El fichero `metadata.json` contiene información necesaria para reutilizar el modelo:

```json
{
  "model_id": "...",
  "algorithm": "Mixed",
  "treatment": "RiegoControl",
  "features": ["RiegoControl", "NDVI", "TasaBuenos"],
  "geo": { "punto": { "lat": 37.0, "lng": -4.0 } },
  "all_cols": ["TasaBuenos", "NDVI"],
  "targets": ["TasaBuenos"],
  "input_features": ["NDVI"],
  "window_size": 28,
  "target_profiles": {
    "TasaBuenos": {
      "algorithm": "SVR",
      "window_size": 28,
      "feature_variant": "target_only",
      "hyperprofile": "control_tasabuenos_svr_v1"
    }
  },
  "feature_columns_by_target": {
    "TasaBuenos": ["TasaBuenos_lag1", "TasaBuenos_roll7d"]
  },
  "metrics": {
    "TasaBuenos": {
      "mae": 0.12,
      "rmse": 0.18,
      "r2": 0.74
    }
  },
  "warnings": []
}
```

### 7.2. Persistencia en base de datos

Además de guardar los artefactos físicos del modelo, el backend crea un registro en `ModeloGuardado`:

```python
class ModeloGuardado(models.Model):
    model_id = models.CharField(max_length=36, unique=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, ...)
    algorithm = models.CharField(max_length=50)
    treatment = models.CharField(max_length=100)
    features = models.JSONField(default=list)
    geo = models.JSONField(default=dict)
    targets = models.JSONField()
    input_features = models.JSONField()
    all_cols = models.JSONField(default=list)
    metrics = models.JSONField()
    warnings = models.JSONField(default=list)
    n_samples = models.IntegerField(default=0)
    n_train = models.IntegerField(default=0)
    n_val = models.IntegerField(default=0)
    window_size = models.IntegerField(default=0)
    imported = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
```

Este registro permite:

- listar los modelos del usuario;
- aplicar permisos de propietario o administrador;
- mostrar métricas y metadatos en el frontend;
- acceder a la descarga del modelo;
- vincular predicciones futuras al modelo original.

---

## 8. Generación de valores desde modelos guardados

### 8.1. Objetivo del flujo de inferencia

Una vez entrenado un modelo, el usuario puede acceder a “Mis modelos” y pulsar “Generar valor”. Este flujo no reentrena el modelo. Su finalidad es usar el modelo ya existente para producir un nuevo valor de la variable objetivo.

El flujo se diseñó como una **predicción de un único paso**. Es decir, se genera un valor para el día siguiente al último registro del CSV recibido, pero no se encadenan predicciones recursivas a varios días vista. Esta decisión simplifica la inferencia y reduce la acumulación de error.

### 8.2. Preparación de datos para inferencia

La página `frontend/src/pages/GenerarValorModelo.tsx` carga los metadatos del modelo:

```typescript
const model = modelQuery.data ?? null;
const requiredCols = new Set(model?.all_cols ?? []);
```

A partir de `all_cols`, la interfaz sabe exactamente qué columnas necesita reconstruir. Esto evita solicitar al usuario datos que no se utilizaron durante el entrenamiento.

Por ejemplo:

- si el modelo no usa telemetría, no se exige extraer índices GEE;
- si el modelo no usa temperatura, no se pide CSV de temperatura;
- si el modelo usa `TasaBuenos`, se solicita el histórico necesario para esa variable.

La inferencia necesita al menos `window_size` filas completas. Esta condición se comprueba en el frontend:

```typescript
const canPredict = Boolean(
  fusionResult &&
  model &&
  fusionResult.rowCount >= model.window_size &&
  !predictMutation.isPending &&
  !duplicateExists
);
```

También se valida de nuevo en el backend, por lo que la restricción no depende únicamente de la interfaz. `duplicateExists` compara la fecha a predecir —el día siguiente al último registro fusionado— con el historial reciente del modelo y evita lanzar dos inferencias para la misma fecha.

### 8.3. Extracción de telemetría GEE

Si el modelo requiere índices de telemetría, el frontend usa la ubicación guardada en `geo`. Esta ubicación procede del entrenamiento original y garantiza que la nueva extracción se realice sobre la misma parcela.

El backend rechaza la predicción si el modelo no tiene ubicación guardada:

```python
if not record.geo or not isinstance(record.geo, dict) or not record.geo.get("punto"):
    return Response(
        {"detail": "El modelo no tiene ubicación guardada para extraer telemetría GEE."},
        status=400,
    )
```

Esta restricción es importante para mantener la coherencia espacial del modelo. Un modelo entrenado con datos de una parcela concreta no debería recibir telemetría de una ubicación indefinida.

### 8.4. Endpoint de predicción

La generación de valor se realiza mediante:

```http
POST /api/v1/modelos/{model_id}/predict
```

La petición contiene:

| Campo | Descripción |
|---|---|
| `csv_file` | CSV fusionado con las columnas históricas requeridas por el modelo |

El frontend construye el CSV de forma análoga al entrenamiento:

```typescript
const csvContent = fusionResultToCsv(fusionResult, ";");
const csvBlob = new Blob(["\uFEFF" + csvContent], {
  type: "text/csv;charset=utf-8;",
});

await predictMutation.mutateAsync({ modelId, csvBlob });
```

La respuesta contiene el valor generado:

```json
{
  "prediction_id": 10,
  "model_id": "1a2b3c4d-0000-0000-0000-000000000000",
  "generated_at": "2026-05-01T10:30:00Z",
  "predicted_for_date": "2026-05-01",
  "predictions": {
    "TasaBuenos": 0.8123
  },
  "input_row_count": 14,
  "warnings": []
}
```

Si ya existe una predicción para el mismo modelo y la misma `predicted_for_date`, el backend responde con `409 Conflict`:

```json
{
  "detail": "Ya existe una predicción para el 2026-05-01 en este modelo.",
  "existing_prediction_id": 10,
  "predicted_for_date": "2026-05-01"
}
```

---

## 9. Inferencia backend

La inferencia se implementa en `backend/apps/modelos/services/prediction_service.py`. El método principal es:

```python
def predict_one(self, model_id: str, csv_content: bytes) -> dict[str, Any]:
    metadata = self._storage.load_metadata(model_id)
    df = pd.read_csv(io.BytesIO(csv_content), sep=";", parse_dates=["date"], encoding="utf-8-sig")
    df = df.sort_values("date").reset_index(drop=True)

    algorithm = str(metadata.get("algorithm", ""))
    targets = list(metadata.get("targets") or [])
    input_features = list(metadata.get("input_features") or [])
    all_cols = list(metadata.get("all_cols") or (targets + input_features))
    window_size = int(metadata.get("window_size") or 0)

    if metadata.get("target_profiles"):
        predictions = self._predict_per_target(...)
    elif algorithm == "LSTM":
        predictions = self._predict_lstm(model_id, df, targets, all_cols, window_size)
    else:
        predictions = self._predict_sklearn(
            model_id,
            df,
            metadata,
            targets,
            input_features,
            window_size,
            algorithm,
        )
```

Antes de predecir, el servicio valida:

- que exista la columna `date`;
- que estén presentes todas las columnas de `all_cols`;
- que haya variables objetivo;
- que `window_size` sea válido;
- que existan suficientes filas completas.

### 9.1. Inferencia con LSTM

Para LSTM se recuperan:

- modelo `.keras`;
- escalador de entrada `scaler_X`;
- escaladores de salida por objetivo.

Después se selecciona la última ventana histórica:

```python
window = df_clean[all_cols].tail(window_size)
X = scaler_X.transform(window[all_cols]).astype("float32")
X = X.reshape(1, window_size, len(all_cols))
```

Cada modelo LSTM produce un valor escalado, que se transforma de nuevo a la escala original:

```python
y_scaled = lstm_models[target].predict(X, verbose=0)
value = scaler_Y[target].inverse_transform(y_scaled).ravel()[0]
predictions[target] = float(value)
```

La salida final es un diccionario `{variable_objetivo: valor}`.

### 9.2. Inferencia con modelos tabulares

En el caso de modelos tabulares, el estimador entrenado espera recibir las mismas columnas derivadas que se construyeron durante el entrenamiento: retardos, medias móviles, variables cíclicas y, en la ruta hyperprofile, la variante especifica declarada en `target_profiles`.

Para generar esas columnas, el servicio crea una fila sintética que representa el instante de predicción:

```python
predicted_for_date = (df["date"].max() + pd.Timedelta(days=1)).date()
last = df_hist.iloc[-1]
generated_date = pd.Timestamp(predicted_for_date)
future_row = {"date": generated_date}

for col in base_cols:
    future_row[col] = last[col]
```

Esta fila no se usa como verdad de la variable objetivo, sino como soporte para que las funciones de `shift` y `rolling` puedan construir las columnas de entrada del instante actual. Los retardos siguen procediendo de los datos históricos reales.

Después se aplican las mismas transformaciones temporales. En la ruta legacy se usa `_add_temporal_features`; en la ruta hyperprofile se usa `feature_engineering.add_features` con la variante guardada en los metadatos:

```python
df_future = pd.concat([df_hist, pd.DataFrame([future_row])], ignore_index=True)
df_aug = _add_temporal_features(df_future, base_cols, window_size)
row = df_aug.iloc[[-1]]
```

Finalmente, se cargan el modelo y el escalador, se seleccionan las columnas exactas y se predice:

```python
models, scalers = self._storage.load_sklearn(model_id, targets)
feat_cols = feature_columns_by_target[target]

arr = scaler.transform(row[[target, *feat_cols]])
pred_scaled = models[target].predict(arr[:, 1:]).reshape(-1, 1)
pred = _desescalar_parcial(scaler, pred_scaled, 0).ravel()[0]
predictions[target] = float(pred)
```

La función `_desescalar_parcial` permite invertir la normalización de una única columna aunque el escalador se haya ajustado sobre varias columnas.

---

## 10. Historial de predicciones

Cada valor generado se almacena en la tabla `PrediccionModelo`:

```python
class PrediccionModelo(models.Model):
    model = models.ForeignKey(ModeloGuardado, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, ...)
    generated_at = models.DateTimeField(auto_now_add=True)
    predicted_for_date = models.DateField()
    predictions = models.JSONField()
    input_row_count = models.IntegerField(default=0)
    warnings = models.JSONField(default=list)

    class Meta:
        ordering = ["-predicted_for_date", "-generated_at"]
        unique_together = [("model", "predicted_for_date")]
```

La vista `predict_model` crea el registro tras ejecutar la inferencia, siempre que no exista ya un valor generado para el mismo modelo y la misma fecha predicha:

```python
predicted_for_date = result["predicted_for_date"]
existing = PrediccionModelo.objects.filter(
    model=record,
    predicted_for_date=predicted_for_date,
).first()
if existing:
    return Response(..., status=409)

prediction = PrediccionModelo.objects.create(...)
```

El historial se consulta mediante:

```http
GET /api/v1/modelos/{model_id}/predictions
```

Este diseño aporta trazabilidad y evita duplicar el mismo horizonte de predicción. No solo se conoce el modelo entrenado, sino también qué valores se generaron posteriormente, cuándo se generaron y con cuántas filas de entrada. En el frontend, `GenerarValorModelo.tsx` representa el historial reciente con Recharts para visualizar la evolución temporal de los valores generados por target.

---

## 10b. Visualización de la serie de validación

Cuando el entrenamiento termina, el backend incluye en el registro del estado (`_registry[model_id]`) la serie de validación real y predicha:

```python
val_series_data[t] = {
    "y_true": y_true[:100].tolist(),
    "y_pred": y_pred[:100].tolist(),
}
```

El frontend, al consultar el estado completado, renderiza estas series mediante el componente `ValSeriesChart.tsx`. Este componente usa Recharts para dibujar dos líneas superpuestas —la real (verde) y la predicha (naranja discontinuo)— sobre el conjunto de validación, permitiendo al técnico evaluar visualmente la calidad del ajuste antes de guardar el modelo.

> **Sugerencia de figura ML-B.2**: captura del componente `ValSeriesChart` con datos reales del experimento, mostrando la alineación entre la curva real y la predicha para MCD con `control_mcd_xgb_v1`. Incluir en el mismo frame el valor de R² calculado.

## 11. Interfaces públicas del módulo de modelos

El módulo expone las siguientes interfaces REST:

| Método y ruta | Función |
|---|---|
| `POST /api/v1/modelos/train` | Inicia el entrenamiento de un nuevo modelo |
| `GET /api/v1/modelos/{model_id}/status` | Consulta el estado de entrenamiento |
| `GET /api/v1/modelos/` | Lista los modelos accesibles por el usuario |
| `GET /api/v1/modelos/{model_id}/` | Obtiene metadatos de un modelo |
| `DELETE /api/v1/modelos/{model_id}/` | Elimina un modelo accesible por el usuario |
| `GET /api/v1/modelos/{model_id}/download` | Descarga el modelo como ZIP |
| `POST /api/v1/modelos/import` | Importa un ZIP de modelo (solo administrador) |
| `POST /api/v1/modelos/{model_id}/predict` | Genera un valor con un modelo guardado |
| `GET /api/v1/modelos/{model_id}/predictions` | Lista el historial de predicciones |

Estas rutas separan claramente dos fases:

1. **Entrenamiento y gestión del modelo**.
2. **Inferencia y consulta de predicciones generadas**.

La separación facilita el mantenimiento del sistema y permite evolucionar cada fase de forma independiente.

---

## 12. Decisiones de diseño y justificación

### 12.1. Uso del UVL como fuente de verdad

La generación de modelos depende del UVL para conocer:

- variables objetivo;
- Tratamientos;
- columnas CSV;
- tamaño de ventana;
- algoritmo preferido;
- umbrales mínimos de datos;
- umbrales de calidad del modelo.

Esto evita duplicar conocimiento de dominio en Python y TypeScript. El código se mantiene genérico y el modelo de características actúa como punto central de variabilidad.

### 12.2. Entrenamiento asíncrono

El entrenamiento puede tardar varios minutos, especialmente con LSTM. Por ello, se lanza en segundo plano y se consulta su progreso mediante `GET /status`.

Esta decisión mejora la usabilidad y evita peticiones HTTP bloqueantes.

### 12.3. Fallback de LSTM a RandomForest

La LSTM es más expresiva para series temporales, pero también más exigente en datos y dependencias. El fallback a RandomForest permite que el sistema siga funcionando en escenarios donde:

- no hay TensorFlow disponible;
- el dataset tiene menos filas de las necesarias;
- se desea una solución más robusta con pocos datos.

### 12.4. Persistencia dual

Los artefactos pesados se guardan en disco, mientras que los metadatos se replican en base de datos. Esta combinación permite:

- cargar modelos reales para inferencia;
- listar modelos de forma eficiente;
- aplicar permisos;
- exportar e importar ZIP;
- mostrar métricas sin abrir ficheros de modelo.

### 12.5. Predicción de un solo paso

La generación de valores se limita a un único paso de inferencia. Esto evita predicciones recursivas, donde una salida estimada se reutiliza como entrada de la siguiente predicción. Aunque ese enfoque permitiría generar horizontes más largos, también acumularía error y requeriría una validación adicional.

Para el alcance del sistema, una predicción de un único valor es más controlada, explicable y coherente con el flujo de “Generar valor”.

---

## 13. Conclusión

La generación de modelos y valores en agroTrain2 combina configuración SPL, procesamiento temporal de datos, aprendizaje automático y persistencia de resultados. El usuario no selecciona manualmente un algoritmo ni define columnas internas: estas decisiones se derivan de la configuración validada y de los atributos del modelo UVL.

El entrenamiento transforma datos históricos fusionados en un modelo persistente, evaluado mediante métricas de regresión y asociado a un usuario. Posteriormente, ese modelo puede recuperarse desde “Mis modelos” y emplearse para generar nuevos valores de la variable objetivo a partir de datos recientes.

Desde una perspectiva arquitectónica, la solución aporta:

- **trazabilidad**, porque cada modelo y cada predicción quedan registrados;
- **reutilización**, porque un modelo entrenado puede descargarse, importarse y usarse posteriormente;
- **separación de responsabilidades**, porque frontend, endpoints, servicios de entrenamiento, almacenamiento e inferencia tienen funciones diferenciadas;
- **adaptabilidad**, porque la configuración UVL reduce el hardcoding de conocimiento de dominio;
- **robustez operativa**, porque el sistema contempla métricas, avisos, fallback de algoritmo y validaciones en backend.

Por todo ello, el módulo no se limita a entrenar un modelo aislado, sino que implementa un ciclo completo de vida de un sensor digital predictivo: configuración, entrenamiento, evaluación, persistencia, reutilización e inferencia.
