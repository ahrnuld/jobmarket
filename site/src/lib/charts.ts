// Chart builders that return HTML strings. Used by Astro components at build time and by the
// filter scripts in the browser, so the static render and the re-render are identical.
//
// Design rules (dataviz method): thin marks, 4px rounded data-ends square at the baseline,
// hairline solid gridlines, text in text tokens (never the series color), every mark focusable
// with a tooltip, and a table view next to every chart.

import { escapeHtml as esc } from "./format";

export interface BarItem {
  label: string;
  value: number; // drives bar length
  valueText: string;
  tip: string;
  colorVar?: string; // e.g. "--series-1"
  href?: string;
  muted?: boolean; // e.g. indicative
}

export function barList(items: BarItem[], ariaLabel: string, emptyText: string): string {
  if (!items.length) return `<p class="empty">${esc(emptyText)}</p>`;
  const max = Math.max(...items.map((i) => i.value), 0) || 1;
  const rows = items.map((i) => {
    const width = Math.max((i.value / max) * 100, i.value > 0 ? 0.8 : 0);
    const label = i.href ? `<a href="${esc(i.href)}">${esc(i.label)}</a>` : esc(i.label);
    return `<li class="bar-row${i.muted ? " is-muted" : ""}" tabindex="0" data-tip="${esc(i.tip)}">`
      + `<span class="bar-label">${label}</span>`
      + `<span class="bar-track" aria-hidden="true"><span class="bar-fill" style="width:${width.toFixed(2)}%;`
      + `--c:var(${i.colorVar ?? "--series-1"})"></span></span>`
      + `<span class="bar-value">${esc(i.valueText)}</span></li>`;
  });
  return `<ul class="bars" aria-label="${esc(ariaLabel)}">${rows.join("")}</ul>`;
}

export interface ColumnPoint {
  label: string; // full label for tooltip/axis, e.g. "aug 2026"
  value: number;
  partial: boolean;
  tip: string;
}

/** Vertical columns over time (monthly counts). */
export function columns(points: ColumnPoint[], ariaLabel: string, emptyText: string,
                        formatTick: (n: number) => string): string {
  if (!points.length || points.every((p) => p.value === 0)) return `<p class="empty">${esc(emptyText)}</p>`;
  const max = niceMax(Math.max(...points.map((p) => p.value)));
  const cols = points.map((p) => {
    const h = (p.value / max) * 100;
    return `<li class="col${p.partial ? " is-partial" : ""}" tabindex="0" data-tip="${esc(p.tip)}"`
      + ` aria-label="${esc(p.tip)}"><span class="col-fill" style="height:${h.toFixed(2)}%"></span></li>`;
  });
  const first = points[0].label;
  const last = points[points.length - 1].label;
  return `<figure class="colchart" aria-label="${esc(ariaLabel)}">`
    + `<div class="colchart-plot">`
    + `<span class="tick tick-max" aria-hidden="true">${esc(formatTick(max))}</span>`
    + `<span class="tick tick-mid" aria-hidden="true">${esc(formatTick(max / 2))}</span>`
    + `<ol class="cols" style="--n:${points.length}">${cols.join("")}</ol></div>`
    + `<div class="colchart-x" aria-hidden="true"><span>${esc(first)}</span>`
    + (points.length > 1 ? `<span>${esc(last)}</span>` : "")
    + `</div></figure>`;
}

export interface RangeRow {
  label: string;
  p25: number;
  median: number;
  p75: number;
  tip: string;
  colorVar?: string;
  muted?: boolean;
}

/** Salary ranges: a bar from p25 to p75 with the median marked. One shared scale. */
export function ranges(rows: RangeRow[], ariaLabel: string, emptyText: string,
                       formatTick: (n: number) => string): string {
  if (!rows.length) return `<p class="empty">${esc(emptyText)}</p>`;
  const lo = Math.floor(Math.min(...rows.map((r) => r.p25)) / 500) * 500;
  const hi = Math.ceil(Math.max(...rows.map((r) => r.p75)) / 500) * 500;
  const span = hi - lo || 1;
  const pos = (v: number) => ((v - lo) / span) * 100;
  const items = rows.map((r) => `<li class="range-row${r.muted ? " is-muted" : ""}" tabindex="0" data-tip="${esc(r.tip)}">`
    + `<span class="bar-label">${esc(r.label)}</span>`
    + `<span class="range-track" aria-hidden="true"><span class="range-fill" style="left:${pos(r.p25).toFixed(2)}%;`
    + `width:${Math.max(pos(r.p75) - pos(r.p25), 0.8).toFixed(2)}%;--c:var(${r.colorVar ?? "--series-1"})"></span>`
    + `<span class="range-median" style="left:${pos(r.median).toFixed(2)}%;--c:var(${r.colorVar ?? "--series-1"})"></span></span>`
    + `<span class="bar-value">${esc(formatTick(r.median))}</span></li>`);
  return `<div class="rangechart"><ul class="ranges" aria-label="${esc(ariaLabel)}">${items.join("")}</ul>`
    + `<div class="range-axis" aria-hidden="true"><span></span><span class="range-axis-scale">`
    + `<span>${esc(formatTick(lo))}</span><span>${esc(formatTick(hi))}</span></span><span></span></div></div>`;
}

