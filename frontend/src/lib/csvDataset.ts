import Papa, { type ParseError, type ParseResult } from "papaparse";

export type CsvKind = "sensors" | "telemetry";
export type CsvPreviewRow = Record<string, string>;

export interface GenericCsvDataset {
  fileName: string;
  delimiter: "," | ";";
  rowCount: number;
  headers: string[];
  allRows: CsvPreviewRow[];
  errors: string[];
  warnings: string[];
}

export interface CsvDataset {
  kind: CsvKind;
  fileName: string;
  delimiter: "," | ";";
  rowCount: number;
  headers: string[];
  canonicalHeaders: string[];
  recognizedDataColumns: string[];
  previewRows: CsvPreviewRow[];
  allRows: CsvPreviewRow[];
  missingRequiredColumns: string[];
  warnings: string[];
  errors: string[];
  emptyValueCounts: Record<string, number>;
  rowsWithMissingValues: number;
}

const PREVIEW_LIMIT = 5;

function normalizeHeader(value: string): string {
  return value.replace(/^\uFEFF/, "").trim().toLowerCase();
}

function cleanCell(value: unknown): string {
  return String(value ?? "").replace(/^\uFEFF/, "").trim();
}

function unique<T>(values: T[]): T[] {
  return [...new Set(values)];
}

function getDuplicateHeaders(headers: string[]): string[] {
  return headers.filter(
    (header, index) =>
      headers.findIndex((candidate) => normalizeHeader(candidate) === normalizeHeader(header)) !== index,
  );
}

function getRowLengthMismatchCount(errors: ParseError[]): number {
  return errors.filter((error) => error.code === "TooFewFields" || error.code === "TooManyFields").length;
}

function getParseErrors(errors: ParseError[]): string[] {
  return errors
    .filter((error) => error.code !== "TooFewFields" && error.code !== "TooManyFields")
    .map((error) => error.message);
}

function parseHeaderRow(text: string): { delimiter: "," | ";"; headers: string[] } {
  const result = Papa.parse<string[]>(text, {
    preview: 1,
    skipEmptyLines: "greedy",
  });
  const delimiter = result.meta.delimiter === ";" ? ";" : ",";
  const headerRow = (result.data[0] ?? []).map((header, index) => {
    const cleaned = cleanCell(header);
    return cleaned.length > 0 ? cleaned : `columna_${index + 1}`;
  });

  return {
    delimiter,
    headers: headerRow,
  };
}

function parseCsvRows(text: string, delimiter: "," | ";"): Promise<ParseResult<Record<string, unknown>>> {
  return new Promise((resolve, reject) => {
    Papa.parse<Record<string, unknown>>(text, {
      header: true,
      delimiter,
      skipEmptyLines: "greedy",
      transformHeader: (header) => cleanCell(header),
      transform: (value) => cleanCell(value),
      complete: resolve,
      error: reject,
    });
  });
}

export async function parseCsvFileGeneric(file: File): Promise<GenericCsvDataset> {
  const text = await file.text();
  const lines = text.split(/\r?\n/).filter((line) => line.trim().length > 0);

  if (lines.length === 0) {
    return { fileName: file.name, delimiter: ",", rowCount: 0, headers: [], allRows: [], errors: ["El archivo CSV está vacío."], warnings: [] };
  }

  const { delimiter, headers: rawHeaders } = parseHeaderRow(text);
  const result = await parseCsvRows(text, delimiter);
  const dataRows = result.data;
  const allRows: CsvPreviewRow[] = [];

  dataRows.forEach((sourceRow) => {
    const row: CsvPreviewRow = {};
    rawHeaders.forEach((header) => {
      row[header] = cleanCell(sourceRow[header]);
    });
    allRows.push(row);
  });

  const errors: string[] = [];
  const warnings: string[] = [];

  if (dataRows.length === 0) errors.push("El archivo no contiene filas de datos.");

  const duplicateHeaders = unique(getDuplicateHeaders(rawHeaders));
  if (duplicateHeaders.length > 0) warnings.push(`Hay columnas repetidas: ${duplicateHeaders.join(", ")}.`);

  const rowLengthMismatchCount = getRowLengthMismatchCount(result.errors);
  if (rowLengthMismatchCount > 0) warnings.push(`${rowLengthMismatchCount} fila(s) con distinto número de columnas.`);

  return { fileName: file.name, delimiter, rowCount: dataRows.length, headers: rawHeaders, allRows, errors, warnings };
}

