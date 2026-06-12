import type { CsvPreviewRow, GenericCsvDataset } from "@/lib/csvDataset";

export interface SensorFileInput {
  canonicalCol: string;
  dataset: GenericCsvDataset;
  timestampCol: string;
  dataCol: string;
  aggregation?: "avg" | "min" | "max" | "sum";
  /** Pre-computed daily values. When present, bypasses raw row aggregation. */
  precomputedDaily?: Map<string, number>;
}

export interface MergedSensorResult {
  headers: string[];
  rows: CsvPreviewRow[];
  rowCount: number;
  dateRange: [string, string] | null;
  warnings: string[];
}

function parseDate(raw: string): string | null {
  const s = String(raw ?? "").trim();
  if (!s) return null;

  const isoMatch = s.match(/^(\d{4}-\d{2}-\d{2})/);
  if (isoMatch) return isoMatch[1];

  const dmySlash = s.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})/);
  if (dmySlash) return `${dmySlash[3]}-${dmySlash[2].padStart(2, "0")}-${dmySlash[1].padStart(2, "0")}`;

  const dmyDash = s.match(/^(\d{1,2})-(\d{1,2})-(\d{4})/);
  if (dmyDash) return `${dmyDash[3]}-${dmyDash[2].padStart(2, "0")}-${dmyDash[1].padStart(2, "0")}`;

  const numeric = Number(s);
  if (!isNaN(numeric) && numeric > 1_000_000_000) {
    return new Date(numeric * 1000).toISOString().slice(0, 10);
  }

  return null;
}

function resampleToDaily(
  rows: CsvPreviewRow[],
  timestampCol: string,
  dataCol: string,
  aggregation: "avg" | "min" | "max" | "sum" = "avg",
): Map<string, number> {
  const buckets = new Map<string, number[]>();

  for (const row of rows) {
    const date = parseDate(String(row[timestampCol] ?? ""));
    if (!date) continue;
    const val = parseFloat(String(row[dataCol] ?? "").replace(",", "."));
    if (isNaN(val)) continue;
    if (!buckets.has(date)) buckets.set(date, []);
    buckets.get(date)!.push(val);
  }

  const result = new Map<string, number>();
  for (const [date, values] of buckets) {
    let agg: number;
    if (aggregation === "min") agg = Math.min(...values);
    else if (aggregation === "max") agg = Math.max(...values);
    else if (aggregation === "sum") agg = values.reduce((a, b) => a + b, 0);
    else agg = values.reduce((a, b) => a + b, 0) / values.length;
    result.set(date, agg);
  }
  return result;
}

export function mergeSensorFiles(inputs: SensorFileInput[]): MergedSensorResult {
  if (inputs.length === 0) {
    return { headers: ["timestamp"], rows: [], rowCount: 0, dateRange: null, warnings: ["No hay archivos de sensor para fusionar."] };
  }

  const dailyMaps = inputs.map(({ canonicalCol, dataset, timestampCol, dataCol, aggregation, precomputedDaily }) => ({
    canonicalCol,
    daily: precomputedDaily ?? resampleToDaily(dataset.allRows, timestampCol, dataCol, aggregation),
  }));

  const allDates = new Set<string>();
  for (const { daily } of dailyMaps) {
    for (const d of daily.keys()) allDates.add(d);
  }

  if (allDates.size === 0) {
    return { headers: ["timestamp"], rows: [], rowCount: 0, dateRange: null, warnings: ["No se encontraron fechas válidas en los archivos."] };
  }

  const sortedDates = [...allDates].sort();
  const dateRange: [string, string] = [sortedDates[0], sortedDates[sortedDates.length - 1]];
  const canonicalCols = dailyMaps.map(({ canonicalCol }) => canonicalCol);
  const headers = ["timestamp", ...canonicalCols];
  const warnings: string[] = [];

  const rows: CsvPreviewRow[] = sortedDates.map((date) => {
    const row: CsvPreviewRow = { timestamp: date };
    for (const { canonicalCol, daily } of dailyMaps) {
      const val = daily.get(date);
      row[canonicalCol] = val !== undefined ? String(Number(val.toFixed(4))) : "";
    }
    return row;
  });

  for (const { canonicalCol, daily } of dailyMaps) {
    const missing = sortedDates.filter((d) => !daily.has(d)).length;
    if (missing > 0) {
      warnings.push(`${canonicalCol}: ${missing} día(s) sin dato en el rango fusionado.`);
    }
  }

  return { headers, rows, rowCount: rows.length, dateRange, warnings };
}
