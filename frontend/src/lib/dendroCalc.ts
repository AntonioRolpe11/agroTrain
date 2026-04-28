import type { CsvPreviewRow } from "./csvDataset";

// GlobalSense algorithm constants — must match splent_feature_data_processing/services.py
const MCD_MAX_CUTOFF_SECS = 11 * 3600 + 59 * 60 + 59; // 11:59:59
const MCD_MIN_START_SECS = 9 * 3600;                   // 09:00:00
const MCD_MIN_END_SECS = 22 * 3600 + 59 * 60 + 59;    // 22:59:59
const TCT_WEEK_DAYS = 7;
// Thresholds calibrados empíricamente para el sensor GlobalSense de esta instalación.
// El sensor entrega unidades ~3.18× más pequeñas que μm puros, de ahí los valores:
//   −0.1 mm / 3.18 ≈ −32  |  +0.3 mm / 3.18 ≈ 94  |  −0.3 mm / 3.18 ≈ −95
// Verificados contra plataforma de referencia: MAE = 0% en 94 días solapados.
const TCT_GOOD_MIN = -32;
const TCT_GOOD_MAX = 94;
const TCT_SEVERE_MAX = -95;

export interface DendroSelection {
  mcd: boolean;
  tb: boolean;
  ts: boolean;
}

export interface DendroParams {
  mcd?: Map<string, number>;
  tb?: Map<string, number>;
  ts?: Map<string, number>;
  /** Human-readable warnings about days or windows that could not be computed. */
  warnings: string[];
}

interface TimedValue {
  secs: number; // seconds since midnight
  value: number;
}

function parseTimestamp(raw: string): { date: string; secs: number } | null {
  const s = String(raw ?? "").trim();
  if (!s) return null;

  let date: string | null = null;
  let h = 0, m = 0, sec = 0;

  const isoMatch = s.match(/^(\d{4}-\d{2}-\d{2})[T ](\d{2}):(\d{2})(?::(\d{2}))?/);
  if (isoMatch) {
    date = isoMatch[1];
    h = parseInt(isoMatch[2], 10);
    m = parseInt(isoMatch[3], 10);
    sec = parseInt(isoMatch[4] ?? "0", 10);
  }

  if (!date) {
    const dmySlash = s.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})(?:\s+(\d{2}):(\d{2})(?::(\d{2}))?)?/);
    if (dmySlash) {
      date = `${dmySlash[3]}-${dmySlash[2].padStart(2, "0")}-${dmySlash[1].padStart(2, "0")}`;
      h = parseInt(dmySlash[4] ?? "0", 10);
      m = parseInt(dmySlash[5] ?? "0", 10);
      sec = parseInt(dmySlash[6] ?? "0", 10);
    }
  }

  if (!date) {
    const dmyDash = s.match(/^(\d{1,2})-(\d{1,2})-(\d{4})(?:\s+(\d{2}):(\d{2})(?::(\d{2}))?)?/);
    if (dmyDash) {
      date = `${dmyDash[3]}-${dmyDash[2].padStart(2, "0")}-${dmyDash[1].padStart(2, "0")}`;
      h = parseInt(dmyDash[4] ?? "0", 10);
      m = parseInt(dmyDash[5] ?? "0", 10);
      sec = parseInt(dmyDash[6] ?? "0", 10);
    }
  }

  if (!date) return null;
  return { date, secs: h * 3600 + m * 60 + sec };
}

/**
 * Calculates MCD, TB and/or TS from raw sub-daily dendrometry readings using the
 * GlobalSense algorithm (splent_feature_data_processing/services.py).
 *
 * Days or windows where the required time-of-day data is absent are skipped
 * rather than approximated. The returned `warnings` array describes each
 * category of skipped data so the caller can surface it in the UI.
 */