export async function parseCsvFile(
  file: File,
  kind: CsvKind,
  aliases: Record<string, string>,
  dataColumns: string[],
  requiredColumns: string[] = [],
): Promise<CsvDataset> {
  const text = await file.text();
  const lines = text.split(/\r?\n/).filter((line) => line.trim().length > 0);

  if (lines.length === 0) {
    return {
      kind,
      fileName: file.name,
      delimiter: ",",
      rowCount: 0,
      headers: [],
      canonicalHeaders: [],
      recognizedDataColumns: [],
      previewRows: [],
      allRows: [],
      missingRequiredColumns: requiredColumns,
      warnings: [],
      errors: ["El archivo CSV está vacío."],
      emptyValueCounts: {},
      rowsWithMissingValues: 0,
    };
  }

  const { delimiter, headers: rawHeaders } = parseHeaderRow(text);
  const result = await parseCsvRows(text, delimiter);
  const canonicalHeaders = unique(
    rawHeaders
      .map((header) => aliases[normalizeHeader(header)] ?? null)
      .filter((value): value is string => Boolean(value)),
  );
  const recognizedDataColumns = canonicalHeaders.filter((header) => dataColumns.includes(header));
  const missingRequiredColumns = requiredColumns.filter((header) => !canonicalHeaders.includes(header));
  const duplicateHeaders = unique(getDuplicateHeaders(rawHeaders));
  const unknownHeaders = rawHeaders.filter((header) => !(normalizeHeader(header) in aliases));
  const dataRows = result.data;

  const previewRows: CsvPreviewRow[] = [];
  const allRows: CsvPreviewRow[] = [];
  const emptyValueCounts: Record<string, number> = {};
  let rowsWithMissingValues = 0;

  dataRows.forEach((sourceRow) => {
    const row: CsvPreviewRow = {};
    let rowHasMissingValues = false;

    rawHeaders.forEach((header) => {
      const value = cleanCell(sourceRow[header]);
      row[header] = value;

      const canonicalHeader = aliases[normalizeHeader(header)];
      if (canonicalHeader && dataColumns.includes(canonicalHeader) && value === "") {
        emptyValueCounts[canonicalHeader] = (emptyValueCounts[canonicalHeader] ?? 0) + 1;
        rowHasMissingValues = true;
      }
    });

    if (rowHasMissingValues) {
      rowsWithMissingValues += 1;
    }

    allRows.push(row);

    if (previewRows.length < PREVIEW_LIMIT) {
      previewRows.push(row);
    }
  });

  const warnings: string[] = [];
  const errors: string[] = [];
  const parseErrors = unique(getParseErrors(result.errors));
  const rowLengthMismatchCount = getRowLengthMismatchCount(result.errors);

  if (dataRows.length === 0) {
    errors.push("El archivo no contiene filas de datos.");
  }

  if (missingRequiredColumns.length > 0) {
    errors.push(`Faltan columnas obligatorias: ${missingRequiredColumns.join(", ")}.`);
  }

  if (kind !== "sensors" && recognizedDataColumns.length === 0) {
    errors.push("No se reconocen columnas de telemetría válidas en el CSV.");
  }

  if (duplicateHeaders.length > 0) {
    warnings.push(`Hay columnas repetidas en el CSV: ${duplicateHeaders.join(", ")}.`);
  }

  if (kind !== "sensors" && unknownHeaders.length > 0) {
    warnings.push(`Se ignorarán columnas no reconocidas: ${unknownHeaders.join(", ")}.`);
  }

  if (rowLengthMismatchCount > 0) {
    warnings.push(`Se detectaron ${rowLengthMismatchCount} fila(s) con distinto número de columnas.`);
  }

  parseErrors.forEach((error) => {
    errors.push(`Error al procesar el CSV: ${error}`);
  });

  return {
    kind,
    fileName: file.name,
    delimiter,
    rowCount: dataRows.length,
    headers: rawHeaders,
    canonicalHeaders,
    recognizedDataColumns,
    previewRows,
    allRows,
    missingRequiredColumns,
    warnings,
    errors,
    emptyValueCounts,
    rowsWithMissingValues,
  };
}
