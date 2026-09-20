// FR-07: vacancies per COROP area on a map of the Netherlands, for a chosen programme.
//
// COROP areas (40) are the CBS regional division for labour market analysis: larger than
// municipalities, so a single vacancy never makes an area light up, and complete for the whole
// country. The shapes are drawn once at build time (lib/map.ts); these functions compute the
// numbers, the classes and the table, at build time and again in the browser after a filter
// change, so both always show the same figures.

import { barList, table } from "../lib/charts";
import { escapeHtml as esc, fmtInt, fmtPct, fmtPeriod } from "../lib/format";
import { countVacancies, isIndicative, share, type Window } from "../lib/model";
import type { CoropInfo, MapData, Observation, Stats, VacancyRow } from "../lib/types";
import {
  card, type Ctx, type FilterState, programmeName, provenance, seniorityName, vacancyUpdated,
  windowLabel,
} from "./common";

export interface AreaCount extends CoropInfo {
  n: number;
  klass: number; // shade: 0 = no vacancies, 1 (light) .. 5 (dark)
}

export interface MapView {
  areas: AreaCount[]; // sorted by count, descending
  byCode: Map<string, AreaCount>;
  breaks: number[]; // lower bound of classes 2..5
  placed: number; // vacancies in a known COROP area
  total: number; // all vacancies in the selection, nationally
  unknown: number; // total - placed: postings that name no place, or many places at once
}

/**
 * Class boundaries from the data itself (quantiles of the areas that have vacancies), rounded
 * to a readable number. Fixed boundaries would put every area in the same class as soon as a
 * narrow selection is made; quantiles keep the map readable at every filter setting.
 */
export function mapBreaks(values: number[]): number[] {
  const positive = values.filter((v) => v > 0).sort((a, b) => a - b);
  if (positive.length < 2) return [];
  const nice = (v: number) => {
    if (v <= 10) return Math.max(2, Math.round(v));
    const exp = Math.pow(10, Math.floor(Math.log10(v)));
    for (const m of [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]) if (m * exp >= v) return m * exp;
    return 10 * exp;
  };
  const breaks: number[] = [];
  for (const q of [0.2, 0.4, 0.6, 0.8]) {
    const v = nice(positive[Math.min(Math.floor(q * positive.length), positive.length - 1)]);
    // Keep classes worth distinguishing: a class of a single count ("2", "3") tells a reader
    // nothing, so a boundary must leave room above the previous one.
    const prev = breaks[breaks.length - 1];
    if (v > 1 && (prev === undefined || (v >= prev + 2 && v >= prev * 1.5))) breaks.push(v);
  }
  return breaks;
}

export const classOf = (n: number, breaks: number[]) =>
  n <= 0 ? 0 : 1 + breaks.filter((b) => n >= b).length;

/**
 * Spread the classes over the five shades, so the darkest shade always means "most vacancies",
 * however many classes the data produced.
 */
export const shade = (klass: number, classes: number) =>
  klass <= 0 || classes <= 1 ? Math.max(klass, 0) : 1 + Math.round(((klass - 1) * 4) / (classes - 1));

export function buildMapView(state: FilterState, map: MapData, nl: VacancyRow[], win: Window): MapView {
  const months = new Set(win.months);
  const counts = new Map<string, number>();
  for (const [mi, corop, programme, seniority, n] of map.rows) {
    if (!months.has(mi) || programme !== state.programme || seniority !== state.seniority) continue;
    counts.set(corop, (counts.get(corop) ?? 0) + n);
  }
  const breaks = mapBreaks([...counts.values()]);
  const areas: AreaCount[] = map.corops
    .map((c) => {
      const n = counts.get(c.id) ?? 0;
      return { ...c, n, klass: shade(classOf(n, breaks), breaks.length + 1) };
    })
    .sort((a, b) => b.n - a.n || a.name.localeCompare(b.name));
  const placed = areas.reduce((t, a) => t + a.n, 0);
  const total = countVacancies(nl, win.months, state.programme, state.seniority);
  return { areas, byCode: new Map(areas.map((a) => [a.code, a])), breaks, placed, total,
           unknown: Math.max(total - placed, 0) };
}

