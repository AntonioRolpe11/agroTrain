/**
 * Contextual help shown as tooltips next to each wizard *category* header
 * (treatment, soil, input parameters, telemetry, objective). Individual
 * feature options are intentionally left without tooltips.
 *
 * Keyed by UVL feature name. Components could read `attributes.help` from the
 * UVL first and fall back to this map, so help text can later move into the
 * UVL (`help '...'` attribute) without touching any component.
 */
export const FEATURE_HELP: Record<string, string> = {
  Tratamiento:
    "Estrategia de riego de la parcela. Determina los perfiles de entrenamiento (algoritmo, ventana y variantes) de cada variable objetivo.",
  TipoSuelo:
    "Clase de suelo de la parcela. Condiciona qué índices de telemetría son relevantes para el modelo.",
  ParametrosEntrada:
    "Sensores físicos cuyos datos se cargarán como CSV para alimentar el entrenamiento del modelo. Marca de cuáles dispones datos.",
  DatosTelemetria:
    "Índices de vegetación extraídos de Sentinel-2 vía Google Earth Engine para el punto seleccionado. Complementan a los sensores de campo.",
  VariableObjetivo:
    "Variable agronómica que el modelo aprenderá a predecir (MCD, Tasa de buenos o Tasa de severos).",
};
