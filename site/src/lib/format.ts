import type { Lang } from "./types";

const locale = (lang: Lang) => (lang === "nl" ? "nl-NL" : "en-GB");

export const fmtInt = (lang: Lang, n: number) =>
  new Intl.NumberFormat(locale(lang), { maximumFractionDigits: 0 }).format(n);

export const fmtPct = (lang: Lang, share: number | null, digits = 0) =>
  share === null
    ? "–"
    : new Intl.NumberFormat(locale(lang), { style: "percent", maximumFractionDigits: digits }).format(share);

/** Signed percentage points, e.g. "+2,4 pp". */
export const fmtPp = (lang: Lang, pp: number | null) => {
  if (pp === null) return "–";
  const s = new Intl.NumberFormat(locale(lang), { maximumFractionDigits: 1, minimumFractionDigits: 1,
                                                   signDisplay: "exceptZero" }).format(pp);
  return `${s} ${lang === "nl" ? "procentpunt" : "pp"}`;
};

export const fmtEuro = (lang: Lang, n: number | null) =>
  n === null
    ? "–"
    : new Intl.NumberFormat(locale(lang), { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(n);

/** Round to the nearest 50 for display; salary quantiles come from 2,500-euro annual buckets. */
export const roundTo = (n: number, step: number) => Math.round(n / step) * step;

export const fmtDate = (lang: Lang, iso: string | null) => {
  if (!iso) return "–";
  const d = new Date(iso.length === 10 ? `${iso}T12:00:00Z` : iso);
  return new Intl.DateTimeFormat(locale(lang), { day: "numeric", month: "short", year: "numeric",
                                                  timeZone: "Europe/Amsterdam" }).format(d);
};

export const fmtMonth = (lang: Lang, ym: string, style: "short" | "long" = "short") => {
  const d = new Date(`${ym}-15T12:00:00Z`);
  return new Intl.DateTimeFormat(locale(lang), { month: style, year: "numeric", timeZone: "UTC" }).format(d);
};

/** "2025Q3" -> "Q3 2025" / "K3 2025"; "2024" stays; "2025-2030" stays. */
export const fmtPeriod = (lang: Lang, period: string) => {
  const m = /^(\d{4})Q([1-4])$/.exec(period);
  if (m) return `${lang === "nl" ? "K" : "Q"}${m[2]} ${m[1]}`;
  return period;
};

export const escapeHtml = (s: string) =>
  s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;")
   .replace(/'/g, "&#39;");
