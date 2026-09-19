// Filtered views for the programme, skills and salaries pages. Each renders the selected region
// next to the national figure (FR-07), like the overview.

import { fmtInt, fmtPct } from "../lib/format";
import { countVacancies, isIndicative, share, window } from "../lib/model";
import type { GeoData } from "../lib/types";
import { rolesCard, salaryCard, skillsCard } from "./blocks";
import { type Ctx, type FilterState, geoName, indicativeBadge, tile, windowLabel } from "./common";

export const geosFor = (s: FilterState) => (s.geo === "nl" ? ["nl"] : [s.geo, "nl"]);

function panels(ctx: Ctx, state: FilterState, render: (geoId: string) => string): string {
  const geos = geosFor(state);
  return `<div class="panels panels-${geos.length}">${geos.map((g) => {
    const id = `panel-${g.replace(":", "-")}`;
    return `<section class="panel" aria-labelledby="${id}"><h2 id="${id}">${geoName(ctx, g)}</h2>${render(g)}</section>`;
  }).join("")}</div>`;
}

export const PROGRAMME_KINDS: (keyof GeoData)[] = ["vacancies", "skills", "families", "titles", "salaries"];

/** FR-02: volume, top 15 skills, typical titles, salary; for one programme. */
export function renderProgramme(programme: string) {
  return (ctx: Ctx, state: FilterState, data: Record<string, GeoData>): string => {
    const { lang, tr, meta } = ctx;
    const win = window(meta.vacancies.months, state.period);
    return panels(ctx, state, (g) => {
      const d = data[g];
      const n = countVacancies(d.vacancies, win.months, programme, state.seniority);
      const all = countVacancies(d.vacancies, win.months, programme, "all");
      const entry = countVacancies(d.vacancies, win.months, programme, "entry");
      const ictAll = countVacancies(d.vacancies, win.months, "all", "all");
      const tiles = `<div class="tiles">`
        + tile({ label: lang === "nl" ? "Passende vacatures" : "Matching vacancies", value: fmtInt(lang, n),
                 sub: `${windowLabel(ctx, win)} · ${fmtPct(lang, share(all, ictAll))} ${lang === "nl" ? "van alle ICT-vacatures" : "of all ICT vacancies"}`,
                 badges: isIndicative(n, meta.min_sample_size) ? [indicativeBadge(ctx)] : [] })
        + tile({ label: tr.seniority.entry, value: fmtPct(lang, share(entry, all)),
                 sub: `${fmtInt(lang, entry)} ${lang === "nl" ? "van" : "of"} ${fmtInt(lang, all)}` })
        + `</div>`;
      return tiles
        + skillsCard(ctx, d, win, g, programme, state.seniority, 15)
        + rolesCard(ctx, d, win, programme)
        + salaryCard(ctx, d, win, g, programme);
    });
  };
}

export const SKILLS_KINDS: (keyof GeoData)[] = ["vacancies", "skills"];

/** FR-03: most requested skills, filterable by programme and level, with change. */
export function renderSkills(ctx: Ctx, state: FilterState, data: Record<string, GeoData>): string {
  const win = window(ctx.meta.vacancies.months, state.period);
  return panels(ctx, state, (g) => skillsCard(ctx, data[g], win, g, state.programme, state.seniority, 25,
    ctx.lang === "nl" ? "Meest gevraagde skills" : "Most requested skills"));
}

export const SALARY_KINDS: (keyof GeoData)[] = ["salaries"];

/** FR-04 (vacancy part): salary ranges by level, with sample sizes. */
export function renderSalaries(ctx: Ctx, state: FilterState, data: Record<string, GeoData>): string {
  const win = window(ctx.meta.vacancies.months, state.period);
  return panels(ctx, state, (g) => salaryCard(ctx, data[g], win, g, state.programme));
}