const classRanges = (breaks: number[]): [number, number | null][] => {
  if (!breaks.length) return [[1, null]];
  const bounds: [number, number | null][] = [[1, breaks[0] - 1]];
  breaks.forEach((b, i) => bounds.push([b, i + 1 < breaks.length ? breaks[i + 1] - 1 : null]));
  return bounds;
};

export function legend(ctx: Ctx, view: MapView): string {
  const { lang } = ctx;
  const label = ([lo, hi]: [number, number | null]) =>
    hi === null ? `${fmtInt(lang, lo)}+` : lo === hi ? fmtInt(lang, lo) : `${fmtInt(lang, lo)}–${fmtInt(lang, hi)}`;
  const ranges = classRanges(view.breaks);
  const items = ranges.map((r, i) =>
    `<li><span class="map-key map-c${shade(i + 1, ranges.length)}" aria-hidden="true"></span>${esc(label(r))}</li>`);
  // "none found", not "none": an empty area means our source published nothing there.
  items.push(`<li><span class="map-key map-c0" aria-hidden="true"></span>`
    + `${esc(lang === "nl" ? "niets gevonden" : "none found")}</li>`);
  const title = lang === "nl" ? "Vacatures per gebied" : "Vacancies per area";
  return `<div class="map-legend"><p class="map-legend-title">${esc(title)}</p>`
    + `<ul aria-label="${esc(title)}">${items.join("")}</ul></div>`;
}

const provinceName = (ctx: Ctx, id: string) =>
  ctx.meta.geos.find((g) => g.id === `p:${id}`)?.name[ctx.lang] ?? id;

/** Text under the map: what is counted, where it comes from, and the full table (FR-05). */
export function details(ctx: Ctx, state: FilterState, view: MapView, win: Window): string {
  const { lang, tr, meta } = ctx;
  const nl = lang === "nl";
  const top = view.areas[0];
  const indicative = isIndicative(view.placed, meta.min_sample_size);
  const counted = nl
    ? `${fmtInt(lang, view.placed)} van de ${fmtInt(lang, view.total)} vacatures in deze selectie (${fmtPct(lang, share(view.placed, view.total))}) noemen een plaats die in een COROP-gebied valt.`
    : `${fmtInt(lang, view.placed)} of the ${fmtInt(lang, view.total)} vacancies in this selection (${fmtPct(lang, share(view.placed, view.total))}) name a place that falls within a COROP area.`;
  const one = view.unknown === 1;
  const rest = view.unknown === 0 ? "" : (nl
    ? ` De ${one ? "andere vacature noemt" : `overige ${fmtInt(lang, view.unknown)} noemen`} alleen "Nederland" of een provincie, of zoveel plaatsen tegelijk dat er geen werkplek uit op te maken is; die staat${one ? "" : "n"} niet op de kaart.`
    : ` The other ${one ? "vacancy names" : `${fmtInt(lang, view.unknown)} name`} only "Netherlands" or a province, or so many places at once that no workplace can be derived; ${one ? "it is" : "they are"} not on the map.`);
  const lead = top && top.n > 0
    ? (nl ? ` De meeste staan in ${top.name} (${fmtInt(lang, top.n)}).` : ` Most are in ${top.name} (${fmtInt(lang, top.n)}).`)
    : "";
  return `<p class="map-summary">${esc(counted + rest + lead)}</p>`
    + provenance(ctx, {
      sourceIds: [meta.vacancy_source],
      updated: vacancyUpdated(ctx),
      n: view.placed,
      extra: `${programmeName(ctx, state.programme)} · ${seniorityName(ctx, state.seniority)} · ${windowLabel(ctx, win)}`
        + (indicative ? ` · ${tr.chart.indicative.toLowerCase()}` : ""),
    })
    + `<p class="provenance">${esc(nl ? "Gebiedsgrenzen" : "Area boundaries")}: `
    + `<a href="https://www.cbs.nl/nl-nl/onze-diensten/methoden/classificaties/overig/gebiedsindelingen">CBS</a>`
    + ` ${esc(nl ? "gebiedsindelingen 2026 (COROP), CC BY 4.0" : "regional divisions 2026 (COROP), CC BY 4.0")}.</p>`
    + `<details class="table-view"><summary>${esc(tr.chart.showTable)}</summary>`
    + table(nl ? "Vacatures per COROP-gebied" : "Vacancies per COROP area",
      [nl ? "COROP-gebied" : "COROP area", nl ? "Provincie" : "Province", tr.chart.vacancies,
       nl ? "Aandeel" : "Share"],
      view.areas.map((a) => [a.name, provinceName(ctx, a.province), fmtInt(lang, a.n),
                             fmtPct(lang, share(a.n, view.placed), 1)]), 2)
    + `</details>`;
}

