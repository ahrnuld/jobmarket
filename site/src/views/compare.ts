// Programme comparison (FR-09): two programmes side by side, in one region and period.
// Each programme keeps its own color on every chart (dataviz: color follows the entity).

import { barList, lineChart, ranges, table } from "../lib/charts";
import { escapeHtml as esc, fmtEuro, fmtInt, fmtPct } from "../lib/format";
import { countVacancies, isIndicative, monthly, salaryStats, share, topFamilies, topSkills, window } from "../lib/model";
import type { GeoData, Stats } from "../lib/types";
import { monthlyFromAnnual } from "./blocks";
import {
  card, type Ctx, familyName, type FilterState, geoName, indicativeBadge, monthLabel, PROGRAMME_COLOR,
  programmeName, provenance, seniorityName, skillLabel, tile, vacancyUpdated, windowLabel,
} from "./common";
import { graduateCard } from "./stats";
import { completeMonths } from "./trends";

export const COMPARE_KINDS: (keyof GeoData)[] = ["vacancies", "skills", "families", "salaries"];

export function renderCompare(ctx: Ctx, state: FilterState, data: Record<string, GeoData>, stats?: Stats): string {
  const { lang, tr, meta } = ctx;
  const d = data[state.geo];
  const win = window(meta.vacancies.months, state.period);
  const progs = [state.a, state.b];
  const min = meta.min_sample_size;
  const head = (p: string) => `<h3 class="compare-head" style="--c:var(${PROGRAMME_COLOR[p]})">${esc(programmeName(ctx, p))}</h3>`;
  const ict = countVacancies(d.vacancies, win.months);
  const out: string[] = [];

  if (state.a === state.b) {
    out.push(`<p class="empty">${lang === "nl" ? "Kies twee verschillende opleidingen." : "Choose two different programmes."}</p>`);
  }

  // Volume and entry level
  const cols = progs.map((p) => {
    const n = countVacancies(d.vacancies, win.months, p);
    const prev = win.previous ? countVacancies(d.vacancies, win.previous, p) : null;
    const entry = countVacancies(d.vacancies, win.months, p, "entry");
    const change = prev ? `${n >= prev ? "+" : ""}${fmtPct(lang, (n - prev) / prev)} ${tr.chart.vsPrevious}` : tr.chart.noPrevious;
    return `<div>${head(p)}<div class="tiles">`
      + tile({ label: lang === "nl" ? "Vacatures" : "Vacancies", value: fmtInt(lang, n),
               sub: `${fmtPct(lang, share(n, ict))} ${lang === "nl" ? "van alle ICT-vacatures" : "of all ICT vacancies"} · ${change}`,
               badges: isIndicative(n, min) ? [indicativeBadge(ctx)] : [] })
      + tile({ label: tr.seniority.entry, value: fmtPct(lang, share(entry, n)), sub: `${fmtInt(lang, entry)} ${tr.chart.vacancies}` })
      + `</div></div>`;
  });
  out.push(card(ctx, { headingLevel: 2,
    title: lang === "nl" ? "Hoeveel vacatures?" : "How many vacancies?",
    subtitle: `${geoName(ctx, state.geo)} · ${windowLabel(ctx, win)}`,
    body: `<div class="grid-2 compare">${cols.join("")}</div>`,
    provenance: provenance(ctx, { sourceIds: [meta.vacancy_source], updated: vacancyUpdated(ctx), n: ict }),
  }));

  // Trend: both programmes on one axis (same unit), complete months only
  const full = completeMonths(ctx, win.months);
  const labels = full.map((mi) => monthLabel(ctx, mi));
  const series = progs.map((p) => {
    const m = monthly(d.vacancies, full, p);
    return { id: p, label: programmeName(ctx, p), colorVar: PROGRAMME_COLOR[p], values: full.map((mi) => m.get(mi) ?? 0) };
  });
  if (full.length > 1) {
    out.push(card(ctx, { headingLevel: 2,
      title: lang === "nl" ? "Vacatures per maand" : "Vacancies per month",
      subtitle: lang === "nl" ? "Alleen complete maanden." : "Complete months only.",
      body: lineChart(labels, series, lang === "nl" ? "Vacatures per maand per opleiding" : "Vacancies per month per programme",
                      (v) => fmtInt(lang, v), (v) => fmtInt(lang, v)),
      provenance: provenance(ctx, { sourceIds: [meta.vacancy_source], updated: vacancyUpdated(ctx), n: ict }),
      table: table(tr.chart.month, [tr.chart.month, ...series.map((s) => s.label)],
                   labels.map((l, k) => [l, ...series.map((s) => fmtInt(lang, s.values[k]))])),
    }));
  }

  // Skills: top 10 each, skills in both lists marked
  const tops = progs.map((p) => topSkills(d.skills, d.vacancies, win, p, "all", 10));
  const shared = new Set(tops[0].items.map((s) => s.id).filter((id) => tops[1].items.some((s) => s.id === id)));
  const skillCols = progs.map((p, k) => `<div>${head(p)}${barList(tops[k].items.map((s) => ({
    label: `${skillLabel(ctx, s.id)}${shared.has(s.id) ? " ●" : ""}`,
    value: s.share, valueText: fmtPct(lang, s.share),
    tip: `${skillLabel(ctx, s.id)}: ${fmtPct(lang, s.share)} (${fmtInt(lang, s.n)})${shared.has(s.id) ? (lang === "nl" ? " · in beide top 10" : " · in both top 10s") : ""}`,
    colorVar: PROGRAMME_COLOR[p], muted: isIndicative(tops[k].total, min),
  })), programmeName(ctx, p), tr.chart.noData)}</div>`);
  out.push(card(ctx, { headingLevel: 2,
    title: lang === "nl" ? "Top 10 skills" : "Top 10 skills",
    subtitle: lang === "nl"
      ? "Aandeel vacatures dat de skill noemt. ● = staat in beide lijsten."
      : "Share of vacancies mentioning the skill. ● = in both lists.",
    body: `<div class="grid-2 compare">${skillCols.join("")}</div>`,
    provenance: provenance(ctx, { sourceIds: [meta.vacancy_source, "esco"], updated: vacancyUpdated(ctx), n: tops[0].total + tops[1].total }),
    table: table("Skills", [lang === "nl" ? "Plaats" : "Rank", ...progs.map((p) => programmeName(ctx, p))],
      Array.from({ length: 10 }, (_, i) => [String(i + 1), ...tops.map((t) => (t.items[i] ? `${skillLabel(ctx, t.items[i].id)} (${fmtPct(lang, t.items[i].share)})` : "–"))])),
    badges: tops.some((t) => isIndicative(t.total, min)) ? [indicativeBadge(ctx)] : [],
  }));

  // Salaries: one shared scale so the two programmes compare directly
  const rows = progs.flatMap((p) => (["entry", "all"] as const).map((lvl) => {
    const s = salaryStats(d.salaries, win.months, p, lvl);
    return { p, lvl, s };
  })).filter((r) => r.s.n > 0);
  out.push(card(ctx, { headingLevel: 2,
    title: lang === "nl" ? "Salaris in vacatures (bruto per maand)" : "Salary in vacancies (gross per month)",
    subtitle: lang === "nl" ? "Balk: middelste helft; streep: mediaan." : "Bar: middle half; mark: median.",
    body: ranges(rows.map(({ p, lvl, s }) => ({
      label: `${programmeName(ctx, p)} · ${seniorityName(ctx, lvl)} (n=${s.n})`,
      p25: monthlyFromAnnual(s.p25!), median: monthlyFromAnnual(s.median!), p75: monthlyFromAnnual(s.p75!),
      tip: `${programmeName(ctx, p)}, ${seniorityName(ctx, lvl)}: ${fmtEuro(lang, monthlyFromAnnual(s.median!))} (n=${s.n})`,
      colorVar: PROGRAMME_COLOR[p], muted: isIndicative(s.n, min),
    })), lang === "nl" ? "Salarisbereik" : "Salary range", tr.chart.noData, (v) => fmtEuro(lang, v)),
    provenance: provenance(ctx, { sourceIds: [meta.vacancy_source], updated: vacancyUpdated(ctx),
                                  n: rows.filter((r) => r.lvl === "all").reduce((t, r) => t + r.s.n, 0),
                                  unit: lang === "nl" ? "vacatures met salaris" : "vacancies with a salary" }),
    table: table(lang === "nl" ? "Salaris" : "Salary", ["", "n", lang === "nl" ? "Mediaan" : "Median"],
      rows.map(({ p, lvl, s }) => [`${programmeName(ctx, p)} · ${seniorityName(ctx, lvl)}`, fmtInt(lang, s.n), fmtEuro(lang, monthlyFromAnnual(s.median!))])),
    badges: rows.some((r) => isIndicative(r.s.n, min)) ? [indicativeBadge(ctx)] : [],
  }));

  // Roles
  const roleCols = progs.map((p) => `<div>${head(p)}${barList(topFamilies(d.families, win.months, p, 6).map((f) => ({
    label: familyName(ctx, f.id), value: f.n, valueText: fmtInt(lang, f.n),
    tip: `${familyName(ctx, f.id)}: ${fmtInt(lang, f.n)}`, colorVar: PROGRAMME_COLOR[p],
  })), programmeName(ctx, p), tr.chart.noData)}</div>`);
  out.push(card(ctx, { headingLevel: 2,
    title: lang === "nl" ? "Soorten functies" : "Types of role",
    body: `<div class="grid-2 compare">${roleCols.join("")}</div>`,
    provenance: provenance(ctx, { sourceIds: [meta.vacancy_source], updated: vacancyUpdated(ctx) }),
  }));

  if (stats) out.push(graduateCard(ctx, stats, progs));
  return out.join("");
}
