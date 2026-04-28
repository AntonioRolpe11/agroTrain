# Cómo funciona el sistema como línea de producto (SPL)

Este documento explica de forma informal cómo está montado todo el sistema para que sea una **línea de producto de software (SPL)**. La idea central es que el fichero `agroTrain.uvl` es el "cerebro" de la aplicación: define qué cultivos existen, qué sensores admite, qué índices de telemetría se pueden usar y qué variables objetivo se pueden predecir. Nadie hardcodea esa información en Python ni en TypeScript — todo se lee del UVL en tiempo de ejecución.

---

## 1. Qué es UVL y cómo está montado el fichero

UVL (Universal Variability Language) es un formato de texto para describir **feature models**: árboles de características con relaciones entre ellas. En agroTrain2 el árbol tiene esta pinta resumida:

```
Entrada
├── DatosParcela  [wizard_step: parcel]
│   ├── Cultivo  (ALTERNATIVE: solo uno)
│   │   ├── Olivo  { window_size 7, preferred_algorithm 'LSTM', min_samples 730, ... }
│   │   ├── Almendro  { window_size 5, ... }
│   │   └── ...
│   └── TipoSuelo  (ALTERNATIVE: solo uno)
│       ├── CampinaArcillosa  { label 'Campiña arcillosa / bujeo' }
│       └── ...
├── ParametrosEntrada  [wizard_step: sensors, label: 'Parámetros de entrada']
│   ├── Dendrometro  (MANDATORY)
│   │   └── DatoMCD / DatoTB / DatoTS  (OPTIONAL, csv_col: 'MCD' / ...)
│   ├── HumedadSuelo  (OPTIONAL)
│   │   └── Hd05..Hd75  (OPTIONAL, csv_col: 'humedad_HdXX')
│   └── TemperaturaAire  (OPTIONAL, csv_cols: 'tmax,tmin')
├── DatosTelemetria  [wizard_step: telemetry]
│   └── NDVI / EVI / SAVI / NDWI  (OPTIONAL, csv_col: ...)
└── VariableObjetivo  [wizard_step: objective]
    └── TasaBuenos / TasaSeveros / MCD  (ALTERNATIVE, quality_min: ..., quality_good: ...)
```

Y luego hay un bloque de `constraints` que define reglas entre features:

```
TasaBuenos => DatoTB          # si eliges esa variable objetivo, necesitas ese sensor
Olivo => Hd35 | Hd45 | Hd55  # el olivo requiere humedad a esas profundidades
LomasCalizasAlbariza => (SAVI & NDWI)  # ese tipo de suelo obliga a esos índices GEE
```

**Lo importante**: las relaciones entre nodos del árbol pueden ser:
- `mandatory` — siempre activo, no hay opción
- `optional` — el usuario puede activarlo o no
- `alternative` — exactamente uno de los hijos (radio)
- `or` — uno o más hijos (checkbox, mínimo uno)

Y cada nodo puede tener **atributos** en `{ ... }` que son información extra que el sistema lee para hacer cosas.

---

## 2. Los atributos: qué son y para qué sirven

Un atributo es simplemente metadata que cuelgas de un nodo del UVL. Cuando Flamapy lo lee, los expone como pares clave-valor. El sistema los usa para todo:

| Atributo | Quién lo usa | Para qué |
|---|---|---|
| `label` | Frontend (wizard, mensajes de error) y backend (mensajes de validación) | Nombre legible en español del feature. Sin él se usa el nombre técnico (`LomasCalizasAlbariza` vs `Lomas calizas / albariza`) |
| `wizard_step` | Backend y frontend | A qué paso del wizard pertenece este subárbol. Permite la validación por pasos |
| `csv_col` | Backend (entrenamiento) y frontend (Results.tsx) | Nombre de la columna en el CSV de sensores que mapea este feature |
| `csv_cols` | Ídem | Cuando un feature genera varias columnas (TemperaturaAire → `tmax,tmin`) |
| `window_size` | Backend (training_service.py) | Días de ventana lag para LSTM/GB según el cultivo |
| `preferred_algorithm` | Backend | `'LSTM'` o `'GradientBoosting'` para ese cultivo |
| `min_samples` | Backend | Si el CSV tiene menos filas que esto, fuerza GradientBoosting aunque el cultivo prefiera LSTM |
| `min_reject` | Frontend (Results.tsx) | Mínimo de filas fusionadas para no bloquear el entrenamiento |
| `min_warn` | Frontend | Umbral de aviso de datos insuficientes |
| `min_good` | Frontend | A partir de cuántas filas los datos son "buenos" |
| `quality_min` | Backend (training_service.py) | R² mínimo aceptable para esta variable objetivo |
| `quality_good` | Backend | R² que se considera bueno |