export function calculateDendroParams(
  rows: CsvPreviewRow[],
  timestampCol: string,
  dataCol: string,
  selected: DendroSelection,
): DendroParams {
  const warnings: string[] = [];

  if (!selected.mcd && !selected.tb && !selected.ts) {
    return { warnings };
  }

  // ── 1. Build daily buckets ───────────────────────────────────────────────
  const dailyBuckets = new Map<string, TimedValue[]>();
  let unparsedRows = 0;

  for (const row of rows) {
    const ts = parseTimestamp(String(row[timestampCol] ?? ""));
    if (!ts) { unparsedRows++; continue; }
    const val = parseFloat(String(row[dataCol] ?? "").replace(",", "."));
    if (isNaN(val)) continue;

    if (!dailyBuckets.has(ts.date)) dailyBuckets.set(ts.date, []);
    dailyBuckets.get(ts.date)!.push({ secs: ts.secs, value: val });
  }

  if (unparsedRows > 0) {
    warnings.push(`${unparsedRows} fila(s) ignoradas por timestamp no reconocido.`);
  }

  if (dailyBuckets.size === 0) {
    warnings.push("No se encontraron datos válidos en el CSV.");
    return { warnings };
  }

  for (const readings of dailyBuckets.values()) {
    readings.sort((a, b) => a.secs - b.secs);
  }

  // ── 2. Check sub-daily resolution (needed for MCD) ───────────────────────
  // A day is "sub-daily" if it has readings in the 09:00–22:59 window.
  // If no day qualifies, MCD cannot be computed at all.
  if (selected.mcd) {
    const daysWithWindow = [...dailyBuckets.values()].filter(
      (readings) => readings.some((r) => r.secs >= MCD_MIN_START_SECS && r.secs <= MCD_MIN_END_SECS),
    ).length;

    if (daysWithWindow === 0) {
      warnings.push(
        "MCD no calculable: el CSV no contiene lecturas entre las 09:00 y las 23:00. " +
        "Se necesitan datos sub-diarios con marca temporal horaria para calcular MCD.",
      );
      selected = { ...selected, mcd: false };
    }
  }

  // ── 3. MCD ───────────────────────────────────────────────────────────────
  const mcdResult = new Map<string, number>();
  const maxBefore12 = new Map<string, number>();
  let mcdSkipped = 0;

  for (const [date, readings] of dailyBuckets) {
    const beforeMaxVals = readings
      .filter((r) => r.secs <= MCD_MAX_CUTOFF_SECS)
      .map((r) => r.value);

    const windowMinVals = readings
      .filter((r) => r.secs >= MCD_MIN_START_SECS && r.secs <= MCD_MIN_END_SECS)
      .map((r) => r.value);

    // maxBefore12 is used for TCT even when MCD itself is not selected/possible
    if (beforeMaxVals.length > 0) {
      maxBefore12.set(date, Math.max(...beforeMaxVals));
    }
    // If no reading before 12:00 exists (edge case), skip this day for TCT too
    // — do NOT fall back to midnight or all-day values, as that distorts TCT.

    if (selected.mcd) {
      if (beforeMaxVals.length > 0 && windowMinVals.length > 0) {
        mcdResult.set(date, Math.max(Math.max(...beforeMaxVals) - Math.min(...windowMinVals), 0));
      } else {
        mcdSkipped++;
      }
    }
  }

  if (selected.mcd && mcdSkipped > 0) {
    warnings.push(
      `MCD: ${mcdSkipped} día(s) omitidos por falta de lecturas en las ventanas horarias requeridas ` +
      "(antes de las 12:00 y/o entre las 09:00–23:00).",
    );
  }

  // ── 4. TCT (required for TB/TS) ──────────────────────────────────────────
  const tctResult = new Map<string, number>();
  let tctGaps = 0;

  if (selected.tb || selected.ts) {
    if (maxBefore12.size === 0) {
      warnings.push(
        "TB/TS no calculables: ningún día tiene lecturas antes de las 12:00, " +
        "necesarias para calcular el TCT.",
      );
      return {
        mcd: mcdResult.size > 0 ? mcdResult : undefined,
        warnings,
      };
    }

    const orderedDays = [...maxBefore12.keys()].sort();
    const msPerDay = 86400000;

    for (let i = 0; i < orderedDays.length - 1; i++) {
      const dayN = orderedDays[i];
      const dayN1 = orderedDays[i + 1];
      const gap = Math.round((new Date(dayN1).getTime() - new Date(dayN).getTime()) / msPerDay);
      if (gap === 1) {
        const diff = maxBefore12.get(dayN1)! - maxBefore12.get(dayN)!;
        tctResult.set(dayN1, parseFloat(diff.toFixed(2)));
      } else {
        tctGaps++;
      }
    }

    if (tctGaps > 0) {
      warnings.push(
        `TCT: ${tctGaps} transición(es) entre días no consecutivos omitidas. ` +
        "Los huecos interrumpen la ventana deslizante de 7 días para TB/TS.",
      );
    }
  }

  // ── 5. TB and TS: 7-day rolling window ───────────────────────────────────
  const tbResult = new Map<string, number>();
  const tsResult = new Map<string, number>();

  if (selected.tb || selected.ts) {
    const tctDays = [...tctResult.keys()].sort();

    if (tctDays.length < TCT_WEEK_DAYS) {
      warnings.push(
        `TB/TS no calculables: se necesitan al menos ${TCT_WEEK_DAYS} días consecutivos con TCT ` +
        `(solo hay ${tctDays.length} disponibles).`,
      );
    } else {
      let windowsSkipped = 0;
      for (let i = 0; i < tctDays.length; i++) {
        const windowStart = Math.max(0, i - (TCT_WEEK_DAYS - 1));
        const windowDays = tctDays.slice(windowStart, i + 1);

        // Ensure all 7 days in the window are truly consecutive (no hidden gaps)
        let windowIsConsecutive = windowDays.length === TCT_WEEK_DAYS;
        if (windowIsConsecutive) {
          for (let j = 0; j < windowDays.length - 1; j++) {
            const gap = Math.round(
              (new Date(windowDays[j + 1]).getTime() - new Date(windowDays[j]).getTime()) / 86400000,
            );
            if (gap !== 1) { windowIsConsecutive = false; break; }
          }
        }

        if (!windowIsConsecutive) { windowsSkipped++; continue; }

        const window = windowDays.map((d) => tctResult.get(d)!);
        const day = tctDays[i];

        if (selected.tb) {
          const buenos = window.filter((d) => d >= TCT_GOOD_MIN && d <= TCT_GOOD_MAX).length;
          tbResult.set(day, parseFloat(((buenos / TCT_WEEK_DAYS) * 100).toFixed(4)));
        }
        if (selected.ts) {
          const severos = window.filter((d) => d < TCT_SEVERE_MAX).length;
          tsResult.set(day, parseFloat(((severos / TCT_WEEK_DAYS) * 100).toFixed(4)));
        }
      }

      if (windowsSkipped > 0) {
        warnings.push(
          `TB/TS: ${windowsSkipped} día(s) omitidos porque su ventana de 7 días contiene huecos.`,
        );
      }

      if (tbResult.size === 0 && tsResult.size === 0) {
        warnings.push(
          "TB/TS: no se produjo ningún resultado. Verifica que el CSV contiene al menos " +
          `${TCT_WEEK_DAYS + 1} días consecutivos con lecturas válidas antes de las 12:00.`,
        );
      }
    }
  }

  return {
    mcd: selected.mcd && mcdResult.size > 0 ? mcdResult : undefined,
    tb: selected.tb && tbResult.size > 0 ? tbResult : undefined,
    ts: selected.ts && tsResult.size > 0 ? tsResult : undefined,
    warnings,
  };
}