/** Accessible name and tooltip of one area. */
export const areaTitle = (ctx: Ctx, a: AreaCount) =>
  `${a.name}: ${fmtInt(ctx.lang, a.n)} ${a.n === 1 ? ctx.tr.chart.vacancy : ctx.tr.chart.vacancies}`;

/** Recolour the shapes that were rendered at build time (browser only). */
export function paint(ctx: Ctx, svg: SVGSVGElement, view: MapView): void {
  for (const path of Array.from(svg.querySelectorAll<SVGPathElement>("path[data-code]"))) {
    const area = view.byCode.get(path.dataset.code ?? "");
    if (!area) continue;
    path.setAttribute("class", `map-area map-c${area.klass}`);
    const title = path.querySelector("title");
    if (title) title.textContent = areaTitle(ctx, area);
  }
}


/** The official regional picture next to our own counts (FR-05, TR-04: how representative?). */
export function officialCard(ctx: Ctx, stats: Stats): string {
  const { lang, tr } = ctx;
  const nl = lang === "nl";
  const series = stats.series["cbs_open_vacancies_ict_sector_region"];
  const all = stats.observations.filter((o) => o.series === "cbs_open_vacancies_ict_sector_region");
  if (!series || !all.length) return "";
  const period = [...all].sort((a, b) => (a.start < b.start ? -1 : 1)).at(-1)!.period;
  const inPeriod = all.filter((o) => o.period === period && o.region !== "NL" && o.value !== null);
  if (!inPeriod.length) return "";
  const name = (id: string) => ctx.meta.geos.find((g) => g.id === `p:${id}`)?.name[lang] ?? id;
  const sorted = [...inPeriod].sort((a, b) => (b.value ?? 0) - (a.value ?? 0));
  const unit = nl ? "openstaande vacatures" : "open vacancies";
  const items = sorted.map((o) => ({
    label: name(o.region),
    value: o.value ?? 0,
    valueText: fmtInt(lang, o.value ?? 0),
    tip: `${name(o.region)}: ${fmtInt(lang, o.value ?? 0)} ${unit} (${fmtPeriod(lang, period)})`,
  }));
  const published = (list: Observation[]) =>
    list.map((o) => o.published ?? o.retrieved).sort().at(-1) ?? null;
  return card(ctx, {
    title: nl ? "Ter vergelijking: de officiële verdeling over de provincies"
              : "For comparison: the official spread across the provinces",
    subtitle: nl
      ? `CBS telt op een peilmoment (${fmtPeriod(lang, period)}) de openstaande vacatures bij bedrijven in de sector Informatie en communicatie. Dat is een andere telling dan onze advertenties hierboven — een voorraad in plaats van nieuwe advertenties, en alleen ICT-bedrijven — maar het laat zien waar het ICT-werk zit volgens de officiële statistiek.`
      : `CBS counts the vacancies open at a point in time (${fmtPeriod(lang, period)}) at companies in the Information and communication sector. That is a different count from our ads above — a stock rather than new ads, and ICT companies only — but it shows where the ICT work is according to official statistics.`,
    body: barList(items, series.title[lang], tr.chart.noData),
    provenance: provenance(ctx, { sourceIds: [series.source], updated: published(inPeriod),
                                  extra: series.table ? `${nl ? "tabel" : "table"} ${series.table}` : undefined }),
    table: table(series.title[lang], [nl ? "Provincie" : "Province", unit],
                 sorted.map((o) => [name(o.region), fmtInt(lang, o.value ?? 0)])),
    headingLevel: 2,
  });
}
