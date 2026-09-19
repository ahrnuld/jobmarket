// Internship view (FR-12): where internship postings are, for which programme, asking which skills.
// Built at build time from every region's data; the period switch toggles pre-rendered variants.

import { barList, table } from "../lib/charts";
import { fmtInt, fmtPct } from "../lib/format";
import { byProgramme, countVacancies, isIndicative, share, topSkills, type Period, window } from "../lib/model";
import type { GeoData } from "../lib/types";
import {
  card, type Ctx, geoName, indicativeBadge, programmeName, provenance, skillLabel, tile, vacancyUpdated,
  windowLabel,
} from "./common";

export function renderInternships(ctx: Ctx, period: Period, geos: Record<string, GeoData>): string {
  const { lang, tr, meta } = ctx;
  const win = window(meta.vacancies.months, period);
  const min = meta.min_sample_size;
  const nl = geos.nl;
  const interns = countVacancies(nl.vacancies, win.months, "all", "internship");
  const entry = countVacancies(nl.vacancies, win.months, "all", "entry");
  const ict = countVacancies(nl.vacancies, win.months);
  const nh = geos["p:noord-holland"] ? countVacancies(geos["p:noord-holland"].vacancies, win.months, "all", "internship") : 0;
  const badge = (n: number) => (isIndicative(n, min) ? [indicativeBadge(ctx)] : []);
  const out: string[] = [];

  out.push(`<div class="tiles">`
    + tile({ label: lang === "nl" ? "Stagevacatures in Nederland" : "Internship postings in the Netherlands",
             value: fmtInt(lang, interns), sub: `${windowLabel(ctx, win)} · ${fmtPct(lang, share(interns, ict), 1)} ${lang === "nl" ? "van alle ICT-vacatures" : "of all ICT vacancies"}`,
             badges: badge(interns) })
    + tile({ label: lang === "nl" ? "Waarvan in Noord-Holland" : "Of which in Noord-Holland", value: fmtInt(lang, nh),
             sub: fmtPct(lang, share(nh, interns)), badges: badge(nh) })
    + tile({ label: tr.seniority.entry, value: fmtInt(lang, entry),
             sub: lang === "nl" ? "stages plus juniorfuncties" : "internships plus junior roles" })
    + `</div>`);

  // Regions: labour market regions ranked by internship postings
  const regions = meta.geos.filter((g) => g.level === "region" && geos[g.id]).map((g) => ({
    id: g.id,
    interns: countVacancies(geos[g.id].vacancies, win.months, "all", "internship"),
    entry: countVacancies(geos[g.id].vacancies, win.months, "all", "entry"),
  })).filter((r) => r.interns > 0).sort((a, b) => b.interns - a.interns || b.entry - a.entry).slice(0, 15);
  out.push(card(ctx, { headingLevel: 2,
    title: lang === "nl" ? "Regio's met de meeste stagevacatures" : "Regions with the most internship postings",
    subtitle: lang === "nl"
      ? "Arbeidsmarktregio's. Stages worden vaak niet als vacature geplaatst maar via de hogeschool of het netwerk gevonden; deze aantallen zijn dus een ondergrens."
      : "Labour market regions. Internships are often found through the university or personal network rather than a posting, so these numbers are a lower bound.",
    body: barList(regions.map((r) => ({
      label: geoName(ctx, r.id), value: r.interns,
      valueText: `${fmtInt(lang, r.interns)} · ${lang === "nl" ? "stage+junior" : "intern+junior"} ${fmtInt(lang, r.entry)}`,
      tip: `${geoName(ctx, r.id)}: ${fmtInt(lang, r.interns)} ${lang === "nl" ? "stages" : "internships"}, ${fmtInt(lang, r.entry)} ${tr.seniority.entry.toLowerCase()}`,
    })), lang === "nl" ? "Stagevacatures per regio" : "Internship postings by region", tr.chart.noData),
    provenance: provenance(ctx, { sourceIds: [meta.vacancy_source], updated: vacancyUpdated(ctx), n: interns }),
    table: table(lang === "nl" ? "Regio's" : "Regions", [tr.filters.region, tr.seniority.internship, tr.seniority.entry],
                 regions.map((r) => [geoName(ctx, r.id), fmtInt(lang, r.interns), fmtInt(lang, r.entry)])),
    badges: badge(interns),
  }));

  // Programmes
  const progIds = meta.programmes.map((p) => p.id);
  const perProg = byProgramme(nl.vacancies, win.months, progIds, "internship");
  out.push(card(ctx, { headingLevel: 2,
    title: lang === "nl" ? "Stagevacatures per opleiding" : "Internship postings by programme",
    subtitle: geoName(ctx, "nl"),
    body: barList(progIds.map((p) => ({
      label: programmeName(ctx, p), value: perProg[p], valueText: fmtInt(lang, perProg[p]),
      tip: `${programmeName(ctx, p)}: ${fmtInt(lang, perProg[p])}`, muted: isIndicative(perProg[p], min),
    })), lang === "nl" ? "Stages per opleiding" : "Internships by programme", tr.chart.noData),
    provenance: provenance(ctx, { sourceIds: [meta.vacancy_source], updated: vacancyUpdated(ctx), n: interns }),
    table: table(tr.filters.programme, [tr.filters.programme, tr.chart.count], progIds.map((p) => [programmeName(ctx, p), fmtInt(lang, perProg[p])])),
  }));

  // Skills in internship and junior postings (entry: larger sample than internships alone)
  const skills = topSkills(nl.skills, nl.vacancies, win, "all", "entry", 12);
  out.push(card(ctx, { headingLevel: 2,
    title: lang === "nl" ? "Skills in stage- en juniorvacatures" : "Skills in internship and junior postings",
    subtitle: lang === "nl"
      ? `Aandeel van ${fmtInt(lang, skills.total)} stage- en juniorvacatures in Nederland dat de skill noemt.`
      : `Share of ${fmtInt(lang, skills.total)} internship and junior postings in the Netherlands mentioning the skill.`,
    body: barList(skills.items.map((s) => ({
      label: skillLabel(ctx, s.id), value: s.share, valueText: fmtPct(lang, s.share),
      tip: `${skillLabel(ctx, s.id)}: ${fmtPct(lang, s.share)} (${fmtInt(lang, s.n)})`, muted: isIndicative(skills.total, min),
    })), "Skills", tr.chart.noData),
    provenance: provenance(ctx, { sourceIds: [meta.vacancy_source, "esco"], updated: vacancyUpdated(ctx), n: skills.total }),
    table: table("Skills", ["Skill", tr.chart.count, tr.chart.share], skills.items.map((s) => [skillLabel(ctx, s.id), fmtInt(lang, s.n), fmtPct(lang, s.share)])),
    badges: badge(skills.total),
  }));
  return out.join("");
}
