// Published statistics (CBS, HBO-Monitor, ROA, UWV). Rendered at build time only.

import { lineChart, table } from "../lib/charts";
import { fmtEuro, fmtInt, fmtPct, fmtPeriod } from "../lib/format";
import type { Observation, Stats } from "../lib/types";
import { card, type Ctx, indicativeBadge, programmeName, provenance, sampleBadge, tile } from "./common";

export const obs = (stats: Stats, series: string, filter: Partial<Observation> = {}) =>
  stats.observations.filter((o) => o.series === series
    && Object.entries(filter).every(([k, v]) => (o as unknown as Record<string, unknown>)[k] === v));

const latestPublished = (list: Observation[]) =>
  list.map((o) => o.published ?? o.retrieved).sort().at(-1) ?? null;

const latest = (list: Observation[]) => [...list].sort((a, b) => (a.start < b.start ? -1 : 1)).at(-1);

/**
 * Graduate outcomes per programme (HBO-Monitor) and the forecast (ROA), as tiles.
 * FR-04 (graduate part) and FR-02 (starting salary). Forecasts are labelled as scenarios (LR-06).
 */
export function graduateCard(ctx: Ctx, stats: Stats, programmes: string[], headingLevel: 2 | 3 = 3): string {
  const { lang, tr, meta } = ctx;
  const used: Observation[] = [];
  const tiles = programmes.map((p) => {
    const sal = latest(obs(stats, "hbo_starting_salary", { breakdown: p }));
    const match = latest(obs(stats, "hbo_job_match", { breakdown: p }));
    const outlook = latest(obs(stats, "roa_outlook", { breakdown: p }));
    for (const o of [sal, match, outlook]) if (o) used.push(o);
    const badges = [sal, match, outlook].some((o) => o?.sample) ? [sampleBadge(ctx)] : [];
    if (sal?.n !== null && sal?.n !== undefined && sal.n < meta.min_sample_size) badges.push(indicativeBadge(ctx));
    const parts = [
      match?.value != null ? `${fmtPct(lang, match.value / 100)} ${lang === "nl" ? "werkt op minimaal hbo-niveau" : "work at bachelor level or above"}` : null,
      outlook?.label ? `${lang === "nl" ? "Vooruitzicht" : "Outlook"} ${outlook.period}: ${outlook.label}` : null,
      sal ? `${lang === "nl" ? "Afgestudeerd" : "Graduated"} ${sal.period}${sal.n ? `, n=${fmtInt(lang, sal.n)}` : ""}` : null,
    ].filter(Boolean);
    return tile({
      label: programmes.length > 1 ? programmeName(ctx, p) : (lang === "nl" ? "Startsalaris afgestudeerden" : "Graduate starting salary"),
      value: sal?.value != null ? fmtEuro(lang, sal.value) : "–",
      sub: parts.join(" · "),
      badges,
    });
  });
  if (!used.length) return "";
  const sources = [...new Set(used.map((o) => o.source))];
  const updated = used.map((o) => o.published ?? o.retrieved).sort().at(-1) ?? null;
  const links = [...new Set(used.map((o) => o.url).filter((u): u is string => !!u && !u.includes("example.invalid")))];
  return card(ctx, {
    title: lang === "nl" ? "Na het afstuderen" : "After graduating",
    subtitle: lang === "nl"
      ? "Bruto maandsalaris ongeveer een jaar na afstuderen en werk op niveau (HBO-Monitor), en het arbeidsmarktperspectief volgens ROA. Een prognose is een scenario, geen zekerheid."
      : "Gross monthly salary about a year after graduating and work at level (HBO-Monitor), and the labour market outlook according to ROA. A forecast is a scenario, not a certainty.",
    body: `<div class="tiles">${tiles.join("")}</div>`,
    provenance: provenance(ctx, { sourceIds: sources, updated,
                                  extra: used.some((o) => o.sample) ? tr.chart.sampleExplain : undefined })
      + (links.length ? `<p class="provenance">${links.map((u) => `<a href="${u}">${new URL(u).hostname} ↗</a>`).join(" · ")}</p>` : ""),
    headingLevel,
  });
}

/** A line chart of one statistics series split by region or breakdown, last `years` years. */
export function statLines(ctx: Ctx, stats: Stats, seriesId: string, split: "region" | "breakdown",
                          keys: { key: string; label: string; colorVar: string }[], years = 10,
                          headingLevel: 2 | 3 = 3): string {
  const { lang, tr } = ctx;
  const meta = stats.series[seriesId];
  const all = obs(stats, seriesId);
  if (!meta || !all.length) return "";
  const cutoff = `${Number(all.at(-1)!.start.slice(0, 4)) - years}`;
  const periods = [...new Set(all.filter((o) => o.start >= cutoff).map((o) => o.period))]
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
