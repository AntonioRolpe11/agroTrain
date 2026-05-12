import type { TelemetryPoint } from "@/types/api";
import type { CsvPreviewRow } from "@/lib/csvDataset";

export interface FusedRow {
  [column: string]: string | number | null | boolean;
  _telemetryInterpolated: boolean;
}

export interface FusionResult {
  headers: string[];
  rows: FusedRow[];
  rowCount: number;
  sensorDateRange: [string, string] | null;
  exactMatchCount: number;
  interpolatedCount: number;
  warnings: string[];
}

export interface FusionParams {
  sensorRows: CsvPreviewRow[];
  sensorHeaders: string[];
  telemetryPoints: TelemetryPoint[];
  selectedIndices: string[];
}

function parseSensorDate(timestamp: string): string | null {
  if (!timestamp || timestamp.trim() === "") return null;

  const isoMatch = timestamp.match(/^(\d{4}-\d{2}-\d{2})/);
  if (isoMatch) return isoMatch[1];

  const dmyMatch = timestamp.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})/);
  if (dmyMatch) {
    const day = dmyMatch[1].padStart(2, "0");
    const month = dmyMatch[2].padStart(2, "0");
    return `${dmyMatch[3]}-${month}-${day}`;
  }

  const numeric = Number(timestamp);
  if (!isNaN(numeric) && numeric > 1_000_000_000) {
    return new Date(numeric * 1000).toISOString().slice(0, 10);
  }

  return null;
}

function dateToMs(date: string): number {
  return new Date(date).getTime();
}

interface KnownPoint {
  date: string;
  value: number;
}

function getInterpolatedValue(
  sortedPoints: KnownPoint[],
  targetDate: string,
): { value: number | null; interpolated: boolean } {
  if (sortedPoints.length === 0) return { value: null, interpolated: false };

  const exact = sortedPoints.find((p) => p.date === targetDate);
  if (exact) return { value: exact.value, interpolated: false };

  const target = dateToMs(targetDate);
  let before: KnownPoint | null = null;
  let after: KnownPoint | null = null;

  for (const point of sortedPoints) {
    const t = dateToMs(point.date);
    if (t < target) before = point;
    else if (t > target && after === null) after = point;
  }

  if (before && after) {
    const t0 = dateToMs(before.date);
    const t1 = dateToMs(after.date);
    const ratio = (target - t0) / (t1 - t0);
    const interpolated = before.value + (after.value - before.value) * ratio;
    return { value: Math.round(interpolated * 10_000) / 10_000, interpolated: true };
  }

  // Clamp to nearest boundary: repeat first value before range, last value after range
  if (!before) return { value: sortedPoints[0].value, interpolated: true };
  return { value: sortedPoints[sortedPoints.length - 1].value, interpolated: true };
}

export function getSensorDateRange(
  rows: CsvPreviewRow[],
  headers: string[],
): [string, string] | null {
  const timestampCol = headers.find((h) => h.toLowerCase().trim() === "timestamp");
  if (!timestampCol) return null;

  const dates: string[] = [];
  for (const row of rows) {
    const date = parseSensorDate(row[timestampCol] ?? "");
    if (date) dates.push(date);
  }

  if (dates.length === 0) return null;
  dates.sort();
  return [dates[0], dates[dates.length - 1]];
}

export function csvRowsToTelemetryPoints(
  rows: CsvPreviewRow[],
  headers: string[],
  selectedIndices: string[],
): TelemetryPoint[] {
  // Find the raw header name whose alias matches the canonical name
  const findCol = (canonical: string): string | undefined =>
    headers.find((h) => {
      const normalized = h.toLowerCase().trim();
      if (canonical === "date") return normalized === "date";
      return normalized === canonical.toLowerCase();
    });

  const dateCol = findCol("date");
  if (!dateCol) return [];

  // Pre-compute index → raw header mapping once (not per row)
  const indexCols: [string, string][] = selectedIndices
    .map((idx) => [idx, findCol(idx)] as [string, string])
    .filter(([, col]) => col !== undefined);

  return rows.flatMap((row) => {
    // Normalize date to YYYY-MM-DD regardless of source format
    const dateStr = parseSensorDate(row[dateCol] ?? "");
    if (!dateStr) return [];

    const values: Record<string, number> = {};
    for (const [index, col] of indexCols) {
      const v = parseFloat(row[col] ?? "");
      if (!isNaN(v)) values[index] = v;
    }

    return [{ date: dateStr, values, cloudCover: null } satisfies TelemetryPoint];
  });
}

