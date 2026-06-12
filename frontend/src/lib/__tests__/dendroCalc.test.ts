import { describe, it, expect } from "vitest";
import { calculateDendroParams, type DendroSelection } from "@/lib/dendroCalc";

function buildSubDailyRows(days: number, startDate = "2026-01-01"): Array<Record<string, string>> {
  const rows: Array<Record<string, string>> = [];
  const start = new Date(`${startDate}T00:00:00Z`);
  for (let d = 0; d < days; d++) {
    const day = new Date(start.getTime() + d * 86400000);
    const isoDay = day.toISOString().slice(0, 10);
    // 10:00 and 14:00 readings — within the 09:00–23:00 window
    rows.push({ timestamp: `${isoDay} 10:00`, value: String(100 + d) });
    rows.push({ timestamp: `${isoDay} 14:00`, value: String(95 + d) });
  }
  return rows;
}

const TS = "timestamp";
const DC = "value";

describe("calculateDendroParams", () => {
  it("returns nothing when nothing is selected", () => {
    const result = calculateDendroParams([], TS, DC, { mcd: false, tb: false, ts: false } as DendroSelection);
    expect(result.warnings).toEqual([]);
    expect(result.mcd).toBeUndefined();
  });

  it("returns warning when no parsable rows", () => {
    const result = calculateDendroParams(
      [{ timestamp: "nonsense", value: "x" }],
      TS, DC,
      { mcd: true, tb: false, ts: false },
    );
    expect(result.warnings.some((w) => w.includes("ignoradas") || w.includes("válidos"))).toBe(true);
  });

  it("computes MCD when sub-daily window present", () => {
    const rows = buildSubDailyRows(3);
    const result = calculateDendroParams(rows, TS, DC, { mcd: true, tb: false, ts: false });
    expect(result.mcd).toBeDefined();
    expect(result.mcd!.size).toBe(3);
  });

  it("flags MCD non-computable when no 09-23 readings", () => {
    const rows = [
      { timestamp: "2026-01-01 02:00", value: "10" },
      { timestamp: "2026-01-02 03:00", value: "11" },
    ];
    const result = calculateDendroParams(rows, TS, DC, { mcd: true, tb: false, ts: false });
    expect(result.warnings.some((w) => w.includes("MCD no calculable"))).toBe(true);
    expect(result.mcd).toBeUndefined();
  });

  it("computes TB across 7 consecutive days", () => {
    const rows = buildSubDailyRows(10);
    const result = calculateDendroParams(rows, TS, DC, { mcd: false, tb: true, ts: false });
    expect(result.tb).toBeDefined();
    expect(result.tb!.size).toBeGreaterThan(0);
  });

  it("flags TB non-computable when fewer than 7 days", () => {
    const rows = buildSubDailyRows(3);
    const result = calculateDendroParams(rows, TS, DC, { mcd: false, tb: true, ts: false });
    expect(result.warnings.some((w) => w.includes("TB/TS"))).toBe(true);
  });

  it("computes TS when selected", () => {
    const rows = buildSubDailyRows(10);
    const result = calculateDendroParams(rows, TS, DC, { mcd: false, tb: false, ts: true });
    expect(result.ts).toBeDefined();
  });

  it("parses DMY-slash timestamps", () => {
    const rows = [
      { timestamp: "01/04/2026 10:00", value: "100" },
      { timestamp: "01/04/2026 14:00", value: "90" },
    ];
    const result = calculateDendroParams(rows, TS, DC, { mcd: true, tb: false, ts: false });
    expect(result.mcd?.has("2026-04-01")).toBe(true);
  });
});
