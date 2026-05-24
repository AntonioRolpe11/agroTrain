"""
Genera un CSV de entrenamiento por tipo de tratamiento, combinando las estaciones
que pertenecen a cada tratamiento. Columnas: dendrometría (MCD/TasaBuenos/TasaSeveros),
humedad por alturas (Hd05..Hd75), temperatura ambiente (tmax/tmin) y DPV.

Salida: csvs/entrenamiento_{Tratamiento}.csv
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from .data_prep import CSV_DIR, prepare_station

logger = logging.getLogger(__name__)

# Los CSV de Secano_46_2-1_O viven en una subcarpeta, no sueltos en csvs/.
SECANO_46_DIR = CSV_DIR / "secano49:26-5-5"

# Tratamiento UVL -> [(estación, csv_dir_override_o_None), ...].
TREATMENT_STATIONS: dict[str, list[tuple[str, Path | None]]] = {
    "RiegoControl": [("Control_59_3-3_O", None), ("Control_60_4-3_O", None)],
    "RiegoDeficitario": [("RDC_49_5-1_O", None), ("RDC_62_6-3_O", None)],
    "RiegoDeficitarioSevero": [("Secano_46_2-1_O", SECANO_46_DIR), ("Secano_53_3-2_O", None)],
}

# Columnas pedidas, en orden.
DENDRO_COLS = ["MCD", "TasaBuenos", "TasaSeveros"]
HUMIDITY_COLS = [
    "humedad_Hd05", "humedad_Hd15", "humedad_Hd25", "humedad_Hd35",
    "humedad_Hd45", "humedad_Hd55", "humedad_Hd65", "humedad_Hd75",
]
TEMP_AIR_COLS = ["tmax", "tmin"]
ATM_COLS = ["dpv"]

OUTPUT_COLS = ["date", "station", *DENDRO_COLS, *HUMIDITY_COLS, *TEMP_AIR_COLS, *ATM_COLS]


def build_treatment_frame(treatment: str, stations: list[tuple[str, Path | None]]) -> pd.DataFrame:
    parts: list[pd.DataFrame] = []
    for station, csv_dir in stations:
        df, warnings = prepare_station(station, csv_dir)
        for w in warnings:
            logger.warning("[%s] %s", station, w)
        df = df.copy()
        df["station"] = station
        for col in OUTPUT_COLS:
            if col not in df.columns:
                df[col] = pd.NA
        parts.append(df[OUTPUT_COLS])
    combined = pd.concat(parts, ignore_index=True)
    combined = combined.sort_values(["station", "date"]).reset_index(drop=True)
    numeric = [c for c in combined.columns if c not in ("date", "station")]
    combined[numeric] = combined[numeric].apply(pd.to_numeric, errors="coerce").round(4)
    return combined


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    for treatment, stations in TREATMENT_STATIONS.items():
        df = build_treatment_frame(treatment, stations)
        out_path = CSV_DIR / f"entrenamiento_{treatment}.csv"
        df.to_csv(out_path, index=False, sep=",", encoding="utf-8")
        station_names = [s for s, _ in stations]
        print(
            f"{out_path.name}: {len(df)} filas, estaciones={station_names}, "
            f"rango={df['date'].min()} -> {df['date'].max()}"
        )


if __name__ == "__main__":
    main()
