import { describe, expect, it } from "vitest";
import { barList, niceMax } from "./charts";
import { countVacancies, knownLevel, salaryStats, topSkills, window } from "./model";
import type { MonthInfo, SalaryRow, SkillRow, VacancyRow } from "./types";

const months: MonthInfo[] = ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06"]
  .map((month) => ({ month, partial: month === "2026-06" }));

describe("window", () => {
  it("takes the last N months and the preceding window", () => {
    const w = window(months, "3m");
    expect(w.months).toEqual([3, 4, 5]);
    expect(w.previous).toEqual([0, 1, 2]);
    expect(w.partial).toBe(true);
  });
  it("has no previous window when history is too short", () => {
    expect(window(months, "6m").previous).toBeNull();
    expect(window(months, "12m").months).toEqual([0, 1, 2, 3, 4, 5]);
    expect(window(months, "all").previous).toBeNull();
  });
});

const vac: VacancyRow[] = [
  [0, "all", "all", 100], [1, "all", "all", 100], [2, "all", "all", 100],
  [3, "all", "all", 200], [4, "all", "all", 200], [5, "all", "all", 200],
  [3, "informatica", "all", 120], [3, "all", "junior", 20],
];

describe("knownLevel", () => {
  it("counts only the vacancies that state a level", () => {
    const rows: VacancyRow[] = [
      [0, "all", "all", 100], [0, "all", "unknown", 64], [0, "all", "entry", 12],
      [0, "informatica", "all", 50], [0, "informatica", "unknown", 30],
    ];
    expect(knownLevel(rows, [0])).toBe(36);
    expect(knownLevel(rows, [0], "informatica")).toBe(20);
    // The point of it: a share of all vacancies would understate entry level by two thirds.
    expect(12 / knownLevel(rows, [0])).toBeCloseTo(0.333, 2);
  });
});

describe("counts", () => {
  it("sums only the requested programme and level", () => {
    expect(countVacancies(vac, [3, 4, 5])).toBe(600);
    expect(countVacancies(vac, [3], "informatica")).toBe(120);
    expect(countVacancies(vac, [3], "all", "junior")).toBe(20);
  });
});

describe("topSkills", () => {
  const skills: SkillRow[] = [
    [0, "all", "all", "python", 30], [1, "all", "all", "python", 30], [2, "all", "all", "python", 30],
    [3, "all", "all", "python", 100], [4, "all", "all", "python", 100], [5, "all", "all", "python", 100],
    [3, "all", "all", "java", 60],
  ];
  it("computes shares and change in percentage points", () => {
    const r = topSkills(skills, vac, window(months, "3m"));
    expect(r.total).toBe(600);
    expect(r.items[0]).toMatchObject({ id: "python", n: 300, share: 0.5, previousShare: 0.3 });
    expect(r.items[0].change).toBeCloseTo(20);
    expect(r.items[1]).toMatchObject({ id: "java", previousShare: 0 });
  });
  it("gives no change without a previous window", () => {
    expect(topSkills(skills, vac, window(months, "all")).items[0].change).toBeNull();
  });
});

describe("salaryStats", () => {
  it("interpolates quantiles inside 2,500 euro buckets", () => {
    const rows: SalaryRow[] = [[0, "all", "all", 40000, 50], [0, "all", "all", 50000, 50]];
    const s = salaryStats(rows, [0]);
    expect(s.n).toBe(100);
    expect(s.median).toBe(42500); // top of the first bucket
    expect(s.p25).toBe(41250);
    expect(s.p75).toBe(51250);
  });
  it("uses 600-euro buckets below 30,000 (internship allowances)", () => {
    const rows: SalaryRow[] = [[0, "all", "internship", 6000, 10]]; // 500-550 a month
    const s = salaryStats(rows, [0], "all", "internship");
    expect(s.median).toBe(6300); // middle of the 6,000-6,600 bucket = 525 a month
  });
  it("returns nulls without data", () => {
    expect(salaryStats([], [0])).toEqual({ n: 0, p25: null, median: null, p75: null });
  });
});

describe("charts", () => {
  it("escapes labels (labels are data)", () => {
    const html = barList([{ label: "<script>x</script>", value: 1, valueText: "1", tip: '"quoted"' }], "a", "none");
    expect(html).not.toContain("<script>");
    expect(html).toContain("&lt;script&gt;");
    expect(html).toContain("&quot;quoted&quot;");
  });
  it("rounds axis maxima to clean numbers", () => {
    expect(niceMax(26000)).toBe(30000);
    expect(niceMax(348)).toBe(400);
    expect(niceMax(0)).toBe(1);
  });
});
