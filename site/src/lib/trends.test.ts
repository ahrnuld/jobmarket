import { describe, expect, it } from "vitest";
import { movers, quarters, spanMonths, yearsBefore } from "./model";
import type { MonthInfo } from "./types";

const months: MonthInfo[] = Array.from({ length: 30 }, (_, i) => {
  const d = new Date(Date.UTC(2024, i, 1));
  return { month: d.toISOString().slice(0, 7), partial: false };
});

describe("spans", () => {
  it("takes the last N years of months", () => {
    expect(spanMonths(months, "1y")).toHaveLength(12);
    expect(spanMonths(months, "2y")).toHaveLength(24);
    expect(spanMonths(months, "5y")).toHaveLength(30);
    expect(spanMonths(months, "all")).toHaveLength(30);
  });
  it("computes a cutoff date years back", () => {
    expect(yearsBefore("2026-04-01", 5)).toBe("2021-04-01");
  });
});

describe("movers", () => {
  const idx = spanMonths(months, "1y"); // months 18..29: halves 18-23 and 24-29
  const totals = new Map(idx.map((i) => [i, 100]));
  it("compares shares in the recent half with the earlier half", () => {
    const rows: [number, string, number][] = [
      ...idx.map((i) => [i, "rising", i >= 24 ? 40 : 10] as [number, string, number]),
      ...idx.map((i) => [i, "falling", i >= 24 ? 5 : 30] as [number, string, number]),
      ...idx.map((i) => [i, "rare", 1] as [number, string, number]),
    ];
    const res = movers(rows, totals, idx)!;
    expect(res.rising.map((m) => m.id)).toEqual(["rising"]);
    expect(res.rising[0].change).toBeCloseTo(30);
    expect(res.falling.map((m) => m.id)).toEqual(["falling"]);
    expect(res.recent).toEqual([24, 25, 26, 27, 28, 29]); // "rare" is below the minimum count
  });
  it("needs at least three months per half", () => {
    expect(movers([], new Map([[0, 1]]), [0, 1, 2, 3, 4])).toBeNull();
  });
});

describe("quarters", () => {
  it("groups months into calendar quarters", () => {
    const q = quarters(months, [0, 1, 2, 3]);
    expect(q.map((x) => x.label)).toEqual(["2024Q1", "2024Q2"]);
    expect(q[0].months).toEqual([0, 1, 2]);
  });
});
