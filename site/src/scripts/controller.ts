// Client-side filtering for a page whose static HTML shows the default filter state.
// Changing a filter fetches the needed aggregate files and re-renders with the same view
// function used at build time. The filter state lives in the URL query, so views can be shared.

import { fetchGeo, fetchMeta, fetchStats } from "../lib/client-data";
import { PERIODS, SENIORITIES, type Period, type Seniority } from "../lib/model";
import type { GeoData, Lang, Stats } from "../lib/types";
import { DEFAULT_STATE, type Ctx, type FilterState, makeCtx } from "../views/common";

interface Options {
  lang: Lang;
  root: HTMLElement;
  form: HTMLFormElement;
  kinds: (keyof GeoData)[];
  geos: (state: FilterState) => string[];
  render: (ctx: Ctx, state: FilterState, data: Record<string, GeoData>, stats?: Stats) => string;
  /** Also load stats.json (the trends page re-renders official series too). */
  withStats?: boolean;
  defaults?: Partial<FilterState>;
  onRendered?: () => void;
}

/** Filter state from the URL query, limited to values the form actually offers. */
export function readState(form: HTMLFormElement, defaults: FilterState): FilterState {
  const params = new URLSearchParams(location.search);
  const state = { ...defaults };
  for (const key of Object.keys(defaults) as (keyof FilterState)[]) {
    const v = params.get(key);
    const field = form.elements.namedItem(key) as HTMLSelectElement | null;
    if (v && field && [...field.options].some((o) => o.value === v)) (state[key] as string) = v;
  }
  if (!PERIODS.includes(state.period as Period)) state.period = defaults.period;
  if (!SENIORITIES.includes(state.seniority as Seniority)) state.seniority = defaults.seniority;
  return state;
}

function writeForm(form: HTMLFormElement, state: FilterState) {
  for (const [k, v] of Object.entries(state)) {
    const field = form.elements.namedItem(k) as HTMLSelectElement | null;
    if (field) field.value = v;
  }
}

/** Keep the filter state in the URL, so a filtered view can be shared. */
export function writeQuery(state: FilterState, defaults: FilterState) {
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(state)) {
    if (v !== (defaults as unknown as Record<string, string>)[k]) params.set(k, v);
  }
  const q = params.toString();
  history.replaceState(null, "", q ? `?${q}` : location.pathname);
}

/** The filter values the form currently holds. */
export function formState(form: HTMLFormElement, state: FilterState): FilterState {
  const fd = new FormData(form);
  const next = { ...state };
  for (const k of Object.keys(next) as (keyof FilterState)[]) {
    const v = fd.get(k);
    if (typeof v === "string") (next[k] as string) = v;
  }
  return next;
}

export function initFilteredView(o: Options) {
  const defaults: FilterState = { ...DEFAULT_STATE, ...o.defaults };
  const status = o.form.querySelector<HTMLElement>("[data-filter-status]");
  let state = readState(o.form, defaults);
  let request = 0;

  async function update(pushUrl: boolean) {
    const mine = ++request;
    o.root.classList.add("is-loading");
    o.root.setAttribute("aria-busy", "true");
    if (status) status.textContent = "";
    try {
      const meta = await fetchMeta();
      const geos = o.geos(state);
      const [loaded, stats] = await Promise.all([
        Promise.all(geos.map((g) => fetchGeo(g, o.kinds))),
        o.withStats ? fetchStats() : Promise.resolve(undefined),
      ]);
      if (mine !== request) return; // a newer selection won
      const data = Object.fromEntries(geos.map((g, i) => [g, loaded[i]]));
      o.root.innerHTML = o.render(makeCtx(o.lang, meta), state, data, stats);
      o.onRendered?.();
      if (pushUrl) writeQuery(state, defaults);
    } catch {
      if (status && mine === request) status.textContent = status.dataset.errorText ?? "Error";
    } finally {
      if (mine === request) {
        o.root.classList.remove("is-loading");
        o.root.removeAttribute("aria-busy");
      }
    }
  }

  o.form.addEventListener("change", () => {
    state = formState(o.form, state);
    void update(true);
  });
  o.form.addEventListener("submit", (e) => e.preventDefault());

  // The static HTML shows the defaults; re-render only if the URL asks for something else.
  writeForm(o.form, state);
  if (JSON.stringify(state) !== JSON.stringify(defaults)) void update(false);
}
