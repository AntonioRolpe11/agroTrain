"""
Carga de los 3 CSV de entrenamiento por tratamiento como fuente de datos del harness.

A diferencia de `data_prep.prepare_station` (que reconstruye cada estación desde sus 24 CSV
sueltos en `csvs/`), aquí la fuente son los ficheros `entrenamiento_{tratamiento}.csv` ya
generados por `make_training_csvs.py`. Cada uno agrupa las 2 parcelas de su tratamiento y trae
una columna `station`. Este módulo los lee y los **divide por estación** para que el runner siga
trabajando con **una serie por parcela** (sin pooling: nunca se concatenan parcelas distintas en
el mismo entrenamiento).

El frame por estación que se devuelve cumple el mismo contrato que
`data_prep.to_platform_training_frame`: columnas `date` + targets + inputs de plataforma
(humedad por alturas, tmax, tmin, dpv), sin telemetría.
"""
from __future__ import annotations

import logging

import pandas as pd

from .data_prep import CSV_DIR, PLATFORM_INPUTS_NO_TELEMETRY, PLATFORM_TARGETS

logger = logging.getLogger(__name__)

# Tratamiento UVL -> fichero de entrenamiento.
TREATMENT_CSVS: dict[str, str] = {
    "RiegoControl": "entrenamiento_RiegoControl.csv",
    "RiegoDeficitario": "entrenamiento_RiegoDeficitario.csv",
    "RiegoDeficitarioSevero": "entrenamiento_RiegoDeficitarioSevero.csv",
}

# Estación (parcela) -> tratamiento al que pertenece.
STATION_TO_TREATMENT: dict[str, str] = {
    "Control_59_3-3_O": "RiegoControl",
    "Control_60_4-3_O": "RiegoControl",
    "RDC_49_5-1_O": "RiegoDeficitario",
    "RDC_62_6-3_O": "RiegoDeficitario",
    "Secano_46_2-1_O": "RiegoDeficitarioSevero",
    "Secano_53_3-2_O": "RiegoDeficitarioSevero",
}


def treatment_of(station: str) -> str:
    """Tratamiento UVL de una estación. KeyError si la estación es desconocida."""
    return STATION_TO_TREATMENT[station]


def stations_of(treatment: str) -> list[str]:
    """Estaciones (parcelas) que componen un tratamiento, en orden estable."""
    return [s for s, t in STATION_TO_TREATMENT.items() if t == treatment]


def _platform_columns(df: pd.DataFrame) -> list[str]:
    """date + targets + inputs de plataforma presentes, en orden canónico."""
    cols = ["date"]
    cols += [c for c in PLATFORM_TARGETS if c in df.columns and c not in cols]
    cols += [c for c in PLATFORM_INPUTS_NO_TELEMETRY if c in df.columns and c not in cols]
    return cols


def load_training_csv_frames() -> dict[str, pd.DataFrame]:
    """
    Lee los 3 CSV de entrenamiento y devuelve {station: frame_plataforma}.

    Cada frame es la serie diaria de UNA parcela (date + targets + inputs), ordenada por fecha,
    con `date` en datetime64 y sin la columna `station`. No se mezclan parcelas.
    """
    frames: dict[str, pd.DataFrame] = {}
    for treatment, filename in TREATMENT_CSVS.items():
        path = CSV_DIR / filename
        if not path.exists():
            logger.warning("CSV de entrenamiento ausente: %s (tratamiento %s)", path, treatment)
            continue
        raw = pd.read_csv(path, sep=",", encoding="utf-8")
        if "station" not in raw.columns:
            raise ValueError(f"{path.name}: falta la columna 'station'")
        if "date" not in raw.columns:
            raise ValueError(f"{path.name}: falta la columna 'date'")
        raw["date"] = pd.to_datetime(raw["date"], errors="coerce")

        for station, station_raw in raw.groupby("station"):
            if station in frames:
                logger.warning("Estación duplicada %s en %s; se ignora la repetición", station, path.name)
                continue
            cols = _platform_columns(station_raw)
            frame = station_raw[cols].sort_values("date").reset_index(drop=True)
            frames[str(station)] = frame

    if not frames:
        raise FileNotFoundError(
            f"No se cargó ninguna estación desde los CSV de entrenamiento en {CSV_DIR}. "
            "¿Se generaron con make_training_csvs.py?"
        )
    return frames