export function fuseSensorAndTelemetry(params: FusionParams): FusionResult {
  const { sensorRows, sensorHeaders, telemetryPoints, selectedIndices } = params;
  const warnings: string[] = [];

  const timestampCol = sensorHeaders.find((h) => h.toLowerCase().trim() === "timestamp") ?? null;
  if (!timestampCol) {
    return {
      headers: ["date", ...sensorHeaders, ...selectedIndices],
      rows: [],
      rowCount: 0,
      sensorDateRange: null,
      exactMatchCount: 0,
      interpolatedCount: 0,
      warnings: ["No se encontró la columna timestamp en los datos de sensores."],
    };
  }

  const dataHeaders = sensorHeaders.filter((h) => h !== timestampCol);

  // Group sensor rows by date and accumulate values for averaging
  const dateAccumulator = new Map<string, Record<string, number[]>>();

  for (const row of sensorRows) {
    const date = parseSensorDate(row[timestampCol] ?? "");
    if (!date) continue;

    if (!dateAccumulator.has(date)) {
      dateAccumulator.set(date, Object.fromEntries(dataHeaders.map((h) => [h, [] as number[]])));
    }
    const acc = dateAccumulator.get(date)!;

    for (const col of dataHeaders) {
      const v = parseFloat(row[col] ?? "");
      if (!isNaN(v)) acc[col].push(v);
    }
  }

  if (dateAccumulator.size === 0) {
    warnings.push("No se pudieron parsear fechas válidas del CSV de sensores.");
    return {
      headers: ["date", ...dataHeaders, ...selectedIndices],
      rows: [],
      rowCount: 0,
      sensorDateRange: null,
      exactMatchCount: 0,
      interpolatedCount: 0,
      warnings,
    };
  }

  const sortedDates = Array.from(dateAccumulator.keys()).sort();
  const sensorDateRange: [string, string] = [sortedDates[0], sortedDates[sortedDates.length - 1]];

  if (selectedIndices.length > 0 && telemetryPoints.length === 0) {
    warnings.push("La fuente de telemetría no contiene ningún punto; las columnas de índices quedarán vacías.");
  }

  // Build sorted known-point arrays per index
  const indexPoints: Record<string, KnownPoint[]> = {};

  for (const point of telemetryPoints) {
    for (const index of selectedIndices) {
      const v = point.values[index];
      if (v != null) {
        indexPoints[index] ??= [];
        indexPoints[index].push({ date: point.date, value: v });
      }
    }
  }

  for (const pts of Object.values(indexPoints)) {
    pts.sort((a, b) => a.date.localeCompare(b.date));
  }

  // Build one fused row per day
  const fusedRows: FusedRow[] = [];
  let exactMatchCount = 0;
  let interpolatedCount = 0;

  for (const date of sortedDates) {
    const acc = dateAccumulator.get(date)!;
    const fusedRow: FusedRow = { date, _telemetryInterpolated: false };

    // Daily mean for each sensor column
    for (const col of dataHeaders) {
      const vals = acc[col];
      fusedRow[col] =
        vals.length > 0
          ? Math.round((vals.reduce((s, v) => s + v, 0) / vals.length) * 10_000) / 10_000
          : null;
    }

    // Telemetry indices (exact match, linear interpolation, or edge clamp)
    let rowInterpolated = false;
    let rowExact = false;

    for (const index of selectedIndices) {
      const pts = indexPoints[index] ?? [];
      const { value, interpolated } = getInterpolatedValue(pts, date);
      fusedRow[index] = value;
      if (interpolated) rowInterpolated = true;
      else if (value !== null) rowExact = true;
    }

    if (rowInterpolated) {
      fusedRow._telemetryInterpolated = true;
      interpolatedCount++;
    } else if (rowExact) {
      exactMatchCount++;
    }

    fusedRows.push(fusedRow);
  }

  return {
    headers: ["date", ...dataHeaders, ...selectedIndices],
    rows: fusedRows,
    rowCount: fusedRows.length,
    sensorDateRange,
    exactMatchCount,
    interpolatedCount,
    warnings,
  };
}

export function fusionResultToCsv(result: FusionResult, delimiter: "," | ";" = ";"): string {
  const displayHeaders = result.headers.filter((h) => !h.startsWith("_"));
  const lines: string[] = [displayHeaders.join(delimiter)];

  for (const row of result.rows) {
    const values = displayHeaders.map((h) => {
      const v = row[h];
      if (v === null || v === undefined || v === "") return "";
      return String(v);
    });
    lines.push(values.join(delimiter));
  }

  return lines.join("\n");
}
