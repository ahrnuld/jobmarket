// Pure calculations over the published aggregates. Used at build time (static HTML) and in the
// browser (filters), so both always show the same numbers.

import type { FamilyRow, MonthInfo, SalaryRow, SkillRow, TitleRow, VacancyRow } from "./types";

export type Period = "3m" | "6m" | "12m" | "all";
export const PERIODS: Period[] = ["3m", "6m", "12m", "all"];
export const DEFAULT_PERIOD: Period = "12m"; // FR-01

export const SENIORITIES = ["all", "entry", "internship", "junior", "medior", "senior", "unknown"] as const;
export type Seniority = (typeof SENIORITIES)[number];

export const SALARY_BUCKET = 2500;

export interface Window {
  months: number[]; // indices into meta months
  previous: number[] | null; // the equally long window just before, if fully available
  partial: boolean; // window contains a partial month
}

/** The last N months (or all), plus the preceding window of the same length for comparisons. */
export function window(months: MonthInfo[], period: Period): Window {
  const all = months.map((_, i) => i);
  const size = period === "all" ? all.length : Math.min(Number(period.replace("m", "")), all.length);
  const current = all.slice(all.length - size);
  const prevStart = all.length - 2 * size;
  const previous = period !== "all" && prevStart >= 0 ? all.slice(prevStart, all.length - size) : null;
  return { months: current, previous, partial: current.some((i) => months[i]?.partial) };
}

const inSet = (months: number[]) => {
  const s = new Set(months);
  return (mi: number) => s.has(mi);
};

export function countVacancies(rows: VacancyRow[], months: number[], programme = "all",
                               seniority: string = "all"): number {
  const has = inSet(months);
  let total = 0;
  for (const [mi, p, s, n] of rows) if (has(mi) && p === programme && s === seniority) total += n;
  return total;
}

export function monthly(rows: VacancyRow[], months: number[], programme = "all",
                        seniority: string = "all"): Map<number, number> {
  const out = new Map<number, number>(months.map((m) => [m, 0]));
  for (const [mi, p, s, n] of rows) {
    if (out.has(mi) && p === programme && s === seniority) out.set(mi, (out.get(mi) ?? 0) + n);
  }
  return out;
}

export function byProgramme(rows: VacancyRow[], months: number[], programmes: string[],
                            seniority: string = "all"): Record<string, number> {
  return Object.fromEntries(programmes.map((p) => [p, countVacancies(rows, months, p, seniority)]));
}

/** Share with a safe zero denominator. */
export const share = (part: number, whole: number) => (whole > 0 ? part / whole : null);

export interface SkillStat {
  id: string;
  n: number;
  share: number; // of vacancies in the same selection
  previousShare: number | null;
  change: number | null; // percentage points
}

export function topSkills(skillRows: SkillRow[], vacancyRows: VacancyRow[], win: Window,
                          programme = "all", seniority: string = "all", limit = 15) {
  const total = countVacancies(vacancyRows, win.months, programme, seniority);
  const prevTotal = win.previous ? countVacancies(vacancyRows, win.previous, programme, seniority) : 0;
  const cur = new Map<string, number>();
  const prev = new Map<string, number>();
  const hasCur = inSet(win.months);
  const hasPrev = inSet(win.previous ?? []);
  for (const [mi, p, s, skill, n] of skillRows) {
    if (p !== programme || s !== seniority) continue;
    if (hasCur(mi)) cur.set(skill, (cur.get(skill) ?? 0) + n);
    else if (hasPrev(mi)) prev.set(skill, (prev.get(skill) ?? 0) + n);
  }
  const items: SkillStat[] = [...cur.entries()]
    .map(([id, n]) => {
      const sh = total ? n / total : 0;
      const prevShare = prevTotal ? (prev.get(id) ?? 0) / prevTotal : null;
      return { id, n, share: sh, previousShare: prevShare,
               change: prevShare === null ? null : (sh - prevShare) * 100 };
    })
    .sort((a, b) => b.n - a.n || a.id.localeCompare(b.id))
    .slice(0, limit);
  return { total, previousTotal: win.previous ? prevTotal : null, items };
}

export function topFamilies(rows: FamilyRow[], months: number[], programme: string, limit = 8) {
  const has = inSet(months);
  const counts = new Map<string, number>();
  for (const [mi, p, fam, n] of rows) if (has(mi) && p === programme) counts.set(fam, (counts.get(fam) ?? 0) + n);
  return [...counts.entries()].map(([id, n]) => ({ id, n }))
    .sort((a, b) => b.n - a.n || a.id.localeCompare(b.id)).slice(0, limit);
}

export function topTitles(rows: TitleRow[], months: number[], programme: string, limit = 10) {
  const has = inSet(months);
  const counts = new Map<string, number>();
  for (const [mi, p, title, n] of rows) if (has(mi) && p === programme) counts.set(title, (counts.get(title) ?? 0) + n);
  return [...counts.entries()].map(([title, n]) => ({ title, n }))
    .sort((a, b) => b.n - a.n || a.title.localeCompare(b.title)).slice(0, limit);
}

export interface SalaryStat {
  n: number;
  p25: number | null; // annual gross, euro
  median: number | null;
  p75: number | null;
}

/** Quantiles from 2,500-euro buckets, interpolated within the bucket. */
export function salaryStats(rows: SalaryRow[], months: number[], programme = "all",
                            seniority: string = "all"): SalaryStat {
  const has = inSet(months);
  const buckets = new Map<number, number>();
  for (const [mi, p, s, bucket, n] of rows) {
    if (has(mi) && p === programme && s === seniority) buckets.set(bucket, (buckets.get(bucket) ?? 0) + n);
  }
  const sorted = [...buckets.entries()].sort((a, b) => a[0] - b[0]);
  const n = sorted.reduce((t, [, c]) => t + c, 0);
  if (!n) return { n: 0, p25: null, median: null, p75: null };
  const q = (p: number) => {
    const target = p * n;
    let cum = 0;
    for (const [bucket, c] of sorted) {
      if (cum + c >= target) return bucket + ((target - cum) / c) * SALARY_BUCKET;
      cum += c;
    }
    return sorted[sorted.length - 1][0] + SALARY_BUCKET;
  };
  return { n, p25: q(0.25), median: q(0.5), p75: q(0.75) };
}

/** TR-02: figures on fewer records than the minimum are shown as indicative. */
export const isIndicative = (n: number, min: number) => n < min;
