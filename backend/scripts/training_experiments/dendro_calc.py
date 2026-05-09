"""
Python port of frontend/src/lib/dendroCalc.ts (GlobalSense algorithm).

Computes MCD (maximum contraction of the day), TasaBuenos (TB) and TasaSeveros (TS)
from raw sub-daily dendrometry readings. Constants and behaviour MUST stay in sync
with the TypeScript reference, which itself mirrors splent_feature_data_processing/services.py.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable

import pandas as pd

MCD_MAX_CUTOFF_SECS = 11 * 3600 + 59 * 60 + 59  # 11:59:59
MCD_MIN_START_SECS = 9 * 3600                   # 09:00:00
MCD_MIN_END_SECS = 22 * 3600 + 59 * 60 + 59     # 22:59:59
TCT_WEEK_DAYS = 7

# Empirically calibrated for GlobalSense sensor (~3.18× smaller than pure μm).
# −0.1 mm / 3.18 ≈ −32  |  +0.3 mm / 3.18 ≈ 94  |  −0.3 mm / 3.18 ≈ −95
TCT_GOOD_MIN = -32
TCT_GOOD_MAX = 94
TCT_SEVERE_MAX = -95


_ISO_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})[T ](\d{2}):(\d{2})(?::(\d{2}))?")
_DMY_SLASH_RE = re.compile(
    r"^(\d{1,2})/(\d{1,2})/(\d{4})(?:\s+(\d{2}):(\d{2})(?::(\d{2}))?)?"
)
_DMY_DASH_RE = re.compile(
    r"^(\d{1,2})-(\d{1,2})-(\d{4})(?:\s+(\d{2}):(\d{2})(?::(\d{2}))?)?"
)


def parse_timestamp(raw: str) -> tuple[str, int] | None:
    """Parses ISO8601 / DD/MM/YYYY / DD-MM-YYYY into (date_str, secs_since_midnight)."""
    s = (raw or "").strip()
    if not s:
        return None

    m = _ISO_RE.match(s)
    if m:
        date = m.group(1)
        h, mi = int(m.group(2)), int(m.group(3))
        sec = int(m.group(4) or 0)
        return date, h * 3600 + mi * 60 + sec

    m = _DMY_SLASH_RE.match(s)
    if m:
        day, month, year = m.group(1).zfill(2), m.group(2).zfill(2), m.group(3)
        h = int(m.group(4) or 0)
        mi = int(m.group(5) or 0)
        sec = int(m.group(6) or 0)
        return f"{year}-{month}-{day}", h * 3600 + mi * 60 + sec

    m = _DMY_DASH_RE.match(s)
    if m:
        day, month, year = m.group(1).zfill(2), m.group(2).zfill(2), m.group(3)
        h = int(m.group(4) or 0)
        mi = int(m.group(5) or 0)
        sec = int(m.group(6) or 0)
        return f"{year}-{month}-{day}", h * 3600 + mi * 60 + sec

    return None


@dataclass
class DendroSelection:
    mcd: bool = True
    tb: bool = True
    ts: bool = True


@dataclass
class DendroResult:
    mcd: dict[str, float]
    tb: dict[str, float]
    ts: dict[str, float]
    warnings: list[str]


def calculate_dendro_params(
    timestamps: Iterable[str],
    values: Iterable[float | str],
    selected: DendroSelection | None = None,
) -> DendroResult:
    """
    Calculates MCD/TB/TS from sub-daily dendrometry readings.

    `timestamps` and `values` are parallel sequences (one per reading).
    Days or windows where the required time-of-day data is absent are skipped.
    """
    sel = selected or DendroSelection()
    warnings: list[str] = []

    if not (sel.mcd or sel.tb or sel.ts):
        return DendroResult({}, {}, {}, warnings)

    # 1. Build daily buckets [(secs, value)] per date.
    daily: dict[str, list[tuple[int, float]]] = {}
    unparsed_rows = 0
    for ts_raw, v_raw in zip(timestamps, values):
        parsed = parse_timestamp(str(ts_raw or ""))
        if parsed is None:
            unparsed_rows += 1
            continue
        date, secs = parsed
        try:
            v = float(str(v_raw).replace(",", "."))
        except (TypeError, ValueError):
            continue
        if v != v:  # NaN
            continue
        daily.setdefault(date, []).append((secs, v))

    if unparsed_rows > 0:
        warnings.append(f"{unparsed_rows} fila(s) ignoradas por timestamp no reconocido.")

    if not daily:
        warnings.append("No se encontraron datos válidos en el CSV.")
        return DendroResult({}, {}, {}, warnings)

    for readings in daily.values():
        readings.sort(key=lambda r: r[0])

    # 2. Sub-daily resolution check for MCD.
    if sel.mcd:
        days_with_window = sum(
            1
            for readings in daily.values()
            if any(MCD_MIN_START_SECS <= s <= MCD_MIN_END_SECS for s, _ in readings)
        )
        if days_with_window == 0:
            warnings.append(
                "MCD no calculable: el CSV no contiene lecturas entre las 09:00 y las 23:00. "
                "Se necesitan datos sub-diarios con marca temporal horaria para calcular MCD."
            )
            sel = DendroSelection(mcd=False, tb=sel.tb, ts=sel.ts)

    # 3. MCD + maxBefore12 (also feeds TCT).
    mcd_result: dict[str, float] = {}
    max_before_12: dict[str, float] = {}
    mcd_skipped = 0

    for date, readings in daily.items():
        before_max = [v for s, v in readings if s <= MCD_MAX_CUTOFF_SECS]
        window_min = [v for s, v in readings if MCD_MIN_START_SECS <= s <= MCD_MIN_END_SECS]

        if before_max:
            max_before_12[date] = max(before_max)

        if sel.mcd:
            if before_max and window_min:
                mcd_result[date] = max(max(before_max) - min(window_min), 0.0)
            else:
                mcd_skipped += 1

    if sel.mcd and mcd_skipped > 0:
        warnings.append(
            f"MCD: {mcd_skipped} día(s) omitidos por falta de lecturas en las ventanas horarias requeridas "
            "(antes de las 12:00 y/o entre las 09:00–23:00)."
        )

    # 4. TCT — needed for TB/TS.
    tct_result: dict[str, float] = {}
    tct_gaps = 0

    if sel.tb or sel.ts:
        if not max_before_12:
            warnings.append(
                "TB/TS no calculables: ningún día tiene lecturas antes de las 12:00, "
                "necesarias para calcular el TCT."
            )
            return DendroResult(
                mcd=mcd_result if sel.mcd else {},
                tb={},
                ts={},
                warnings=warnings,
            )

        ordered_days = sorted(max_before_12.keys())
        for i in range(len(ordered_days) - 1):
            d_n = ordered_days[i]
            d_n1 = ordered_days[i + 1]
            gap = (datetime.fromisoformat(d_n1) - datetime.fromisoformat(d_n)).days
            if gap == 1:
                diff = max_before_12[d_n1] - max_before_12[d_n]
                tct_result[d_n1] = round(diff, 2)
            else:
                tct_gaps += 1

        if tct_gaps > 0:
            warnings.append(
                f"TCT: {tct_gaps} transición(es) entre días no consecutivos omitidas. "
                "Los huecos interrumpen la ventana deslizante de 7 días para TB/TS."
            )

    # 5. Rolling 7-day window for TB / TS.
    tb_result: dict[str, float] = {}
    ts_result: dict[str, float] = {}

    if sel.tb or sel.ts:
        tct_days = sorted(tct_result.keys())

        if len(tct_days) < TCT_WEEK_DAYS:
            warnings.append(
                f"TB/TS no calculables: se necesitan al menos {TCT_WEEK_DAYS} días consecutivos con TCT "
                f"(solo hay {len(tct_days)} disponibles)."
            )
        else:
            windows_skipped = 0
            for i in range(len(tct_days)):
                window_start = max(0, i - (TCT_WEEK_DAYS - 1))
                window_days = tct_days[window_start : i + 1]

                consecutive = len(window_days) == TCT_WEEK_DAYS
                if consecutive:
                    for j in range(len(window_days) - 1):
                        gap = (
                            datetime.fromisoformat(window_days[j + 1])
                            - datetime.fromisoformat(window_days[j])
                        ).days
                        if gap != 1:
                            consecutive = False
                            break

                if not consecutive:
                    windows_skipped += 1
                    continue

                window = [tct_result[d] for d in window_days]
                day = tct_days[i]

                if sel.tb:
                    buenos = sum(1 for d in window if TCT_GOOD_MIN <= d <= TCT_GOOD_MAX)
                    tb_result[day] = round(buenos / TCT_WEEK_DAYS * 100, 4)
                if sel.ts:
                    severos = sum(1 for d in window if d < TCT_SEVERE_MAX)
                    ts_result[day] = round(severos / TCT_WEEK_DAYS * 100, 4)

            if windows_skipped > 0:
                warnings.append(
                    f"TB/TS: {windows_skipped} día(s) omitidos porque su ventana de 7 días contiene huecos."
                )

            if not tb_result and not ts_result:
                warnings.append(
                    "TB/TS: no se produjo ningún resultado. Verifica que el CSV contiene al menos "
                    f"{TCT_WEEK_DAYS + 1} días consecutivos con lecturas válidas antes de las 12:00."
                )

    return DendroResult(
        mcd=mcd_result if sel.mcd else {},
        tb=tb_result if sel.tb else {},
        ts=ts_result if sel.ts else {},
        warnings=warnings,
    )


def dendro_dataframe(timestamps: Iterable[str], values: Iterable[float | str]) -> pd.DataFrame:
    """Convenience wrapper: returns a DataFrame indexed by date with columns MCD/TasaBuenos/TasaSeveros."""
    res = calculate_dendro_params(timestamps, values)
    all_dates = sorted(set(res.mcd) | set(res.tb) | set(res.ts))
    return pd.DataFrame(
        {
            "date": pd.to_datetime(all_dates),
            "MCD": [res.mcd.get(d) for d in all_dates],
            "TasaBuenos": [res.tb.get(d) for d in all_dates],
            "TasaSeveros": [res.ts.get(d) for d in all_dates],
        }
    )
