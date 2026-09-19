// Trends page (FR-08): rising and declining skills and roles, vacancy volumes and salaries over
// 1, 2, 5 years or the full history, with series start and methodology breaks marked.

import { barList, columns, lineChart, type Marker, table } from "../lib/charts";
import { fmtDate, fmtEuro, fmtInt, fmtMonth, fmtPct, fmtPp, fmtPeriod } from "../lib/format";
import { MIN_HALF_MONTHS, SPAN_YEARS, monthly, movers, quarters, salaryStats, spanMonths, type Mover } from "../lib/model";
import type { GeoData, Stats } from "../lib/types";
import { monthlyFromAnnual } from "./blocks";
import {
  card, type Ctx, familyName, type FilterState, geoName, monthLabel, PROGRAMME_COLOR, provenance,
  skillLabel, vacancyUpdated,
} from "./common";
import { graduateTrend, statLines } from "./stats";

export const TRENDS_KINDS: (keyof GeoData)[] = ["vacancies", "skills", "families", "salaries"];

/** Markers for the vacancy series: where it starts, and methodology changes that break it. */
function vacancyMarkers(ctx: Ctx, idx: number[]): Marker[] {
  const { meta, lang } = ctx;
  const months = meta.vacancies.months;
  const markers: Marker[] = [];
  if (idx[0] === 0 && meta.vacancies.first_posted) {
    markers.push({ index: 0, label: lang === "nl" ? "start reeks" : "series start" });
  }
  for (const e of meta.changelog) {
    if (!e.series_break?.length) continue;
    const pos = idx.findIndex((i) => months[i].month === e.date.slice(0, 7));
    if (pos >= 0) markers.push({ index: pos, label: `${lang === "nl" ? "methodewijziging" : "method change"} ${fmtDate(lang, e.date)}` });
  }
  return markers;
}

export const completeMonths = (ctx: Ctx, idx: number[]) => idx.filter((i) => !ctx.meta.vacancies.months[i].partial);

export const notEnoughMonths = (ctx: Ctx, have: number) => (ctx.lang === "nl"
  ? `Een lijn verschijnt zodra er twee complete maanden zijn (nu: ${have}). Maanden die nog lopen of waarin de reeks begon, tellen niet mee omdat ze een vertekend beeld geven.`
  : `A line appears once there are two complete months (now: ${have}). Months still running or in which the series began are left out because they would distort the picture.`);

function moversCard(ctx: Ctx, title: string, res: ReturnType<typeof movers>, label: (id: string) => string,
                    n: number, minMonthsText: string): string {
  const { lang, tr, meta } = ctx;
  if (!res) {
    return card(ctx, { headingLevel: 2,
      title,
      body: `<p class="empty">${minMonthsText}</p>`,
      provenance: provenance(ctx, { sourceIds: [meta.vacancy_source], updated: vacancyUpdated(ctx) }),
    });
  }
  const items = (list: Mover[], colorVar: string) => list.map((m) => ({
    label: label(m.id),
    value: Math.abs(m.change),
    valueText: fmtPp(lang, m.change),
    tip: `${label(m.id)}: ${fmtPct(lang, m.earlierShare, 1)} → ${fmtPct(lang, m.recentShare, 1)} (${fmtPp(lang, m.change)})`,
    colorVar,
  }));
  const period = (ms: number[]) => `${monthLabel(ctx, ms[0])} – ${monthLabel(ctx, ms[ms.length - 1])}`;
  const body = `<div class="grid-2">`
    + `<div><h3 class="card-sub">▲ ${lang === "nl" ? "Stijgend" : "Rising"}</h3>${barList(items(res.rising, "--rise"), lang === "nl" ? "Stijgend" : "Rising", tr.chart.noData)}</div>`
    + `<div><h3 class="card-sub">▼ ${lang === "nl" ? "Dalend" : "Declining"}</h3>${barList(items(res.falling, "--fall"), lang === "nl" ? "Dalend" : "Declining", tr.chart.noData)}</div>`
    + `</div>`;
  return card(ctx, { headingLevel: 2,
    title,
    subtitle: lang === "nl"
      ? `Verschil in aandeel vacatures tussen ${period(res.recent)} en ${period(res.earlier)}, in procentpunten.`
      : `Difference in share of vacancies between ${period(res.recent)} and ${period(res.earlier)}, in percentage points.`,
    body,
    provenance: provenance(ctx, { sourceIds: [meta.vacancy_source], updated: vacancyUpdated(ctx), n }),
    table: table(title, ["", lang === "nl" ? "Eerder" : "Earlier", lang === "nl" ? "Recent" : "Recent", tr.chart.change],
      [...res.rising, ...res.falling].map((m) => [label(m.id), fmtPct(lang, m.earlierShare, 1), fmtPct(lang, m.recentShare, 1), fmtPp(lang, m.change)])),
  });
}

