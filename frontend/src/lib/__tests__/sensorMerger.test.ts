import { describe, it, expect } from "vitest";
import { mergeSensorFiles, type SensorFileInput } from "@/lib/sensorMerger";

function makeInput(canonical: string, rows: Array<Record<string, string>>): SensorFileInput {
  return {
    canonicalCol: canonical,
    dataset: { allRows: rows, headers: ["date", "value"] } as any,
    timestampCol: "date",
    dataCol: "value",
  };
}

describe("mergeSensorFiles", () => {
  it("returns warnings when input list is empty", () => {
    const result = mergeSensorFiles([]);
    expect(result.rows).toEqual([]);
    expect(result.warnings.length).toBeGreaterThan(0);
  });

  it("aggregates multiple rows per day by average", () => {
    const result = mergeSensorFiles([
      makeInput("temp", [
        { date: "2026-01-01", value: "10" },
        { date: "2026-01-01", value: "20" },
        { date: "2026-01-02", value: "30" },
      ]),
    ]);
    expect(result.rows).toHaveLength(2);
    expect(Number(result.rows[0].temp)).toBe(15);
    expect(Number(result.rows[1].temp)).toBe(30);
  });

  it("respects max aggregation", () => {
    const result = mergeSensorFiles([
      {
        canonicalCol: "tmax",
        dataset: {
          allRows: [
            { date: "2026-01-01", value: "10" },
            { date: "2026-01-01", value: "30" },
          ],
        } as any,
        timestampCol: "date",
        dataCol: "value",
        aggregation: "max",
      },
    ]);
    expect(Number(result.rows[0].tmax)).toBe(30);
  });

  it("supports min aggregation", () => {
    const result = mergeSensorFiles([
      {
        canonicalCol: "tmin",
        dataset: {
          allRows: [
            { date: "2026-01-01", value: "10" },
            { date: "2026-01-01", value: "30" },
          ],
        } as any,
        timestampCol: "date",
        dataCol: "value",
        aggregation: "min",
      },
    ]);
    expect(Number(result.rows[0].tmin)).toBe(10);
  });

  it("warns when a column is missing on some days", () => {
    const result = mergeSensorFiles([
      makeInput("a", [{ date: "2026-01-01", value: "1" }]),
      makeInput("b", [{ date: "2026-01-02", value: "2" }]),
    ]);
    expect(result.rowCount).toBe(2);
    expect(result.warnings.some((w) => w.includes("a"))).toBe(true);
    expect(result.warnings.some((w) => w.includes("b"))).toBe(true);
  });

  it("accepts DMY-slash dates", () => {
    const result = mergeSensorFiles([
      makeInput("x", [
        { date: "01/04/2026", value: "5" },
        { date: "02/04/2026", value: "10" },
      ]),
    ]);
    expect(result.rows).toHaveLength(2);
    expect(result.rows[0].timestamp).toBe("2026-04-01");
  });

  it("uses precomputedDaily when supplied", () => {
    const daily = new Map([
      ["2026-01-01", 100],
      ["2026-01-02", 200],
    ]);
    const result = mergeSensorFiles([
      {
        canonicalCol: "mcd",
        dataset: { allRows: [] } as any,
        timestampCol: "date",
        dataCol: "value",
        precomputedDaily: daily,
      },
    ]);
    expect(result.rows).toHaveLength(2);
    expect(Number(result.rows[0].mcd)).toBe(100);
    expect(Number(result.rows[1].mcd)).toBe(200);
  });
});
