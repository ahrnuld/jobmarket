// Published statistics (CBS; Studiekeuze123 with HBO-Monitor, CBS Microdata and ROA figures).

import { barList, lineChart, table } from "../lib/charts";
import { escapeHtml as esc, fmtEuro, fmtInt, fmtPct, fmtPeriod } from "../lib/format";
import { yearsBefore } from "../lib/model";
import type { Observation, Stats } from "../lib/types";
import {
  card, type Ctx, PROGRAMME_COLOR, programmeName, provenance, sampleBadge,
} from "./common";

export const obs = (stats: Stats, series: string, filter: Partial<Observation> = {}) =>
  stats.observations.filter((o) => o.series === series
    && Object.entries(filter).every(([k, v]) => (o as unknown as Record<string, unknown>)[k] === v));

const latestPublished = (list: Observation[]) =>
  list.map((o) => o.published ?? o.retrieved).sort().at(-1) ?? null;

const latest = (list: Observation[]) => [...list].sort((a, b) => (a.start < b.start ? -1 : 1)).at(-1);

const SK = "studiekeuze123";

/** The latest value of a Studiekeuze123 series for one breakdown. */
const skValue = (stats: Stats, series: string, breakdown: string) =>
  latest(obs(stats, series, { breakdown }));

/** Programmes whose graduate figures are identical (computed per group of related programmes). */
function sharedWith(ctx: Ctx, stats: Stats, programme: string): string[] {
  const key = (p: string) => ["sk_starting_salary", "sk_job_at_level", "sk_job_in_field", "sk_permanent_contract"]
    .map((s) => skValue(stats, s, p)?.value ?? "-").join("|");
  const mine = key(programme);
  if (mine.replace(/[|-]/g, "") === "") return [];
  return ctx.meta.programmes.map((p) => p.id).filter((p) => p !== programme && key(p) === mine);
}

/**
 * What graduates achieve, per programme: estimated starting salary, work at level and in field,
 * time to a job, contracts, and ROA's outlook (FR-02, FR-04). Source: Studiekeuzedatabase of the
 * Landelijk Centrum Studiekeuze; each figure names its underlying source. Forecasts are labelled
 * as scenarios (LR-06).
 */
