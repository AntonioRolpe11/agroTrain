import { describe, it, expect } from "vitest";
import { parseCsvFile, parseCsvFileGeneric } from "@/lib/csvDataset";

function makeFile(content: string, name = "test.csv"): File {
  return new File([content], name, { type: "text/csv" });
}

describe("parseCsvFileGeneric", () => {
  it("reports empty file", async () => {
    const result = await parseCsvFileGeneric(makeFile(""));
    expect(result.errors.length).toBeGreaterThan(0);
  });

  it("parses comma-delimited file", async () => {
    const result = await parseCsvFileGeneric(makeFile("a,b\n1,2\n3,4"));
    expect(result.delimiter).toBe(",");
    expect(result.headers).toEqual(["a", "b"]);
    expect(result.rowCount).toBe(2);
  });

  it("parses semicolon-delimited file", async () => {
    const result = await parseCsvFileGeneric(makeFile("a;b\n1;2"));
    expect(result.delimiter).toBe(";");
  });

  it("warns about duplicate headers", async () => {
    const result = await parseCsvFileGeneric(makeFile("a,a,b\n1,2,3"));
    expect(result.warnings.some((w) => w.includes("repetidas"))).toBe(true);
  });

  it("strips UTF-8 BOM", async () => {
    const result = await parseCsvFileGeneric(makeFile("﻿date,value\n2026-01-01,1"));
    expect(result.headers[0]).toBe("date");
  });
});

describe("parseCsvFile (typed sensors)", () => {
  const aliases = { date: "date", mcd: "MCD", tmax: "tmax" };
  const dataCols = ["MCD", "tmax"];

  it("returns errors on empty file", async () => {
    const result = await parseCsvFile(makeFile(""), "sensors", aliases, dataCols, ["MCD"]);
    expect(result.errors).toContain("El archivo CSV está vacío.");
  });

  it("reports missing required columns", async () => {
    const result = await parseCsvFile(
      makeFile("date,tmax\n2026-01-01,25"),
      "sensors",
      aliases,
      dataCols,
      ["MCD"],
    );
    expect(result.missingRequiredColumns).toEqual(["MCD"]);
    expect(result.errors.some((e) => e.includes("Faltan"))).toBe(true);
  });

  it("counts empty values per column", async () => {
    const result = await parseCsvFile(
      makeFile("date,MCD,tmax\n2026-01-01,10,\n2026-01-02,,30"),
      "sensors",
      aliases,
      dataCols,
    );
    expect(result.emptyValueCounts.MCD).toBe(1);
    expect(result.emptyValueCounts.tmax).toBe(1);
    expect(result.rowsWithMissingValues).toBe(2);
  });

  it("returns canonical headers and recognized columns", async () => {
    const result = await parseCsvFile(
      makeFile("Date,MCD,tmax\n2026-01-01,10,25"),
      "sensors",
      aliases,
      dataCols,
    );
    expect(result.canonicalHeaders).toEqual(expect.arrayContaining(["date", "MCD", "tmax"]));
    expect(result.recognizedDataColumns).toEqual(expect.arrayContaining(["MCD", "tmax"]));
  });

  it("rejects telemetry CSV without recognized columns", async () => {
    const result = await parseCsvFile(
      makeFile("foo,bar\n1,2"),
      "telemetry",
      { date: "date", ndvi: "NDVI" },
      ["NDVI"],
    );
    expect(result.errors.some((e) => e.includes("telemetría"))).toBe(true);
  });

  it("warns about unknown headers for telemetry", async () => {
    const result = await parseCsvFile(
      makeFile("date,NDVI,FOO\n2026-01-01,0.5,9"),
      "telemetry",
      { date: "date", ndvi: "NDVI" },
      ["NDVI"],
    );
    expect(result.warnings.some((w) => w.includes("FOO"))).toBe(true);
  });
});
