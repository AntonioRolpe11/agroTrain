# Notas: Adaptación ML para contexto olivos

## Contexto
Posible especialización de agroTrain2 solo para olivos. Estaciones reales con dos dimensiones de tratamiento:
- **Régimen hídrico**: Control / RDC (déficit regulado) / Secano (déficit severo)
- **Fertilización**: Compost / Fertiriego

Estaciones: Control 59, Control 60, RDC 49, RDC 62, Secano 53, Secano 46.

## Decisiones clave

**Tratamiento como dimensión UVL no aporta para estratificar modelos** — el usuario ya importa el CSV de la estación concreta, el tratamiento está implícito en la señal.

**Donde sí aporta el tratamiento como metadato:**
- `window_size` distinto por régimen (secano → lag mayor, respuesta más lenta)
- Feature importance: en secano el dendrómetro es más predictivo; en control, humedad suelo
- `quality_min` más permisivo para secano (señal más ruidosa)

## Multi-estación (mismo tratamiento)

RDC 49 + RDC 62 tienen las mismas fechas → no se pueden concatenar cronológicamente.

**Solución propuesta:** usar una como train y otra como validación externa.
- Más exigente que split temporal: prueba generalización a otro árbol
- R² resultante más honesto (sin data leakage árbol-árbol)

**Implementación mínima:**
- `POST /api/v1/modelos/train` acepta `val_csv_file` opcional
- Si presente, omite split 80/20 temporal y usa ese CSV como validation set
- `metadata.json` registra estrategia de validación usada

## Pendiente
- Decidir si se implementa `val_csv_file` en el endpoint de entrenamiento
- Definir atributos UVL para `window_size` diferenciado por régimen hídrico en olivo
