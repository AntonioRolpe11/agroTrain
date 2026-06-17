/// <reference types="cypress" />

/**
 * Deterministic CSV generators for the e2e suite.
 *
 * No RNG: every generator is a pure function of its arguments so specs are
 * reproducible run-to-run. The shapes mirror what the real app parsers expect
 * (dendroCalc.ts, sensorMerger.ts, csvDataset.ts), so uploading these through
 * the UI exercises the same code paths a user would hit with real sensor files.
 */

function isoFrom(startISO: string, dayIndex: number): string {
  const d = new Date(`${startISO}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + dayIndex);
  return d.toISOString().slice(0, 10);
}

/**
 * Raw sub-daily dendrometer CSV that `dendroCalc.ts` turns into
 * MCD / TasaBuenos / TasaSeveros. Emits 4 readings/day (08,10,14,18h) over
 * `days` consecutive days so:
 *   - there are readings before 12:00 (needed for the TCT morning max), and
 *   - readings inside the 09:00–23:00 window (needed for MCD).
 * The morning max oscillates across the "buenos" band edge, giving the derived
 * TasaBuenos series real variance (a constant target would yield NaN R²).
 * Columns: `timestamp;valor`.
 */
export function buildDendrometerCsv(days = 80, startISO = "2023-01-01"): string {
  const lines = ["timestamp;valor"];
  let base = 1000;
  for (let i = 0; i < days; i++) {
    const date = isoFrom(startISO, i);
    const delta = 50 + 60 * Math.sin(i / 4); // morning-max growth, ~ -10..110 μm
    base += delta;
    const readings: Array<[string, number]> = [
      ["08:00:00", base - 5],
      ["10:00:00", base], // morning max → drives TCT (and thus TasaBuenos)
      ["14:00:00", base - 40], // midday contraction → drives MCD
      ["18:00:00", base - 15],
    ];
    for (const [hms, val] of readings) {
      lines.push(`${date} ${hms};${val.toFixed(2)}`);
    }
  }
  return lines.join("\n");
}

/** Simple daily sensor CSV (`fecha;valor`) for generic sensors (humedad, dpv…). */
export function buildDailySensorCsv(
  days = 80,
  startISO = "2023-01-01",
  opts: { base?: number; amp?: number } = {},
): string {
  const base = opts.base ?? 20;
  const amp = opts.amp ?? 5;
  const lines = ["fecha;valor"];
  for (let i = 0; i < days; i++) {
    const v = base + amp * Math.sin(i / 6);
    lines.push(`${isoFrom(startISO, i)};${v.toFixed(3)}`);
  }
  return lines.join("\n");
}

/** Telemetry CSV (`date;<INDEX>…`) with daily index values in [0,1]. */
export function buildTelemetryCsv(indices: string[], days = 80, startISO = "2023-01-01"): string {
  const lines = [["date", ...indices].join(";")];
  for (let i = 0; i < days; i++) {
    const cells = [isoFrom(startISO, i)];
    indices.forEach((_, k) => cells.push((0.4 + 0.2 * Math.sin((i + k) / 7)).toFixed(4)));
    lines.push(cells.join(";"));
  }
  return lines.join("\n");
}

/**
 * Pre-fused CSV (`date;TasaBuenos`) for the API-level training/prediction
 * helpers (cy.trainModelViaApi). Smooth seasonal signal + mild deterministic
 * ripple so the target is non-degenerate.
 */
export function buildFusedCsv(rows = 180, startISO = "2022-01-01"): string {
  const lines = ["date;TasaBuenos"];
  for (let i = 0; i < rows; i++) {
    const v = 0.55 + 0.2 * Math.sin(i / 9) + 0.03 * Math.cos(i / 3);
    lines.push(`${isoFrom(startISO, i)};${v.toFixed(4)}`);
  }
  return lines.join("\n");
}
