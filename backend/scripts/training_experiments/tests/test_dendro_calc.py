"""
Sanity tests for the Python port of dendroCalc.ts.

These cover the deterministic pieces (timestamp parsing, MCD math, TCT diff,
TB/TS rolling thresholds). Numbers are derived directly from the algorithm's
definitions; if the TS reference (`dendroCalc.ts`) ever drifts, these tests
will catch the divergence.
"""
from __future__ import annotations

import pytest

from backend.scripts.training_experiments.dendro_calc import (
    TCT_GOOD_MAX,
    TCT_GOOD_MIN,
    TCT_SEVERE_MAX,
    TCT_WEEK_DAYS,
    DendroSelection,
    calculate_dendro_params,
    parse_timestamp,
)


# ─────────────────────────────────────── timestamp parsing ──

def test_parse_iso_with_seconds():
    assert parse_timestamp("2025-02-10T12:34:56Z") == ("2025-02-10", 12 * 3600 + 34 * 60 + 56)


def test_parse_iso_without_seconds():
    assert parse_timestamp("2025-02-10T08:00") == ("2025-02-10", 8 * 3600)


def test_parse_dmy_slash_with_time():
    # 5/3/2025 14:30 → 2025-03-05 14:30:00
    assert parse_timestamp("5/3/2025 14:30") == ("2025-03-05", 14 * 3600 + 30 * 60)


def test_parse_dmy_dash_no_time():
    assert parse_timestamp("05-03-2025") == ("2025-03-05", 0)


def test_parse_invalid_returns_none():
    assert parse_timestamp("hello") is None
    assert parse_timestamp("") is None


# ─────────────────────────────────────── MCD ──

def test_mcd_basic_one_day():
    # Day with: 09:00→10.0, 11:30→12.0 (max before 12), 14:00→9.0 (min in window 09-23)
    timestamps = [
        "2025-04-01T09:00:00Z",
        "2025-04-01T11:30:00Z",
        "2025-04-01T14:00:00Z",
    ]
    values = [10.0, 12.0, 9.0]
    res = calculate_dendro_params(timestamps, values, DendroSelection(mcd=True, tb=False, ts=False))
    assert res.mcd["2025-04-01"] == pytest.approx(3.0)  # 12 - 9 = 3
    assert res.tb == {}
    assert res.ts == {}


def test_mcd_clamps_to_zero_when_negative():
    # Reading rises after 12:00 → max_before_12 < min_window → clamp to 0
    timestamps = [
        "2025-04-01T08:00:00Z",
        "2025-04-01T10:00:00Z",
        "2025-04-01T15:00:00Z",
    ]
    values = [5.0, 6.0, 8.0]  # max_before_12 = 6, min_window = 8 → diff = -2 → max(_, 0) = 0
    res = calculate_dendro_params(timestamps, values, DendroSelection(mcd=True, tb=False, ts=False))
    assert res.mcd["2025-04-01"] == 0.0


def test_mcd_skipped_without_morning_window():
    # Only readings after 12 → no max_before_12 → MCD undefined for this day
    timestamps = ["2025-04-01T15:00:00Z", "2025-04-01T18:00:00Z"]
    values = [10.0, 11.0]
    res = calculate_dendro_params(timestamps, values, DendroSelection(mcd=True, tb=False, ts=False))
    assert "2025-04-01" not in res.mcd
    assert any("MCD no calculable" in w or "MCD: " in w for w in res.warnings)


# ─────────────────────────────────────── TCT + TB/TS ──

def _fabricate_eight_consecutive_days(max_morning_values: list[float]) -> tuple[list[str], list[float]]:
    """Return timestamps/values such that max_before_12 per day equals each input value."""
    assert len(max_morning_values) == 8
    timestamps: list[str] = []
    values: list[float] = []
    for i, v in enumerate(max_morning_values, start=1):
        date = f"2025-04-{i:02d}"
        # Single 11:00 reading per day → it becomes max_before_12.
        timestamps.append(f"{date}T11:00:00Z")
        values.append(v)
        # An afternoon reading so MCD-only days don't affect TCT.
        timestamps.append(f"{date}T15:00:00Z")
        values.append(v - 0.1)
    return timestamps, values


def test_tct_diff_consecutive_days():
    # max_before_12: [100, 110, 105, 108, 100, 95, 90, 100]
    # TCT (day_n+1 - day_n): [10, -5, 3, -8, -5, -5, 10] for days 02..08
    ts, vs = _fabricate_eight_consecutive_days([100, 110, 105, 108, 100, 95, 90, 100])
    res = calculate_dendro_params(ts, vs, DendroSelection(mcd=False, tb=True, ts=False))
    # Day 8 has a 7-day window covering days 2..8 with TCTs above
    # All inside [TCT_GOOD_MIN, TCT_GOOD_MAX] → TB = 7/7 * 100 = 100.0
    assert res.tb["2025-04-08"] == pytest.approx(100.0)


def test_ts_counts_severe_drops():
    # TCT[i] < TCT_SEVERE_MAX (-95) → count as severe.
    # Drop one big value to push TCT very negative.
    morning = [100, 100, 100, 100, 100, 100, -50, 100]  # day7 TCT = -150 (severe), day8 = +150 (NOT severe; > GOOD_MAX though)
    ts, vs = _fabricate_eight_consecutive_days(morning)
    res = calculate_dendro_params(ts, vs, DendroSelection(mcd=False, tb=False, ts=True))
    # Day 8 window covers days 2..8, TCTs ~ [0,0,0,0,0,-150,150]. Severos = 1/7 * 100 ≈ 14.2857
    assert res.ts["2025-04-08"] == pytest.approx(100 / 7, abs=1e-4)


def test_tb_ts_skipped_with_short_data():
    # Only 3 days of TCT data (4 days total) → cannot fill 7-day window.
    timestamps = []
    values = []
    for i in range(1, 5):
        timestamps.append(f"2025-04-0{i}T11:00:00Z")
        values.append(100.0)
    res = calculate_dendro_params(timestamps, values, DendroSelection(mcd=False, tb=True, ts=True))
    assert res.tb == {}
    assert res.ts == {}
    assert any("TB/TS no calculables" in w for w in res.warnings)


# ─────────────────────────────────────── threshold sanity ──

def test_threshold_constants_match_reference():
    # Pinning the empirically calibrated GlobalSense thresholds to catch accidental edits.
    assert TCT_GOOD_MIN == -32
    assert TCT_GOOD_MAX == 94
    assert TCT_SEVERE_MAX == -95
    assert TCT_WEEK_DAYS == 7
