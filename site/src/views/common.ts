// Building blocks shared by all page views. Everything returns HTML strings (see lib/charts.ts).

import { fill, t } from "../i18n";
import { escapeHtml as esc, fmtDate, fmtInt, fmtMonth } from "../lib/format";
import type { Period, Seniority, Span, Window } from "../lib/model";
import type { Lang, Meta } from "../lib/types";

export interface Ctx {
  lang: Lang;
  meta: Meta;
  tr: ReturnType<typeof t>;
}

export const makeCtx = (lang: Lang, meta: Meta): Ctx => ({ lang, meta, tr: t(lang) });

export const geoName = (ctx: Ctx, id: string) =>
  ctx.meta.geos.find((g) => g.id === id)?.name[ctx.lang] ?? (id === "nl" ? ctx.tr.levels.country : id);

export const programmeName = (ctx: Ctx, id: string) =>
  id === "all" ? ctx.tr.filters.allProgrammes : ctx.meta.programmes.find((p) => p.id === id)?.name[ctx.lang] ?? id;

export const skillLabel = (ctx: Ctx, id: string) => ctx.meta.skills.find((s) => s.id === id)?.label ?? id;

export const familyName = (ctx: Ctx, id: string) =>
  ctx.meta.role_families.find((f) => f.id === id)?.name[ctx.lang] ?? id;

export const seniorityName = (ctx: Ctx, s: Seniority | string) =>
  (ctx.tr.seniority as Record<string, string>)[s] ?? s;

/** Programmes always keep the same color (dataviz: color follows the entity). */
export const PROGRAMME_COLOR: Record<string, string> = {
  informatica: "--series-1",
  "business-it-management": "--series-2",
  "technische-informatica": "--series-3",
};

export const monthLabel = (ctx: Ctx, mi: number) => fmtMonth(ctx.lang, ctx.meta.vacancies.months[mi].month);

export function windowLabel(ctx: Ctx, win: Window): string {
  if (!win.months.length) return "–";
  const first = monthLabel(ctx, win.months[0]);
  const last = monthLabel(ctx, win.months[win.months.length - 1]);
  return first === last ? first : `${first} – ${last}`;
}

export function source(ctx: Ctx, id: string) {
  return ctx.meta.sources.find((s) => s.id === id);
}

interface ProvenanceOpts {
  sourceIds: string[];
  updated: string | null;
  n?: number | null;
  unit?: string; // "vacatures" etc.
  extra?: string;
  /** Label before the date; default "bijgewerkt". Use "geraadpleegd" for figures copied by hand. */
  dateLabel?: string;
}

/** FR-05 / TR-01: source, last update and number of records under every chart. */
export function provenance(ctx: Ctx, o: ProvenanceOpts): string {
  const links = o.sourceIds.map((id) => {
    const s = source(ctx, id);
    if (!s) return esc(id);
    const name = s.id === "fixture" ? ctx.tr.chart.sample : s.name;
    return s.url.startsWith("https://example") ? esc(name) : `<a href="${esc(s.url)}">${esc(name)}</a>`;
  });
  const parts = [`${ctx.tr.chart.source}: ${links.join(", ")}`,
                 `${o.dateLabel ?? ctx.tr.chart.updated} ${esc(fmtDate(ctx.lang, o.updated))}`];
  if (o.n !== undefined && o.n !== null) {
    parts.push(`${ctx.tr.chart.basedOn} ${fmtInt(ctx.lang, o.n)} ${esc(o.unit ?? ctx.tr.chart.vacancies)}`);
  }
  if (o.extra) parts.push(esc(o.extra));
  return `<p class="provenance">${parts.join(" · ")}</p>`;
}

export function indicativeBadge(ctx: Ctx): string {
  const text = fill(ctx.tr.chart.indicativeExplain, { min: ctx.meta.min_sample_size });
  return `<span class="badge badge-indicative" tabindex="0" data-tip="${esc(text)}">`
    + `<span aria-hidden="true">◔</span> ${esc(ctx.tr.chart.indicative)}`
    + `<span class="visually-hidden">: ${esc(text)}</span></span>`;
}

export function sampleBadge(ctx: Ctx): string {
  return `<span class="badge badge-sample" tabindex="0" data-tip="${esc(ctx.tr.chart.sampleExplain)}">`
    + `<span aria-hidden="true">⚠</span> ${esc(ctx.tr.chart.sample)}`
    + `<span class="visually-hidden">: ${esc(ctx.tr.chart.sampleExplain)}</span></span>`;
}

export interface CardOpts {
  title: string;
  subtitle?: string;
  body: string;
  provenance: string;
  table?: string;
  badges?: string[];
  headingLevel?: 2 | 3;
  id?: string;
}

export function card(ctx: Ctx, o: CardOpts): string {
  const h = o.headingLevel ?? 3;
  const badges = o.badges?.filter(Boolean).join(" ") ?? "";
  return `<section class="card"${o.id ? ` id="${esc(o.id)}"` : ""}>`
    + `<div class="card-head"><h${h}>${esc(o.title)}</h${h}>${badges ? `<div class="badges">${badges}</div>` : ""}</div>`
    + (o.subtitle ? `<p class="card-sub">${esc(o.subtitle)}</p>` : "")
    + `<div class="card-body">${o.body}</div>${o.provenance}`
    + (o.table ? `<details class="table-view"><summary>${esc(ctx.tr.chart.showTable)}</summary>${o.table}</details>` : "")
    + `</section>`;
}

export interface TileOpts {
  label: string;
  value: string;
  sub?: string;
  badges?: string[];
}

export function tile(o: TileOpts): string {
  return `<div class="tile"><p class="tile-label">${esc(o.label)}</p>`
    + `<p class="tile-value">${esc(o.value)}</p>`
    + (o.sub ? `<p class="tile-sub">${esc(o.sub)}</p>` : "")
    + (o.badges?.length ? `<div class="badges">${o.badges.join(" ")}</div>` : "")
    + `</div>`;
}

export const vacancyUpdated = (ctx: Ctx) => ctx.meta.vacancies.last_posted ?? ctx.meta.generated_at;

/** Common filter state carried in the URL query, so a filtered view can be shared. */
export interface FilterState {
  geo: string;
  period: Period;
  seniority: Seniority;
  programme: string;
  span: Span; // trends page (FR-08)
  a: string; // compare page (FR-09): first programme
  b: string; // compare page: second programme
}

export const DEFAULT_STATE: FilterState = {
  geo: "p:noord-holland", // FR-07: Noord-Holland next to the national figure by default
  period: "12m",
  seniority: "all",
  programme: "all",
  span: "5y",
  a: "informatica",
  b: "technische-informatica", // persona Sanne compares these two
};