export function graduateCard(ctx: Ctx, stats: Stats, programmes: string[], headingLevel: 2 | 3 = 3): string {
  const { lang } = ctx;
  const nl = lang === "nl";
  const avg = skValue(stats, "sk_starting_salary", "hbo-bachelor")?.value ?? null;
  const used: Observation[] = [];
  const rows: string[][] = [];
  const pct = (v: number | null | undefined) => (v == null ? "–" : fmtPct(lang, v / 100));
  const tiles = programmes.map((p) => {
    const v = (s: string) => {
      const o = skValue(stats, s, p);
      if (o) used.push(o);
      return o;
    };
    const sal = v("sk_starting_salary");
    const lvl = v("sk_job_at_level");
    const fld = v("sk_job_in_field");
    const mon = v("sk_months_to_job");
    const perm = v("sk_permanent_contract");
    const out = v("sk_outlook");
    if (!sal && !lvl && !out) return "";
    const diff = sal?.value != null && avg != null ? sal.value - avg : null;
    const items = [
      diff !== null && avg !== null
        ? `${fmtEuro(lang, Math.abs(diff))} ${diff >= 0 ? (nl ? "boven" : "above") : (nl ? "onder" : "below")} `
          + `${nl ? "het gemiddelde van alle hbo-bachelors" : "the average of all hbo bachelors"} (${fmtEuro(lang, avg)})`
        : null,
      lvl?.value != null ? `${pct(lvl.value)} ${nl ? "heeft een baan op hbo-niveau" : "have a job at bachelor level"}` : null,
      fld?.value != null ? `${pct(fld.value)} ${nl ? "werkt in het eigen vakgebied" : "work in their own field"}` : null,
      mon?.value != null ? `${nl ? "gemiddeld" : "on average"} ${fmtInt(lang, mon.value)} ${nl ? "maanden tot een baan" : "months to a job"}` : null,
      perm?.value != null ? `${pct(perm.value)} ${nl ? "heeft een vast contract" : "have a permanent contract"}` : null,
      out?.label ? `${nl ? "Perspectief tot" : "Outlook to"} ${out.period} (ROA): ${out.label}` : null,
    ].filter((x): x is string => !!x);
    rows.push([programmeName(ctx, p), sal?.value != null ? fmtEuro(lang, sal.value) : "–", pct(lvl?.value), pct(fld?.value),
               mon?.value != null ? fmtInt(lang, mon.value) : "–", pct(perm?.value), out?.label ?? "–"]);
    const label = programmes.length > 1
      ? programmeName(ctx, p)
      : (nl ? "Geschat startsalaris (bruto per maand)" : "Estimated starting salary (gross per month)");
    return `<div class="tile"><p class="tile-label">${esc(label)}</p>`
      + `<p class="tile-value">${sal?.value != null ? esc(fmtEuro(lang, sal.value)) : "–"}</p>`
      + `<ul class="tile-list">${items.map((i) => `<li>${esc(i)}</li>`).join("")}</ul></div>`;
  }).filter(Boolean);
  if (!tiles.length) return "";

  // Programmes that share identical figures: say so instead of suggesting separate measurements.
  const notes: string[] = [];
  const seen = new Set<string>();
  for (const p of programmes) {
    if (seen.has(p)) continue;
    const partners = sharedWith(ctx, stats, p);
    const group = [p, ...partners];
    group.forEach((x) => seen.add(x));
    if (!partners.length) continue;
    const names = group.map((x) => programmeName(ctx, x));
    notes.push(nl
      ? `${names.join(" en ")} hebben dezelfde cijfers: ze worden landelijk berekend voor een groep verwante opleidingen, niet per opleiding afzonderlijk.`
      : `${names.join(" and ")} have the same figures: they are calculated nationally for a group of related programmes, not per programme.`);
  }
  const links = [...new Set(used.map((o) => o.url).filter((u): u is string => !!u))];
  const updated = used.map((o) => o.published ?? o.retrieved).sort().at(-1) ?? null;
  const linkLabel = (u: string) => {
    const code = /studies\/(\d+)/.exec(u)?.[1];
    return code ? `Studiekeuze123 ${code}` : "Studiekeuze123";
  };
  return card(ctx, {
    title: nl ? "Na het afstuderen" : "After graduating",
    subtitle: (nl
      ? "Landelijke cijfers over afgestudeerden van voltijdopleidingen. Salaris, contract en tijd tot een baan: CBS Microdata. Baan op niveau en in vakgebied: HBO-Monitor, anderhalf jaar na afstuderen. Perspectief: prognose van ROA, een scenario en geen zekerheid."
      : "National figures on graduates of full-time programmes. Salary, contract and time to a job: CBS Microdata. Job at level and in field: HBO-Monitor, about a year and a half after graduating. Outlook: ROA forecast, a scenario and not a certainty.")
      + (notes.length ? ` ${notes.join(" ")}` : ""),
    body: `<div class="tiles">${tiles.join("")}</div>`,
    provenance: provenance(ctx, {
      sourceIds: [SK], updated, dateLabel: nl ? "geraadpleegd" : "consulted",
      extra: nl ? "meetjaar en aantal respondenten niet gepubliceerd" : "measurement year and number of respondents not published",
    }) + (links.length
      ? `<p class="provenance">${links.map((u) => `<a href="${esc(u)}">${esc(linkLabel(u))} ↗</a>`).join(" · ")}</p>`
      : ""),
    table: table(nl ? "Na het afstuderen" : "After graduating",
      [nl ? "Opleiding" : "Programme", nl ? "Startsalaris" : "Starting salary", nl ? "Op niveau" : "At level",
       nl ? "In vakgebied" : "In field", nl ? "Maanden tot baan" : "Months to job",
       nl ? "Vast contract" : "Permanent contract", nl ? "Perspectief" : "Outlook"],
      rows),
    headingLevel,
  });
}