Si añades un cultivo nuevo al UVL con todos esos atributos, el sistema lo tiene en cuenta automáticamente en todo: wizard, validación, entrenamiento, umbrales. Sin tocar ni una línea de Python ni TypeScript.

---

## 3. El servicio Flamapy: cómo se lee el UVL

`FlamapyService` (en `backend/apps/configurador/services/flamapy_service.py`) es la pieza central del backend. Es un singleton (usa variables de clase) que arranca una sola vez al iniciar el servidor de Django.

### 3.1. Arranque: `warm_up()`

Cuando Django arranca, `apps.py` llama a `FlamapyService.warm_up(path)`. Esto hace cuatro cosas:

```python
fm_model = UVLReader(str(path)).transform()     # 1. Lee el .uvl y lo parsea
cls._base_bdd_model = FmToBDD(fm_model).transform()  # 2. Construye el BDD
cls._all_feature_names = cls._collect_all_feature_names(fm_model.root)  # 3. Lista todos los features
cls._labels = cls._collect_labels()             # 4. Extrae todos los atributos 'label'
cls._partial_scope_features = cls._derive_partial_scope_features()  # 5. Mapea features a pasos del wizard
```

**El BDD** (Binary Decision Diagram) es la representación matemática del modelo de features + sus constraints. Con él se puede verificar si una selección de features es satisfacible (válida) en microsegundos, sin iterar por todas las combinaciones posibles. Se construye una sola vez y se reutiliza en todas las validaciones.

### 3.2. Cómo extrae los labels

```python
def _collect_labels_rec(cls, feature, labels):
    for attr in feature.get_attributes():
        if attr.name == "label" and attr.default_value:
            labels[feature.name] = attr.default_value
    for relation in feature.get_relations():
        for child in relation.children:
            cls._collect_labels_rec(child, labels)
```

Recorre el árbol recursivamente. Si un nodo tiene atributo `label`, lo guarda en el diccionario `{nombre_feature: label_español}`. Luego `get_label("LomasCalizasAlbariza")` devuelve `"Lomas calizas / albariza"`.

### 3.3. Cómo mapea features a pasos del wizard

```python
def _assign_to_steps(cls, feature, scope, unassigned):
    for attr in feature.get_attributes():
        if attr.name == "wizard_step" and attr.default_value:
            step = attr.default_value
            scope[step].extend(cls._collect_all_feature_names(feature))
            return  # para aquí, todo el subárbol pertenece a ese paso
    unassigned.append(feature.name)
    for relation in feature.get_relations():
        for child in relation.children:
            cls._assign_to_steps(child, scope, unassigned)
```

Recorre el árbol. Cuando encuentra un nodo con `wizard_step`, coge ese nodo entero con todos sus descendientes y los asigna a ese paso. No sigue recursando por dentro de ese subárbol (ya están asignados). Los nodos sin `wizard_step` (como el nodo raíz `Entrada`) van al primer paso.

El resultado es un diccionario:
```python
{
  "parcel":    ["DatosParcela", "Cultivo", "Olivo", "Almendro", ..., "TipoSuelo", ...],
  "sensors":   ["ParametrosEntrada", "Dendrometro", "DatoMCD", ..., "HumedadSuelo", ...],
  "telemetry": ["DatosTelemetria", "NDVI", "EVI", "SAVI", "NDWI", "Nubes"],
  "objective": ["VariableObjetivo", "TasaBuenos", "TasaSeveros", "MCD"],
}
```

### 3.4. `to_dict()`: serialización del árbol para el frontend