export function renderTrends(ctx: Ctx, state: FilterState, data: Record<string, GeoData>, stats?: Stats): string {
  const { lang, tr, meta } = ctx;
  const d = data[state.geo];
  const months = meta.vacancies.months;
  const idx = spanMonths(months, state.span);
  const labels = idx.map((i) => monthLabel(ctx, i));
  const start = meta.vacancies.first_posted;
  const needed = 2 * MIN_HALF_MONTHS;
  const firstComparison = months.length ? (() => {
    const [y, m] = months[0].month.split("-").map(Number);
    const dt = new Date(Date.UTC(y, m - 1 + needed, 1));
    return fmtMonth(lang, dt.toISOString().slice(0, 7), "long");
  })() : "–";
  const notEnough = lang === "nl"
    ? `Nog te weinig historie. Voor een vergelijking zijn minstens ${needed} maanden vacaturedata nodig; de eerste vergelijking verschijnt rond ${firstComparison}.`
    : `Not enough history yet. A comparison needs at least ${needed} months of vacancy data; the first comparison appears around ${firstComparison}.`;
  const out: string[] = [];

  // Vacancy volume
  const total = monthly(d.vacancies, idx);
  const n = [...total.values()].reduce((a, b) => a + b, 0);
  out.push(card(ctx, { headingLevel: 2,
    title: lang === "nl" ? "ICT-vacatures per maand" : "ICT vacancies per month",
    subtitle: `${geoName(ctx, state.geo)}. ${tr.chart.partialExplain}${start ? ` ${lang === "nl" ? "De reeks begint op" : "The series starts on"} ${fmtDate(lang, start)}.` : ""}`,
    body: columns(idx.map((i, k) => ({ label: labels[k], value: total.get(i) ?? 0, partial: months[i].partial,
                                      tip: `${labels[k]}: ${fmtInt(lang, total.get(i) ?? 0)} ${tr.chart.vacancies}` })),
                  lang === "nl" ? "Vacatures per maand" : "Vacancies per month", tr.chart.noData, (v) => fmtInt(lang, v)),
    provenance: provenance(ctx, { sourceIds: [meta.vacancy_source], updated: vacancyUpdated(ctx), n }),
    table: table(tr.chart.month, [tr.chart.month, tr.chart.count], idx.map((i, k) => [labels[k], fmtInt(lang, total.get(i) ?? 0)])),
  }));

  // Lines of volumes use complete months only: a partial month looks like a drop or a jump.
  const full = completeMonths(ctx, idx);
  const fullLabels = full.map((i) => monthLabel(ctx, i));
  const progSeries = meta.programmes.map((p) => {
    const m = monthly(d.vacancies, full, p.id);
    return { id: p.id, label: p.name[lang], colorVar: PROGRAMME_COLOR[p.id], values: full.map((i) => m.get(i) ?? 0) };
  });
  const fullMarkers = vacancyMarkers(ctx, full);
  out.push(card(ctx, { headingLevel: 2,
    title: lang === "nl" ? "Per opleiding" : "By programme",
    subtitle: (lang === "nl" ? "Alleen complete maanden." : "Complete months only.")
      + (fullMarkers.length ? ` ${lang === "nl" ? "Verticale lijnen" : "Vertical lines"}: ${fullMarkers.map((m) => m.label).join(", ")}.` : ""),
    body: full.length > 1
      ? lineChart(fullLabels, progSeries, lang === "nl" ? "Vacatures per opleiding per maand" : "Vacancies per programme per month",
                  (v) => fmtInt(lang, v), (v) => fmtInt(lang, v), fullMarkers)
      : `<p class="empty">${notEnoughMonths(ctx, full.length)}</p>`,
    provenance: provenance(ctx, { sourceIds: [meta.vacancy_source], updated: vacancyUpdated(ctx), n }),
    table: table(tr.chart.month, [tr.chart.month, ...meta.programmes.map((p) => p.name[lang])],
                 idx.map((i, k) => [`${labels[k]}${months[i].partial ? ` (${tr.chart.partial})` : ""}`,
                   ...meta.programmes.map((p) => fmtInt(lang, monthly(d.vacancies, [i], p.id).get(i) ?? 0))])),
  }));

  // Rising and declining skills and roles
  const allSkillRows = d.skills.filter(([, p, s]) => p === "all" && s === "all").map(([mi, , , id, c]) => [mi, id, c] as [number, string, number]);
  out.push(moversCard(ctx, lang === "nl" ? "Stijgende en dalende skills" : "Rising and declining skills",
    movers(allSkillRows, total, idx), (id) => skillLabel(ctx, id), n, notEnough));
  const famRows = d.families.filter(([, p]) => p === "all").map(([mi, , id, c]) => [mi, id, c] as [number, string, number]);
  out.push(moversCard(ctx, lang === "nl" ? "Stijgende en dalende functies" : "Rising and declining roles",
    movers(famRows, total, idx), (id) => familyName(ctx, id), n, notEnough));

  // Salary per quarter
  const qs = quarters(months, idx);
  const salarySeries = (["all", "entry"] as const).map((lvl, k) => {
    const st = qs.map((q) => salaryStats(d.salaries, q.months, "all", lvl));
    return { id: lvl, label: (tr.seniority as Record<string, string>)[lvl], colorVar: k ? "--series-2" : "--series-1",
             values: st.map((s) => (s.n >= meta.min_sample_size && s.median !== null ? monthlyFromAnnual(s.median) : null)), n: st.map((s) => s.n) };
  });
  const qLabels = qs.map((q) => fmtPeriod(lang, q.label));
  out.push(card(ctx, { headingLevel: 2,
    title: lang === "nl" ? "Mediaan salaris in vacatures, per kwartaal" : "Median salary in vacancies, per quarter",
    subtitle: lang === "nl"
      ? `Bruto per maand. Kwartalen met minder dan ${meta.min_sample_size} vacatures met salaris zijn weggelaten.`
      : `Gross per month. Quarters with fewer than ${meta.min_sample_size} vacancies with a salary are left out.`,
    body: salarySeries.some((s) => s.values.filter((v) => v !== null).length > 1)
      ? lineChart(qLabels, salarySeries, lang === "nl" ? "Mediaan salaris per kwartaal" : "Median salary per quarter",
                  (v) => fmtEuro(lang, v), (v) => fmtEuro(lang, v))
      : `<p class="empty">${lang === "nl" ? "Nog te weinig kwartalen voor een lijn; zie de tabel." : "Not enough quarters for a line yet; see the table."}</p>`,
    provenance: provenance(ctx, { sourceIds: [meta.vacancy_source], updated: vacancyUpdated(ctx),
                                  n: salarySeries[0].n.reduce((a, b) => a + b, 0), unit: lang === "nl" ? "vacatures met salaris" : "vacancies with a salary" }),
    table: table(lang === "nl" ? "Kwartaal" : "Quarter", [lang === "nl" ? "Kwartaal" : "Quarter", ...salarySeries.flatMap((s) => [s.label, "n"])],
      qLabels.map((l, k) => [l, ...salarySeries.flatMap((s) => [s.values[k] === null ? "–" : fmtEuro(lang, s.values[k]!), fmtInt(lang, s.n[k])])])),
  }));

  // Official statistics over the same span
  if (stats) {
    const years = SPAN_YEARS[state.span];
    out.push(`<h2>${lang === "nl" ? "Officiële statistiek" : "Official statistics"}</h2>`);
    out.push(statLines(ctx, stats, "cbs_open_vacancies_ict_sector_region", "region", [
      { key: "noord-holland", label: "Noord-Holland", colorVar: "--series-1" },
      { key: "NL", label: lang === "nl" ? "Nederland" : "Netherlands", colorVar: "--series-2" }], years));
    out.push(statLines(ctx, stats, "cbs_employed_ict_occupations", "breakdown", [
      { key: "software-developers", label: lang === "nl" ? "Software- en applicatieontwikkelaars" : "Software and application developers", colorVar: "--series-1" },
      { key: "system-analysts-advisers", label: lang === "nl" ? "Systeemanalisten en ICT-adviseurs" : "Systems analysts and ICT advisers", colorVar: "--series-2" },
      { key: "system-network-specialists", label: lang === "nl" ? "Systeembeheerders en netwerkspecialisten" : "System administrators and network specialists", colorVar: "--series-3" },
      { key: "user-support", label: lang === "nl" ? "Gebruikersondersteuning ICT" : "ICT user support", colorVar: "--series-4" }], years));
    out.push(statLines(ctx, stats, "cbs_new_vacancies_ict_occupations", "breakdown", [
      { key: "ict-specialists", label: lang === "nl" ? "Specialisten ICT" : "ICT specialists", colorVar: "--series-1" },
      { key: "ict-technicians", label: lang === "nl" ? "Vakspecialisten ICT" : "ICT technicians", colorVar: "--series-2" }], years));
    out.push(graduateTrend(ctx, stats));
  }
  return out.join("");
}