/** Where graduates of a programme work (HBO-Monitor via Studiekeuze123). */
export function occupationsCard(ctx: Ctx, stats: Stats, programme: string, headingLevel: 2 | 3 = 3): string {
  const { lang, tr } = ctx;
  const nl = lang === "nl";
  const list = obs(stats, "sk_occupation")
    .filter((o) => o.breakdown.startsWith(`${programme}/`) && o.value != null)
    .sort((a, b) => (b.value ?? 0) - (a.value ?? 0));
  if (!list.length) return "";
  const name = (o: Observation) => o.breakdown.slice(programme.length + 1);
  return card(ctx, {
    title: nl ? "Waar werken afgestudeerden?" : "Where do graduates work?",
    subtitle: nl
      ? "Beroepen van afgestudeerden anderhalf jaar na afstuderen (landelijk, alle opleidingsvormen). Alleen de grootste beroepen staan erin, dus de percentages tellen niet op tot 100%."
      : "Occupations of graduates about a year and a half after graduating (national, all study modes). Only the largest occupations are listed, so the percentages do not add up to 100%.",
    body: barList(list.map((o) => ({
      label: name(o), value: o.value!, valueText: fmtPct(lang, o.value! / 100),
      tip: `${name(o)}: ${fmtPct(lang, o.value! / 100)}`, colorVar: PROGRAMME_COLOR[programme],
    })), nl ? "Beroepen van afgestudeerden" : "Occupations of graduates", tr.chart.noData),
    provenance: provenance(ctx, {
      sourceIds: [SK], updated: latestPublished(list), dateLabel: nl ? "geraadpleegd" : "consulted",
      extra: nl ? "onderliggende bron: HBO-Monitor" : "underlying source: HBO-Monitor",
    }),
    table: table(nl ? "Beroepen" : "Occupations", [nl ? "Beroep" : "Occupation", tr.chart.share],
                 list.map((o) => [name(o), fmtPct(lang, o.value! / 100)])),
    headingLevel,
  });
}

/** A line chart of one statistics series split by region or breakdown, last `years` years. */
export function statLines(ctx: Ctx, stats: Stats, seriesId: string, split: "region" | "breakdown",
                          keys: { key: string; label: string; colorVar: string }[], years: number | null = 10,
                          headingLevel: 2 | 3 = 3): string {
  const { lang, tr } = ctx;
  const meta = stats.series[seriesId];
  const all = obs(stats, seriesId);
  if (!meta || !all.length) return "";
  const latestStart = all.map((o) => o.start).sort().at(-1)!;
  const cutoff = years === null ? "" : yearsBefore(latestStart, years);
  const periods = [...new Set(all.filter((o) => o.start > cutoff).map((o) => o.period))]
    .sort((a, b) => (all.find((o) => o.period === a)!.start < all.find((o) => o.period === b)!.start ? -1 : 1));
  const series = keys.map((k) => ({
    id: k.key, label: k.label, colorVar: k.colorVar,
    values: periods.map((p) => all.find((o) => o.period === p && o[split] === k.key)?.value ?? null),
  }));
  const provisional = all.filter((o) => o.note === "voorlopig").map((o) => fmtPeriod(lang, o.period));
  const xLabels = periods.map((p) => fmtPeriod(lang, p));
  const chart = lineChart(xLabels, series, meta.title[lang], (n) => fmtInt(lang, n), (n) => fmtInt(lang, n));
  const rows = periods.map((p, i) => [
    `${fmtPeriod(lang, p)}${all.some((o) => o.period === p && o.note === "voorlopig") ? ` (${tr.chart.provisional})` : ""}`,
    ...series.map((s) => (s.values[i] === null ? "–" : fmtInt(lang, s.values[i]!))),
  ]);
  const tableUrl = all[0].url;
  const extra = provisional.length
    ? `${tr.chart.provisional}: ${[...new Set(provisional)].slice(-4).join(", ")}` : undefined;
  return card(ctx, {
    title: meta.title[lang],
    subtitle: meta.note?.[lang],
    body: chart,
    provenance: provenance(ctx, { sourceIds: [meta.source], updated: latestPublished(all), extra })
      + (tableUrl ? `<p class="provenance"><a href="${tableUrl}">${lang === "nl" ? "Tabel" : "Table"} ${meta.table ?? ""} ↗</a></p>` : ""),
    table: table(meta.title[lang], [tr.chart.period, ...series.map((s) => s.label)], rows),
    badges: all.some((o) => o.sample) ? [sampleBadge(ctx)] : [],
    headingLevel,
  });
}

/** Estimated starting salary per programme over the years; shown once there are several years. */
export function graduateTrend(ctx: Ctx, stats: Stats): string {
  const { lang } = ctx;
  const all = obs(stats, "sk_starting_salary").filter((o) => o.breakdown !== "hbo-bachelor");
  if (!all.length) return "";
  const html = statLines(ctx, stats, "sk_starting_salary", "breakdown",
    ctx.meta.programmes.map((p) => ({ key: p.id, label: p.name[lang], colorVar: PROGRAMME_COLOR[p.id] })), null);
  // A trend needs at least two measurement years; a single year is shown on the programme pages.
  return new Set(all.map((o) => o.period)).size > 1 ? html : "";
}