Hay un endpoint `GET /api/v1/configurator/feature-model` que devuelve el árbol completo como JSON. `FlamapyService.to_dict()` lo genera recursivamente:

```python
def _to_dict_rec(cls, feature) -> dict:
    attrs = {a.name: a.default_value for a in feature.get_attributes()}
    return {
        "name": feature.name,
        "relations": [
            {
                "type": cls._relation_type(relation),   # MANDATORY / OPTIONAL / ALTERNATIVE / OR
                "children": [cls._to_dict_rec(child) for child in relation.children],
            }
            for relation in feature.get_relations()
        ],
        "attributes": attrs  # todos los atributos del UVL, tal cual
    }
```

Y también serializa los constraints como ASTs (árboles de expresiones):

```json
{
  "features": ["TasaBuenos", "DatoTB"],
  "ast": {
    "op": "IMPLIES",
    "left": { "op": "FEATURE", "name": "TasaBuenos" },
    "right": { "op": "FEATURE", "name": "DatoTB" }
  }
}
```

El frontend recibe esto y puede evaluar los constraints él mismo sin llamar al backend.

---

## 4. Validación por pasos: cómo funciona el BDD

Cuando el usuario pulsa "Listo" en un paso del wizard, el frontend llama a:
```
POST /api/v1/configurator/validate-features
{ features: ["Olivo", "Hd35", "TasaBuenos", ...], is_full: false, step: "sensors" }
```

El backend hace esto:

```python
# Scope acumulado hasta ese paso: parcel + sensors
scope = set(self._get_features_for_step("sensors"))

pin_constraints = []
for name in all_feature_names:
    if name in features_set:
        pin_constraints.append(name)       # activo → forzar True
    elif name in scope:
        pin_constraints.append(f"!{name}") # en scope pero no activo → forzar False
    # fuera de scope → libre (el BDD lo puede satisfacer con cualquier valor)
```

Luego añade esas restricciones al UVL como constraints adicionales y construye un BDD temporal. Si el BDD es satisfacible con esas restricciones extra, la selección es válida.

**Por qué esto funciona:** si el usuario tiene seleccionado `Olivo` (que requiere `Hd35 | Hd45 | Hd55`) y ha puesto `Hd35`, al evaluar en el paso `sensors` tanto `Olivo` como `Hd35` están en scope y se pinen a True → el BDD lo satisface. Si el usuario no hubiera puesto ninguna humedad, `Hd35`, `Hd45` y `Hd55` se pinarían a False dentro de scope, y el BDD diría "insatisfacible".

Pero los features de `telemetry` y `objective` **no están en scope todavía**, así que el BDD los deja libres — puede satisfacerlos como quiera. Esto es lo que permite validar paso a paso sin que los constraints entre pasos distintos bloqueen antes de tiempo.

### Mensajes de error genéricos

Si la validación falla, `_get_violated_constraint_messages()` recorre todos los constraints del UVL que son del tipo `A => B`, comprueba cuáles están dentro del scope actual, y para cada uno donde el antecedente está activo pero el consecuente no se satisface, genera un mensaje en español usando los labels:

```python
antecedent_label = cls.get_label("Olivo")           # → "Olivo"
consequent_str = cls._format_ast(ast["right"])       # → "Humedad a 35 cm o Humedad a 45 cm o Humedad a 55 cm"
messages.append(f"{antecedent_label} requiere {consequent_str}.")
```

Sin hardcodear ningún mensaje. Si añades un cultivo nuevo con sus constraints, los mensajes salen solos.

---

## 5. El frontend: cómo se renderiza el wizard de forma genérica

### 5.1. FeatureNode: el renderizador recursivo

`src/components/feature-model/FeatureNode.tsx` toma un nodo del árbol JSON y lo renderiza. El tipo de relación dicta el control:

```
MANDATORY   → badge informativo (no clicable, siempre activo)
ALTERNATIVE → botones de radio (solo uno seleccionable)
OR          → checkboxes (mínimo uno)
OPTIONAL    → checkboxes libres
```

El label que muestra cada botón lo saca de `child.attributes?.label ?? child.name`. Si el nodo tiene `label` en el UVL, lo usa; si no, usa el nombre técnico.

