"""
Per-station data preparation for offline ML experimentation.

Loads the 24 sensor CSVs of a single station from `csvs/`, normalizes orthographic
variants in filenames (`Tª_*↔Ta_*`, `Pluviómetro/Pluvómetro/PLuviómetro→Pluviometro`,
`Dendrómetro→Dendrometro`), aggregates each sensor to daily granularity using the
same rules the frontend (`sensorMerger.ts`) applies, and computes MCD/TasaBuenos/
TasaSeveros from raw dendrometer readings via `dendro_calc.py`.

The result is a single DataFrame indexed by date that mimics the fused CSV the
production pipeline ingests, but with a richer sensor set (all 24 channels) and
without telemetry indices (GEE not available offline).
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

import pandas as pd

from .dendro_calc import calculate_dendro_params

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
CSV_DIR = REPO_ROOT / "csvs"

STATIONS: list[str] = [
    "Control_59_3-3_O",
    "Control_60_4-3_O",
    "RDC_49_5-1_O",
    "RDC_62_6-3_O",
    "Secano_46_2-1_O",
    "Secano_53_3-2_O",
]

PLATFORM_TARGETS: tuple[str, ...] = ("MCD", "TasaBuenos", "TasaSeveros")
PLATFORM_INPUTS_NO_TELEMETRY: tuple[str, ...] = (
    "humedad_Hd05",
    "humedad_Hd15",
    "humedad_Hd25",
    "humedad_Hd35",
    "humedad_Hd45",
    "humedad_Hd55",
    "humedad_Hd65",
    "humedad_Hd75",
    "tmax",
    "tmin",
    "pluv",
    "dpv",
)
PLATFORM_TELEMETRY_INPUTS: tuple[str, ...] = ("NDVI", "EVI", "SAVI", "NDWI")

# Suffix → (canonical_col_or_marker, aggregation_rule).
# `__air_temp__` triggers tmax/tmin extraction. `__dendro__` feeds dendro_calc.
SENSOR_MAP: dict[str, tuple[str, str]] = {
    # Soil humidity (avg)
    "Hd_05_cm": ("humedad_Hd05", "avg"),
    "Hd_15_cm": ("humedad_Hd15", "avg"),
    "Hd_25_cm": ("humedad_Hd25", "avg"),
    "Hd_35_cm": ("humedad_Hd35", "avg"),
    "Hd_45_cm": ("humedad_Hd45", "avg"),
    "Hd_55_cm": ("humedad_Hd55", "avg"),
    "Hd_65_cm": ("humedad_Hd65", "avg"),
    "Hd_75_cm": ("humedad_Hd75", "avg"),
    "Hd_Riego": ("hd_riego", "avg"),
    # Soil temperature at depth (avg)
    "Ta_05_cm": ("temp_s05", "avg"),
    "Ta_15_cm": ("temp_s15", "avg"),
    "Ta_25_cm": ("temp_s25", "avg"),
    "Ta_35_cm": ("temp_s35", "avg"),
    "Ta_45_cm": ("temp_s45", "avg"),
    "Ta_55_cm": ("temp_s55", "avg"),
    "Ta_65_cm": ("temp_s65", "avg"),
    "Ta_75_cm": ("temp_s75", "avg"),
    # Air temperature → tmax/tmin
    "Ta_Ambiente": ("__air_temp__", "minmax"),
    # Irrigation channels
    "Riego": ("riego", "sum"),
    "Ta_Riego": ("ta_riego", "avg"),
    "CE_Riego": ("ce_riego", "avg"),
    # Atmosphere
    "DPV": ("dpv", "avg"),
    "Pluviometro": ("pluv", "sum"),
    # Dendrometer → MCD / TasaBuenos / TasaSeveros via dendro_calc
    "Dendrometro": ("__dendro__", "raw"),
}

# Orthographic normalization on the filename suffix.
SUFFIX_REPLACEMENTS: dict[str, str] = {
    "Tª": "Ta",
    "Pluviómetro": "Pluviometro",
    "Pluvómetro": "Pluviometro",
    "PLuviómetro": "Pluviometro",
    "Dendrómetro": "Dendrometro",
}


def normalize_suffix(suffix: str) -> str:
    out = suffix
    for old, new in SUFFIX_REPLACEMENTS.items():
        out = out.replace(old, new)
    return out


def extract_suffix(filename: str, station: str) -> str | None:
    """Strip station prefix and the leading underscore, return raw suffix without `.csv`."""
    name = filename
    if name.endswith(".csv"):
        name = name[:-4]
    prefix = station + "_"
    if not name.startswith(prefix):
        return None
    return name[len(prefix):]


def _load_raw_csv(path: Path) -> pd.DataFrame:
    """All sensor files share the layout `data,timestamp` with ISO-8601 UTC timestamps."""
    df = pd.read_csv(path, sep=",", encoding="utf-8")
    df.columns = [c.strip().lstrip("﻿") for c in df.columns]
    if "timestamp" not in df.columns or "data" not in df.columns:
        raise ValueError(f"{path.name}: expected columns 'data,timestamp', got {list(df.columns)}")
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df["data"] = pd.to_numeric(df["data"], errors="coerce")
    df = df.dropna(subset=["timestamp", "data"])
    df["date"] = df["timestamp"].dt.tz_convert("UTC").dt.date
    return df


def _aggregate_daily(df: pd.DataFrame, rule: str) -> pd.Series:
    grouped = df.groupby("date")["data"]
    if rule == "avg":
        return grouped.mean()
    if rule == "min":
        return grouped.min()
    if rule == "max":
        return grouped.max()
    if rule == "sum":
        return grouped.sum()
    raise ValueError(f"Unknown aggregation rule: {rule}")


def _process_air_temperature(df: pd.DataFrame) -> pd.DataFrame:
    """Air temperature → daily min (tmin) and max (tmax) — matches production csv_cols 'tmax,tmin'."""
    grouped = df.groupby("date")["data"]
    return pd.DataFrame({"tmin": grouped.min(), "tmax": grouped.max()})


def _process_dendrometer(df: pd.DataFrame) -> pd.DataFrame:
    """Run dendro_calc on raw sub-daily readings → DataFrame with date / MCD / TasaBuenos / TasaSeveros."""
    timestamps = df["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    res = calculate_dendro_params(timestamps.tolist(), df["data"].tolist())
    all_dates = sorted(set(res.mcd) | set(res.tb) | set(res.ts))
    if not all_dates:
        return pd.DataFrame(columns=["date", "MCD", "TasaBuenos", "TasaSeveros"]).set_index("date")
    out = pd.DataFrame(
        {
            "MCD": [res.mcd.get(d) for d in all_dates],
            "TasaBuenos": [res.tb.get(d) for d in all_dates],
            "TasaSeveros": [res.ts.get(d) for d in all_dates],
        },
        index=pd.to_datetime(all_dates).date,
    )
    out.index.name = "date"
    return out


def list_station_files(station: str) -> list[Path]:
    return sorted(p for p in CSV_DIR.iterdir() if p.is_file() and p.name.startswith(station + "_"))


def prepare_station(station: str) -> tuple[pd.DataFrame, list[str]]:
    """
    Build the per-station daily DataFrame.

    Returns (DataFrame, warnings). DataFrame has a `date` column (datetime64[ns]) plus
    one column per sensor canonical name and the three target columns
    (MCD/TasaBuenos/TasaSeveros). Missing values stay as NaN.
    """
    warnings: list[str] = []
    files = list_station_files(station)
    if not files:
        raise FileNotFoundError(f"No CSV files found for station {station} under {CSV_DIR}")

    daily_series: dict[str, pd.Series] = {}
    seen_suffixes: set[str] = set()

    for path in files:
        raw_suffix = extract_suffix(path.name, station)
        if raw_suffix is None:
            continue
        suffix = normalize_suffix(raw_suffix)
        seen_suffixes.add(suffix)
        rule_entry = SENSOR_MAP.get(suffix)
        if rule_entry is None:
            warnings.append(f"{path.name}: suffix '{suffix}' not in SENSOR_MAP, skipped")
            continue

        canonical, rule = rule_entry
        try:
            df = _load_raw_csv(path)
        except Exception as exc:
            warnings.append(f"{path.name}: failed to load ({exc})")
            continue

        if df.empty:
            warnings.append(f"{path.name}: empty after parsing")
            continue

        if canonical == "__air_temp__":
            air = _process_air_temperature(df)
            daily_series["tmin"] = air["tmin"]
            daily_series["tmax"] = air["tmax"]
        elif canonical == "__dendro__":
            dendro = _process_dendrometer(df)
            for col in ("MCD", "TasaBuenos", "TasaSeveros"):
                if col in dendro.columns:
                    daily_series[col] = dendro[col]
        else:
            daily_series[canonical] = _aggregate_daily(df, rule)

    expected = set(SENSOR_MAP.keys())
    missing = sorted(expected - seen_suffixes)
    if missing:
        warnings.append(f"Sensores ausentes en estación {station}: {', '.join(missing)}")

    if not daily_series:
        raise RuntimeError(f"No daily series produced for station {station}")

    df_out = pd.concat(daily_series, axis=1).sort_index()
    df_out.index = pd.to_datetime(df_out.index)
    df_out.index.name = "date"
    full_idx = pd.date_range(df_out.index.min(), df_out.index.max(), freq="D")
    df_out = df_out.reindex(full_idx)
    df_out.index.name = "date"
    # Sum-aggregated event sensors (pluv, riego) report no row on dry/non-irrigation
    # days; treat those gaps as zero rather than NaN so they don't drop training rows.
    for col in ("pluv", "riego"):
        if col in df_out.columns:
            df_out[col] = df_out[col].fillna(0.0)
    df_out = df_out.reset_index()
    return df_out, warnings


def platform_input_columns(df: pd.DataFrame) -> list[str]:
    """Return the non-telemetry input columns that can be selected by the platform UVL."""
    return [c for c in PLATFORM_INPUTS_NO_TELEMETRY if c in df.columns]


def to_platform_training_frame(
    station_df: pd.DataFrame,
    targets: list[str] | tuple[str, ...] = PLATFORM_TARGETS,
    input_cols: list[str] | tuple[str, ...] = PLATFORM_INPUTS_NO_TELEMETRY,
) -> pd.DataFrame:
    """
    Project a rich offline station frame to the same CSV contract used by training.

    Production receives a semicolon CSV with `date`, selected target columns and
    `input_cols` derived from UVL feature `csv_col/csv_cols` attributes. Telemetry
    columns (`NDVI/EVI/SAVI/NDWI`) are intentionally excluded here to avoid GEE.
    Extra raw channels present in `csvs/` but not exposed by the UVL are ignored.
    """
    cols = ["date"]
    cols.extend(c for c in targets if c in station_df.columns and c not in cols)
    cols.extend(c for c in input_cols if c in station_df.columns and c not in cols)
    out = station_df[cols].copy()
    numeric_cols = [c for c in out.columns if c != "date"]
    out[numeric_cols] = out[numeric_cols].round(4)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare per-station daily DataFrame.")
    parser.add_argument("--station", required=True, choices=STATIONS, help="Station prefix")
    parser.add_argument("--output", type=Path, default=None, help="Optional output CSV path")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    df, warnings = prepare_station(args.station)
    for w in warnings:
        logger.warning(w)
    print(f"Station: {args.station}")
    print(f"Rows: {len(df)}    Date range: {df['date'].min().date()} → {df['date'].max().date()}")
    print(f"Columns ({len(df.columns)}): {list(df.columns)}")
    print("Non-null counts per target/sensor (top 10):")
    print(df.drop(columns=["date"]).count().sort_values(ascending=False).head(10).to_string())
    if args.output:
        df.to_csv(args.output, index=False)
        print(f"Written: {args.output}")


if __name__ == "__main__":
    main()
