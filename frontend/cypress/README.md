# Tests E2E (Cypress)

Suite de sistema que cruza frontend + backend reales: login JWT, wizard del
configurador (UVL → UI), entrenamiento de modelos, sensor de validación vs
operativo, e inferencia.

No mockea nada. Antes de cada spec, `cy.task("resetBackend")` ejecuta el comando
Django `reset_test_state`, que deja una DB determinista (usuarios `admin` y
`tecnico` de prueba + UVL `v2_olivos_tratamientos.uvl` activa).

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

`cypress:run` arranca, resetea el estado por spec y corre los 10 ficheros de
`cypress/e2e/`. Verde = sistema OK de punta a punta.

## Notas

- No requiere credenciales de Google Earth Engine: ningún spec extrae telemetría
  (usan CSV `date;<objetivo>`).
- Override del intérprete: `CYPRESS_PYTHON=/ruta/a/python npm run cypress:run`.