Cuando un usuario activa un nodo que tiene hijos, el componente se renderiza recursivamente con esos hijos indentados. Esto es completamente automático: si añades un nodo con hijos opcionales al UVL, aparecen solos en el wizard.

```tsx
{activeChildren.map((child) => {
  if (!hasRelations(child)) return null;
  return (
    <div className="border-l-2 border-primary/25 pl-4">
      <FeatureNode node={child} depth={depth + 1} ... />
    </div>
  );
})}
```

### 5.2. Estado global: `FeatureTreesContext`

El estado de qué features están activos vive en `trees[0].features: string[]` — simplemente una lista de nombres de features activos. Al cargar el modelo por primera vez, se inicializa con todos los features MANDATORY (que están siempre activos).

Cuando el usuario clica un botón en `FeatureNode`, se llama a `handleToggle` o `handleRadioChange` que actualiza esa lista. Todos los componentes que necesitan saber qué hay activo leen de ahí.

### 5.3. Hints de constraints en tiempo real

Cada paso del wizard (StepSensores, StepTelemetria, StepObjetivo) muestra avisos en tiempo real antes de pulsar "Listo". Lo hace evaluando los constraints del modelo localmente con dos funciones:

**`getViolations(constraints, subtreeNames, activeFeatures)`**  
Constraints donde TODOS los features mencionados están dentro del scope del paso actual, y que están violados. Estos bloquean el botón "Listo".

```typescript
// Ejemplo: "DatoTS" y "TasaSeveros" están ambos en el scope de sensors+objective
// Si TasaSeveros está activo pero DatoTS no, esto aparece como violación en objetivo
return constraints.filter(c =>
  c.features.every(f => subtreeNames.has(f)) && !evalAST(c.ast, active)
);
```

**`getIncomingRequirements(constraints, accumulatedScopeNames, activeFeatures)`**  
Constraints IMPLIES donde el antecedente está completamente activo, el constraint está violado, y al menos un feature del consecuente ya está dentro del scope acumulado hasta ahora. Aparecen como avisos ámbar que te dicen "si tienes X activo, necesitas Y".

```typescript
// Ejemplo: tienes LomasCalizasAlbariza (paso parcel) que requiere SAVI & NDWI (paso telemetry)
// En el paso telemetry ya puedes ver ese aviso aunque LomasCalizasAlbariza es de un paso anterior
```

El evaluador de ASTs es el mismo tanto en frontend como en backend, implementado de forma espejo:

```typescript
// Frontend (TypeScript)
function evalAST(ast, features: Set<string>): boolean {
  if (ast.op === "FEATURE") return features.has(ast.name);
  if (ast.op === "IMPLIES") return !evalAST(ast.left, features) || evalAST(ast.right, features);
  if (ast.op === "AND") return evalAST(ast.left, features) && evalAST(ast.right, features);
  if (ast.op === "OR") return evalAST(ast.left, features) || evalAST(ast.right, features);
  ...
}
```

```python
# Backend (Python)
def _eval_ast(cls, node, selected):
    if node["op"] == "FEATURE": return node["name"] in selected
    if node["op"] == "IMPLIES": return not cls._eval_ast(node["left"], selected) or cls._eval_ast(node["right"], selected)
    ...
```

---

## 6. Results.tsx: generación automática de tarjetas de sensores

Esta es la pantalla donde el usuario sube los CSVs de sensores. Las tarjetas se generan automáticamente a partir del UVL.

### 6.1. `collectCsvFeatures()`: sensores genéricos

```typescript
const genericSensors = collectCsvFeatures(model, features, HARDCODED_SENSOR_IDS);
```

Esta función recorre el subárbol `ParametrosEntrada` del modelo, y para cada nodo que:
1. Está en `activeFeatures` (el usuario lo activó)
2. Tiene `csv_col` o `csv_cols`
3. No está en `HARDCODED_SENSOR_IDS` (los que tienen lógica especial: Dendrómetro, TemperaturaAire)

...devuelve `{ featureName, csvCol, label }`. Luego Results.tsx renderiza una `<SensorFileCard>` por cada uno:

