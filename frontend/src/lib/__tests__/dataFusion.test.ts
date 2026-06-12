import { describe, it, expect } from "vitest";
import {
  csvRowsToTelemetryPoints,
  fuseSensorAndTelemetry,
  fusionResultToCsv,
} from "@/lib/dataFusion";

describe("csvRowsToTelemetryPoints", () => {
  it("parses ISO dates and selected indices", () => {
    const rows = [
      { date: "2026-01-01", NDVI: "0.6", EVI: "0.5" },
      { date: "2026-01-02", NDVI: "0.7", EVI: "0.55" },
    ];
    const points = csvRowsToTelemetryPoints(rows, ["date", "NDVI", "EVI"], ["NDVI"]);
    expect(points).toHaveLength(2);
    expect(points[0].values.NDVI).toBe(0.6);
    expect(points[0].values.EVI).toBeUndefined();
  });

  it("returns empty when no date column", () => {
    expect(csvRowsToTelemetryPoints([{ x: "1" }], ["x"], ["NDVI"])).toEqual([]);
  });

  it("accepts DMY-slash dates", () => {
    const rows = [{ date: "01/04/2026", NDVI: "0.5" }];
    const points = csvRowsToTelemetryPoints(rows, ["date", "NDVI"], ["NDVI"]);
    expect(points[0].date).toBe("2026-04-01");
  });
});

describe("fuseSensorAndTelemetry", () => {
  const sensorHeaders = ["timestamp", "MCD"];
  const sensorRows = [
    { timestamp: "2026-01-01", MCD: "10" },
    { timestamp: "2026-01-03", MCD: "12" },
  ];

  it("matches telemetry exactly when dates align", () => {
    const telemetry = [
      { date: "2026-01-01", values: { NDVI: 0.6 } },
      { date: "2026-01-03", values: { NDVI: 0.7 } },
    ];
    const result = fuseSensorAndTelemetry({
      sensorRows, sensorHeaders, telemetryPoints: telemetry as any, selectedIndices: ["NDVI"],
    });
    expect(result.exactMatchCount).toBe(2);
    expect(result.interpolatedCount).toBe(0);
    expect(result.rows[0].NDVI).toBe(0.6);
  });

  it("interpolates linearly when telemetry is at the boundary", () => {
    const telemetry = [
      { date: "2026-01-01", values: { NDVI: 0.6 } },
      { date: "2026-01-05", values: { NDVI: 1.0 } },
    ];
    const result = fuseSensorAndTelemetry({
      sensorRows: [...sensorRows, { timestamp: "2026-01-03", MCD: "20" }],
      sensorHeaders, telemetryPoints: telemetry as any, selectedIndices: ["NDVI"],
    });
    const middle = result.rows.find((r) => r.date === "2026-01-03");
    expect(middle).toBeDefined();
    expect(Number(middle!.NDVI)).toBeCloseTo(0.8, 1);
    expect(middle!._telemetryInterpolated).toBe(true);
  });

  it("clamps to nearest boundary when target outside range", () => {
    const sensors = [{ timestamp: "2026-01-10", MCD: "5" }];
    const telemetry = [{ date: "2026-01-01", values: { NDVI: 0.4 } }];
    const result = fuseSensorAndTelemetry({
      sensorRows: sensors, sensorHeaders, telemetryPoints: telemetry as any, selectedIndices: ["NDVI"],
    });
    expect(result.rows[0].NDVI).toBe(0.4);
    expect(result.rows[0]._telemetryInterpolated).toBe(true);
  });

  it("returns warning when sensor header lacks timestamp", () => {
    const result = fuseSensorAndTelemetry({
      sensorRows: [], sensorHeaders: ["foo"], telemetryPoints: [], selectedIndices: [],
    });
    expect(result.rowCount).toBe(0);
    expect(result.warnings.length).toBeGreaterThan(0);
  });

  it("warns when telemetry empty but indices requested", () => {
    const result = fuseSensorAndTelemetry({
      sensorRows, sensorHeaders, telemetryPoints: [], selectedIndices: ["NDVI"],
    });
    expect(result.warnings.some((w) => w.includes("telemetría"))).toBe(true);
  });
});

describe("fusionResultToCsv", () => {
  it("emits semicolon-separated rows by default", () => {
    const csv = fusionResultToCsv({
      headers: ["date", "MCD", "_telemetryInterpolated"],
      rows: [{ date: "2026-01-01", MCD: 5, _telemetryInterpolated: false } as any],
      rowCount: 1,
      sensorDateRange: null,
      exactMatchCount: 0,
      interpolatedCount: 0,
      warnings: [],
    });
    const lines = csv.split("\n");
    expect(lines[0]).toBe("date;MCD");
    expect(lines[1]).toBe("2026-01-01;5");
  });

  it("supports comma delimiter", () => {
    const csv = fusionResultToCsv(
      {
        headers: ["date", "MCD"],
        rows: [{ date: "2026-01-01", MCD: 5 } as any],
        rowCount: 1,
        sensorDateRange: null,
        exactMatchCount: 0,
        interpolatedCount: 0,
        warnings: [],
      },
      ",",
    );
    expect(csv).toContain("date,MCD");
  });
});