export interface LineSeries {
  id: string;
  label: string;
  colorVar: string;
  values: (number | null)[]; // aligned to the shared x labels
}

/** Line chart over a shared x axis. One y axis only (dataviz rule: never dual-axis). */
export interface Marker {
  index: number; // x position (may be fractional)
  label: string;
}

export function lineChart(xLabels: string[], series: LineSeries[], ariaLabel: string,
                          formatTick: (n: number) => string, formatValue: (n: number) => string,
                          markers: Marker[] = []): string {
  const all = series.flatMap((s) => s.values.filter((v): v is number => v !== null));
  if (!all.length) return "";
  const max = niceMax(Math.max(...all));
  const W = 100;
  const H = 40;
  const x = (i: number) => (xLabels.length > 1 ? (i / (xLabels.length - 1)) * W : W / 2);
  const y = (v: number) => H - (v / max) * H;
  const paths = series.map((s) => {
    let d = "";
    let pen = false;
    s.values.forEach((v, i) => {
      if (v === null) { pen = false; return; }
      d += `${pen ? "L" : "M"}${x(i).toFixed(3)},${y(v).toFixed(3)}`;
      pen = true;
    });
    return `<path d="${d}" style="stroke:var(${s.colorVar})" />`;
  });
  const payload = {
    x: xLabels,
    series: series.map((s) => ({ label: s.label, color: s.colorVar,
                                 values: s.values.map((v) => (v === null ? null : formatValue(v))) })),
    max,
  };
  const legend = series.length > 1
    ? `<ul class="legend">${series.map((s) => `<li><span class="key-line" style="--c:var(${s.colorVar})"></span>${esc(s.label)}</li>`).join("")}</ul>`
    : "";
  return `<figure class="linechart" aria-label="${esc(ariaLabel)}">${legend}`
    + `<div class="linechart-plot" tabindex="0" data-line='${esc(JSON.stringify(payload))}'>`
    + `<span class="tick tick-max" aria-hidden="true">${esc(formatTick(max))}</span>`
    + `<span class="tick tick-mid" aria-hidden="true">${esc(formatTick(max / 2))}</span>`
    + `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" aria-hidden="true">`
    + `<line class="grid" x1="0" x2="${W}" y1="${H / 2}" y2="${H / 2}" />`
    + `<line class="baseline" x1="0" x2="${W}" y1="${H}" y2="${H}" />${paths.join("")}</svg>`
    + markers.map((m) => `<span class="marker" style="left:${((x(m.index) / W) * 100).toFixed(2)}%">`
      + `<span class="marker-label">${esc(m.label)}</span></span>`).join("")
    + `<span class="crosshair" hidden></span></div>`
    + `<div class="colchart-x" aria-hidden="true"><span>${esc(xLabels[0])}</span><span>${esc(xLabels[xLabels.length - 1])}</span></div>`
    + `</figure>`;
}

export function table(caption: string, headers: string[], rows: (string | number)[][], numericFrom = 1): string {
  const head = headers.map((h, i) => `<th scope="col"${i >= numericFrom ? ' class="num"' : ""}>${esc(h)}</th>`).join("");
  const body = rows.map((r) => `<tr>${r.map((c, i) => (i === 0
    ? `<th scope="row">${esc(String(c))}</th>`
    : `<td${i >= numericFrom ? ' class="num"' : ""}>${esc(String(c))}</td>`)).join("")}</tr>`).join("");
  return `<table><caption class="visually-hidden">${esc(caption)}</caption><thead><tr>${head}</tr></thead>`
    + `<tbody>${body}</tbody></table>`;
}

/** Round an axis maximum up to a clean number whose half is also clean (the mid gridline). */
export function niceMax(v: number): number {
  if (v <= 0) return 1;
  const exp = Math.pow(10, Math.floor(Math.log10(v)));
  for (const m of [1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]) if (m * exp >= v) return m * exp;
  return 10 * exp;
}