```tsx
{genericSensors.map((sensor) => (
  <SensorFileCard
    key={sensor.featureName}
    title={sensor.label}
    csvCol={sensor.csvCol}
    ...
  />
))}
```

Si añades un sensor nuevo al UVL con `csv_col`, aparece automáticamente su tarjeta de upload sin cambiar nada en React.

### 6.2. `buildCsvColumnInfo()`: columnas de telemetría

```typescript
const telemetryColumnInfo = buildCsvColumnInfo(model, "DatosTelemetria");
```

Recorre el subárbol `DatosTelemetria` y extrae todos los `csv_col` en una lista. Esto se usa para:
- Saber qué columnas esperar en el CSV de telemetría
- Verificar que los índices seleccionados están presentes en el CSV subido

Si añades `NDRE { csv_col 'NDRE' }` bajo DatosTelemetria en el UVL, el sistema ya sabe que el CSV puede tener una columna `NDRE` sin tocar código.

### 6.3. `buildCropTrainingThresholds()`: indicadores de calidad de datos

```typescript
const cropThresholds = buildCropTrainingThresholds(model);
```

Lee los atributos `min_reject`, `min_warn`, `min_good` de cada cultivo bajo `Cultivo`. Luego busca cuál es el cultivo activo y usa sus umbrales para mostrar el indicador de calidad del dataset fusionado (rojo / amarillo / verde).

### 6.4. Los sensores hardcodeados (excepción legítima)

Hay dos sensores con lógica especial que NO se generan de forma genérica:
- **Dendrómetro**: los datos brutos de diámetro de tronco requieren cálculo específico (MCD, TasaBuenos, TasaSeveros) implementado en `dendroCalc.ts`. No es configurable en UVL porque es física del sensor.
- **TemperaturaAire**: un solo archivo pero genera dos columnas (`tmin`/`tmax`) vía agregación min/max diaria.

Por eso existen en `HARDCODED_SENSOR_IDS` y se excluyen de `collectCsvFeatures`. Sus tarjetas están renderizadas manualmente en Results.tsx.

---

## 7. Entrenamiento ML: parámetros desde el UVL

Cuando el usuario pulsa "Entrenar", el frontend manda:
```
POST /api/v1/modelos/train
{ features: [...lista de features activos...], csv_file: <el CSV fusionado> }
```

El backend hace:

```python
# 1. Saber qué features son targets (variable objetivo)
target_names = FlamapyService.get_subtree_feature_names("VariableObjetivo")
targets = [f for f in features if f in target_names]
# → ["TasaBuenos"]  (la convención es que el nombre del feature == nombre de columna CSV)

# 2. Saber qué features son columnas de entrada
crops = FlamapyService.get_subtree_feature_names("Cultivo")
input_cols = []
for feature in features:
    if feature not in targets and feature not in crops:
        input_cols += FlamapyService.get_csv_columns(feature)
# get_csv_columns lee csv_col / csv_cols del nodo

# 3. Leer el perfil del cultivo
crop = [f for f in features if f in crops][0]   # → "Olivo"
profile = FlamapyService.get_crop_profile("Olivo")
# → { window_size: 7, preferred_algorithm: 'LSTM', min_samples: 730 }

# 4. Leer los umbrales de calidad de la variable objetivo
thresholds = FlamapyService.get_quality_thresholds("TasaBuenos")
# → { min: 0.60, good: 0.80 }
```

Todo viene del UVL. No hay un `crop_profiles.py` con diccionarios hardcodeados. Si cambias `window_size` de Olivo en el UVL, el próximo entrenamiento lo usa sin redeployar.

---

## 8. Cómo añadir cosas nuevas al sistema

### Añadir un cultivo

En `agroTrain.uvl`, bajo `Cultivo > alternative`:

```uvl
MiCultivo { window_size 6, preferred_algorithm 'LSTM', min_samples 500,
            min_reject 50, min_warn 100, min_good 400 }
```

Y si tiene requisito de humedad, un constraint:

```uvl
MiCultivo => Hd25 | Hd35 | Hd45
```

Eso es todo. El wizard lo muestra, la validación lo aplica, el entrenamiento usa esos parámetros.

