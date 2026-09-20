// Overview page (FR-01, FR-07): the selected region next to the national figure.

import { barList, columns, table } from "../lib/charts";
import { fmtInt, fmtPct } from "../lib/format";
import {
  byProgramme, countVacancies, isIndicative, knownLevel, monthly, share, window,
} from "../lib/model";
import type { GeoData } from "../lib/types";
import { path } from "../i18n";
import {
  card, type Ctx, type FilterState, geoName, indicativeBadge, monthLabel, programmeName,
  provenance, seniorityName, tile, vacancyUpdated, windowLabel,
} from "./common";

export const DASHBOARD_KINDS: (keyof GeoData)[] = ["vacancies"];

function changeText(ctx: Ctx, cur: number, prev: number | null): string {
  if (prev === null) return ctx.tr.chart.noPrevious;
  if (prev === 0) return "–";
  const rel = (cur - prev) / prev;
  const sign = rel > 0 ? "+" : "";
  return `${sign}${fmtPct(ctx.lang, rel)} ${ctx.tr.chart.vsPrevious}`;
}

function panel(ctx: Ctx, state: FilterState, geoId: string, data: GeoData): string {
  const { lang, tr, meta } = ctx;
  const win = window(meta.vacancies.months, state.period);
  const rows = data.vacancies;
  const total = countVacancies(rows, win.months, "all", state.seniority);
  const prev = win.previous ? countVacancies(rows, win.previous, "all", state.seniority) : null;
  const all = countVacancies(rows, win.months, "all", "all");
  const entry = countVacancies(rows, win.months, "all", "entry");
  const unknown = countVacancies(rows, win.months, "all", "unknown");
  const stated = knownLevel(rows, win.months);
  const min = meta.min_sample_size;
  const indicative = isIndicative(total, min) ? [indicativeBadge(ctx)] : [];
  const levelNote = state.seniority === "all" ? "" : ` · ${seniorityName(ctx, state.seniority)}`;

  const tiles = [
    tile({ label: `${lang === "nl" ? "ICT-vacatures" : "ICT vacancies"}${levelNote}`, value: fmtInt(lang, total),
           sub: `${windowLabel(ctx, win)} · ${changeText(ctx, total, prev)}`, badges: indicative }),
    tile({ label: tr.seniority.entry, value: fmtPct(lang, share(entry, stated)),
           sub: lang === "nl"
             ? `${fmtInt(lang, entry)} van de ${fmtInt(lang, stated)} vacatures die een niveau noemen`
             : `${fmtInt(lang, entry)} of the ${fmtInt(lang, stated)} vacancies that state a level`,
           badges: isIndicative(stated, min) ? [indicativeBadge(ctx)] : [] }),
    tile({ label: tr.seniority.unknown, value: fmtPct(lang, share(unknown, all)),
           sub: lang === "nl" ? "Niveau staat niet in de titel of het begin van de tekst"
                              : "Level not stated in the title or the start of the text" }),
  ].join("");

  const perMonth = monthly(rows, win.months, "all", state.seniority);
  const points = win.months.map((mi) => {
    const n = perMonth.get(mi) ?? 0;
    const partial = meta.vacancies.months[mi].partial;
    const label = monthLabel(ctx, mi);
    return { label, value: n, partial,
             tip: `${label}${partial ? ` (${tr.chart.partial})` : ""}: ${fmtInt(lang, n)} ${tr.chart.vacancies}` };
  });
  const trend = card(ctx, {
    title: lang === "nl" ? "Nieuwe ICT-vacatures per maand" : "New ICT vacancies per month",
    subtitle: win.partial ? tr.chart.partialExplain : undefined,
    body: columns(points, `${geoName(ctx, geoId)}: ${lang === "nl" ? "vacatures per maand" : "vacancies per month"}`,
                  tr.chart.noData, (n) => fmtInt(lang, n)),
    provenance: provenance(ctx, { sourceIds: meta.vacancy_sources, updated: vacancyUpdated(ctx), n: total }),
    table: table(tr.chart.month, [tr.chart.month, tr.chart.count],
                 points.map((p) => [`${p.label}${p.partial ? ` (${tr.chart.partial})` : ""}`, fmtInt(lang, p.value)])),
    badges: indicative,
  });

  const progIds = meta.programmes.map((p) => p.id);
  const perProg = byProgramme(rows, win.months, progIds, state.seniority);
  const items = progIds.map((id) => ({
    label: programmeName(ctx, id),
    value: perProg[id],
    valueText: `${fmtInt(lang, perProg[id])} · ${fmtPct(lang, share(perProg[id], total))}`,
    tip: `${programmeName(ctx, id)}: ${fmtInt(lang, perProg[id])} ${tr.chart.vacancies} (${fmtPct(lang, share(perProg[id], total))})`,
    href: path(lang, "programmes", id),
    muted: isIndicative(perProg[id], min),
  }));
  const noProgramme = lang === "nl"
    ? "Een vacature kan bij meer dan één opleiding horen, en niet elke ICT-vacature past bij een van de drie (bijv. servicedesk). De percentages tellen daarom niet op tot 100%."
    : "A vacancy can fit more than one programme, and not every ICT vacancy fits one of the three (e.g. service desk). Percentages therefore do not add up to 100%.";
  const programmes = card(ctx, {
    title: lang === "nl" ? "Per opleiding" : "By programme",
    subtitle: noProgramme,
    body: barList(items, lang === "nl" ? "Vacatures per opleiding" : "Vacancies by programme", tr.chart.noData),
    provenance: provenance(ctx, { sourceIds: meta.vacancy_sources, updated: vacancyUpdated(ctx), n: total }),
    table: table(tr.filters.programme, [tr.filters.programme, tr.chart.count, tr.chart.share],
                 items.map((i, k) => [i.label, fmtInt(lang, perProg[progIds[k]]), fmtPct(lang, share(perProg[progIds[k]], total))])),
  });

  return `<section class="panel" aria-labelledby="panel-${geoId.replace(":", "-")}">`
    + `<h2 id="panel-${geoId.replace(":", "-")}">${geoName(ctx, geoId)}</h2>`
    + `<div class="tiles">${tiles}</div>${trend}${programmes}</section>`;
}

/** The selected region, and the national figure next to it (FR-07). */
export function renderDashboard(ctx: Ctx, state: FilterState, data: Record<string, GeoData>): string {
  const geos = state.geo === "nl" ? ["nl"] : [state.geo, "nl"];
  return `<div class="panels panels-${geos.length}">${geos.map((g) => panel(ctx, state, g, data[g])).join("")}</div>`;
}
