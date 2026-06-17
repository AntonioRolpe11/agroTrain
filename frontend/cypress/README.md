# Tests E2E (Cypress)

Suite de sistema que cruza frontend + backend reales y **conduce la plataforma
por navegador** (no por API): login + guards, wizard del configurador (UVL → UI)
con sus restricciones SPL, configuraciones, ingesta de CSV + fusión +
entrenamiento real, listado de modelos, inferencia, y administración de usuarios
y versiones UVL.

Antes de cada spec, `cy.task("resetBackend")` ejecuta el comando Django
`reset_test_state`, que deja una DB determinista (usuarios `admin@test.local` y
`tecnico@test.local` de prueba + UVL `v2_olivos_tratamientos.uvl` activa).

## Selectores

Los componentes llevan atributos `data-cy` estables (p. ej. los botones de
feature del wizard son `data-cy="feature-<NombreFeatureUVL>"`), de modo que los
specs no dependen del texto de las etiquetas UVL en español.

## Helpers (`cypress/support/`)

- `cy.resetBackend()` — flush + reseed determinista (Django).
- `cy.loginAs("admin" | "tecnico")` — persiste el JWT, salta el formulario.
- `cy.completeWizard(opts?)` — recorre los 4 pasos del wizard hasta
  `/validacion-modelo`. Config válida por defecto: `RiegoDeficitario` +
  `Luvisoles` + `DatoTB/Hd35/DPV` + `NDVI` + objetivo `TasaBuenos`.
- `cy.trainModelViaApi(opts?)` — entrena un modelo vía API y espera a que
  termine (precondición rápida para specs de modelos/inferencia).
- `cy.uploadSensorCard(label, content, fileName, tsCol, dataCol)` — sube un CSV
  a una `SensorFileCard` y vincula sus columnas.
- `support/fixtures.ts` — generadores deterministas: `buildDendrometerCsv`
  (sub-diario, lo parsea `dendroCalc.ts`), `buildDailySensorCsv`,
  `buildTelemetryCsv`, `buildFusedCsv`.

## Telemetría (GEE)

El camino de entrenamiento usa un **CSV de telemetría propio** (determinista,
sin GEE). El spec `11_telemetria_ui` ejercita la UI de extracción interceptando
`POST /telemetry/extract` con `cypress/fixtures/telemetry-extract.json`. No se
necesitan credenciales de Google Earth Engine.

## Requisitos

- **Backend**: venv en `backend/.venv` con las deps instaladas
  (`pip install -r backend/requirements/development.txt`, Python 3.12).
  El config localiza el intérprete solo: prueba `backend/.venv` (Unix y Windows),
  luego `python3`/`python` del PATH, o `CYPRESS_PYTHON` si lo defines.
- **Frontend**: `npm install` en `frontend/`.
- `reset_test_state` solo corre con `DEBUG=True` (settings de desarrollo, por
  defecto). Usa la DB de desarrollo (`backend/db.sqlite3`) y la **vacía** en cada
  corrida — en un clon nuevo no hay nada que perder; en un entorno con datos,
  respáldala antes.

## Ejecutar

Tres procesos. Backend y frontend en una terminal cada uno, Cypress en la tercera:

```bash
# Terminal 1 — backend (con el python del venv)
cd backend
.venv/bin/python manage.py migrate
.venv/bin/python manage.py runserver 8000

# Terminal 2 — frontend
cd frontend
npm run dev            # sirve en :8080

# Terminal 3 — tests (headless)
cd frontend
npm run cypress:run    # o: npm run cypress:open  (modo interactivo)
```

`cypress:run` arranca, resetea el estado por spec y corre los ficheros de
`cypress/e2e/`. Verde = sistema OK de punta a punta.

Specs:

```
01_auth                  login, sesión y guards admin
02_navegacion            landing, navbar, 404
03_wizard_completo       4 pasos del configurador (UVL → UI)
04_wizard_restricciones  restricciones SPL aplicadas en la UI
05_configuraciones       guardar / cargar / borrar / importar
06_results_entrenamiento ingesta CSV → fusión → entrenamiento real
07_mis_modelos           listado y acciones por modelo
08_inferencia            generar valor + histórico
09_admin_usuarios        CRUD de usuarios (admin)
10_admin_uvl             versiones UVL: bifurcar / activar / borrar
11_telemetria_ui         extracción de telemetría (GEE simulado)
```

## Notas

- Los specs pesados (`06`, `08`, `11`) entrenan modelos reales sobre CSV
  pequeños; sube el `defaultCommandTimeout`/espera en el propio spec si la
  máquina es lenta.
- Override del runner del reset fuera de Docker:
  `CYPRESS_RESET_CMD="backend/.venv/bin/python" npm run cypress:run`.