### Añadir un sensor genérico

En `ParametrosEntrada > optional`:

```uvl
MiSensor { label 'Nombre bonito', csv_col 'mi_col' }
```

Aparece automáticamente en el wizard (checkbox activable) y en Results.tsx (tarjeta de upload de CSV).

### Añadir un índice de telemetría

En `DatosTelemetria > optional`:

```uvl
NDRE { csv_col 'NDRE' }
```

El frontend lo recoge en `buildCsvColumnInfo`, el backend sabe que es una columna esperada en el CSV. Lo único que sí hay que hacer a mano es añadir la fórmula de banda Sentinel-2 en `telemetry_service.py` (eso es física de satélite, no configuración).

### Añadir una variable objetivo

En `VariableObjetivo > alternative`:

```uvl
MiVariable { label 'Mi variable', quality_min 0.50, quality_good 0.70 }
```

Y el constraint que la conecta a su sensor:

```uvl
MiVariable => MiSensor
```

Por convenio, el nombre del feature (`MiVariable`) debe coincidir con el nombre de la columna en el CSV fusionado. El sistema lo usa así en el entrenamiento.

---

## 9. El flujo completo de una sesión de usuario

1. **Django arranca** → `warm_up()` lee el UVL, construye el BDD, extrae labels, mapea features a pasos.

2. **Frontend carga** → llama a `GET /api/v1/configurator/feature-model` → recibe el árbol completo con relaciones, atributos y constraints como JSON.

3. **Paso 1 (Parcela)**: `FeatureNode` renderiza el subárbol `DatosParcela` recursivamente. El usuario elige cultivo y tipo de suelo (ALTERNATIVE → radio). Al pulsar "Listo":
   - Frontend valida que todos los grupos ALTERNATIVE tienen algo seleccionado (check local)
   - Llama a `POST /validate-features` con `step: "parcel"`
   - Backend pina los features de scope parcel a True/False, deja el resto libre, comprueba BDD

4. **Paso 2 (Sensores)**: igual pero scope ya incluye parcel + sensors. Los constraints entre cultivo y humedad se comprueban ahora porque ambos están en scope.

5. **Paso 3 (Telemetría)**: scope acumulado parcel + sensors + telemetry. El constraint `LomasCalizasAlbariza => SAVI & NDWI` se evalúa aquí (LomasCalizasAlbariza es de parcel, SAVI/NDWI son de telemetry, ambos en scope).

6. **Paso 4 (Objetivo)**: scope completo. Se hace validación final con `is_full: false, step: "objective"`.

7. **Results.tsx**:
   - `collectCsvFeatures()` genera las tarjetas de upload automáticamente
   - Usuario sube CSVs, el sistema los fusiona con telemetría GEE/CSV
   - `POST /api/v1/modelos/train` con la lista de features activos → backend lee el UVL para sacar parámetros de entrenamiento → lanza LSTM o GradientBoosting
   - Resultados incluyen R² comparado con `quality_min`/`quality_good` del UVL

---

## 10. Por qué esto es una línea de producto

Una línea de producto de software (SPL) es un conjunto de sistemas que comparten una arquitectura común pero varían en features. Aquí:

- **El producto** es "un sensor virtual digital configurado para un cultivo concreto"
- **La línea de producto** es todos los posibles sensores para todos los cultivos, suelos, sensores e índices posibles
- **El feature model** (el UVL) define el espacio de variabilidad: qué combinaciones son válidas
- **El BDD** verifica matemáticamente que una selección concreta es una configuración válida dentro de ese espacio

Añadir un nuevo miembro a la línea de producto (nuevo cultivo, nuevo sensor, nueva variable objetivo) es solo añadir nodos al UVL con sus atributos. El resto del sistema — wizard, validación, entrenamiento, mensajes de error, tarjetas de upload — se adapta solo porque todo se deriva del UVL en tiempo de ejecución.

Lo que NO está en el UVL (y es la excepción legitimada):
- Fórmulas de bandas Sentinel-2 (física de satélite)
- Cálculos del dendrómetro (algoritmo de dominio, no configuración)
- El orden de los pasos del wizard (UI concern, no derivable del árbol)
