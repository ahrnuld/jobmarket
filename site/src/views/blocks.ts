// Chart cards reused on several pages: skills, roles and titles, salary ranges.

import { barList, ranges, table } from "../lib/charts";
import { escapeHtml as esc, fmtEuro, fmtInt, fmtPct, fmtPp, roundTo } from "../lib/format";
import { isIndicative, salaryStats, topFamilies, topSkills, topTitles, type Window } from "../lib/model";
import type { GeoData } from "../lib/types";
import {
  card, type Ctx, familyName, geoName, indicativeBadge, programmeName, provenance, seniorityName,
  skillLabel, vacancyUpdated,
} from "./common";

export function skillsCard(ctx: Ctx, data: GeoData, win: Window, geoId: string, programme: string,
                           seniority: string, limit = 15, title?: string): string {
  const { lang, tr, meta } = ctx;
  const res = topSkills(data.skills, data.vacancies, win, programme, seniority, limit);
  const indicative = isIndicative(res.total, meta.min_sample_size);
  const items = res.items.map((s) => ({
    label: skillLabel(ctx, s.id),
    value: s.share,
    valueText: s.change === null ? fmtPct(lang, s.share) : `${fmtPct(lang, s.share)} · ${fmtPp(lang, s.change)}`,
    tip: `${skillLabel(ctx, s.id)}: ${fmtPct(lang, s.share)} (${fmtInt(lang, s.n)} ${lang === "nl" ? "van" : "of"} ${fmtInt(lang, res.total)})`
      + (s.change === null ? "" : `, ${fmtPp(lang, s.change)} ${tr.chart.vsPrevious}`),
    muted: indicative,
  }));
  const subtitle = lang === "nl"
    ? `Aandeel van de ${fmtInt(lang, res.total)} vacatures (${lcFirst(programmeName(ctx, programme))}, ${lcFirst(seniorityName(ctx, seniority))}) dat de skill noemt in de titel of de eerste ~500 tekens.`
      + (res.previousTotal === null ? ` (${tr.chart.noPrevious})` : "")
    : `Share of the ${fmtInt(lang, res.total)} vacancies (${lcFirst(programmeName(ctx, programme))}, ${lcFirst(seniorityName(ctx, seniority))}) mentioning the skill in the title or first ~500 characters.`
      + (res.previousTotal === null ? ` (${tr.chart.noPrevious})` : "");
  const skillMeta = (id: string) => meta.skills.find((s) => s.id === id);
  return card(ctx, {
    title: title ?? (lang === "nl" ? `Top ${limit} gevraagde skills` : `Top ${limit} requested skills`),
    subtitle,
    body: barList(items, `${geoName(ctx, geoId)}: skills`, tr.chart.noData),
    provenance: provenance(ctx, { sourceIds: [meta.vacancy_source, "esco"], updated: vacancyUpdated(ctx), n: res.total }),
    table: table("Skills", ["Skill", tr.chart.count, tr.chart.share, `${tr.chart.change} (${tr.chart.vsPrevious})`, "ESCO"],
      res.items.map((s) => [skillLabel(ctx, s.id), fmtInt(lang, s.n), fmtPct(lang, s.share, 1),
                            fmtPp(lang, s.change), skillMeta(s.id)?.esco_label ?? "–"])),
    badges: indicative ? [indicativeBadge(ctx)] : [],
  });
}

/** Lowercase only the first letter, so abbreviations such as ICT keep their capitals. */
const lcFirst = (s: string) => s.charAt(0).toLowerCase() + s.slice(1);

/** Titles are published normalised (lowercase); restore a capital, but leave ".net" alone. */
const capitalise = (s: string) => (/^[a-z]/.test(s) ? s[0].toUpperCase() + s.slice(1) : s);

export function rolesCard(ctx: Ctx, data: GeoData, win: Window, programme: string): string {
  const { lang, tr, meta } = ctx;
  const fams = topFamilies(data.families, win.months, programme, 8);
  const titles = topTitles(data.titles, win.months, programme, 10);
  const famTotal = fams.reduce((t, f) => t + f.n, 0);
  const famList = barList(fams.map((f) => ({
    label: familyName(ctx, f.id), value: f.n, valueText: fmtInt(lang, f.n),
    tip: `${familyName(ctx, f.id)}: ${fmtInt(lang, f.n)} ${tr.chart.vacancies}`,
  })), lang === "nl" ? "Soorten functies" : "Types of role", tr.chart.noData);
  const titleList = titles.length
    ? `<ol class="list-plain">${titles.map((x) => `<li><span>${esc(capitalise(x.title))}</span><span class="muted num">${fmtInt(lang, x.n)}</span></li>`).join("")}</ol>`
    : `<p class="empty">${esc(tr.chart.noData)}</p>`;
  return card(ctx, {
    title: lang === "nl" ? "Typische functies" : "Typical roles",
    subtitle: lang === "nl"
      ? "Soorten functies (functiefamilies) en de vaakst voorkomende functietitels, zonder niveauwoorden als junior of senior. Alleen titels die minstens 3 keer voorkomen."
      : "Types of role (role families) and the most common job titles, without level words such as junior or senior. Only titles that occur at least 3 times.",
    body: `<div class="grid-2"><div><h4 class="visually-hidden">${lang === "nl" ? "Functiefamilies" : "Role families"}</h4>${famList}</div>`
      + `<div><h4 class="card-sub">${lang === "nl" ? "Vaakst gebruikte titels" : "Most used titles"}</h4>${titleList}</div></div>`,
    provenance: provenance(ctx, { sourceIds: [meta.vacancy_source], updated: vacancyUpdated(ctx), n: famTotal }),
    table: table(lang === "nl" ? "Functiefamilies" : "Role families",
                 [lang === "nl" ? "Functiefamilie" : "Role family", tr.chart.count],
                 fams.map((f) => [familyName(ctx, f.id), fmtInt(lang, f.n)])),
  });
}

/** Monthly gross salary: annual amounts from postings divided by 12, rounded to 50 euro. */
export const monthlyFromAnnual = (annual: number) => roundTo(annual / 12, 50);

export function salaryCard(ctx: Ctx, data: GeoData, win: Window, geoId: string, programme: string,
                           levels = ["entry", "junior", "medior", "senior", "all"]): string {
  const { lang, tr, meta } = ctx;
  const min = meta.min_sample_size;
  const stats = levels.map((lvl) => ({ lvl, s: salaryStats(data.salaries, win.months, programme, lvl) }));
  const rows = stats.filter((x) => x.s.n > 0).map(({ lvl, s }) => ({
    label: `${seniorityName(ctx, lvl)} (n=${fmtInt(lang, s.n)})`,
    p25: monthlyFromAnnual(s.p25!), median: monthlyFromAnnual(s.median!), p75: monthlyFromAnnual(s.p75!),
    tip: `${seniorityName(ctx, lvl)}: ${lang === "nl" ? "mediaan" : "median"} ${fmtEuro(lang, monthlyFromAnnual(s.median!))}, `
      + `${lang === "nl" ? "middelste helft" : "middle half"} ${fmtEuro(lang, monthlyFromAnnual(s.p25!))} – ${fmtEuro(lang, monthlyFromAnnual(s.p75!))} (n=${s.n})`,
    muted: isIndicative(s.n, min),
  }));
  const total = stats.find((x) => x.lvl === "all")?.s.n ?? 0;
  const anyIndicative = rows.some((r) => r.muted);
  return card(ctx, {
    title: lang === "nl" ? "Salaris in vacatures (bruto per maand)" : "Salary in vacancies (gross per month)",
    subtitle: lang === "nl"
      ? `${geoName(ctx, geoId)}, ${lcFirst(programmeName(ctx, programme))}. Balk: de middelste helft van de genoemde salarissen; streep: de mediaan. Alleen vacatures die zelf een salaris noemen; jaarbedragen gedeeld door 12.`
      : `${geoName(ctx, geoId)}, ${lcFirst(programmeName(ctx, programme))}. Bar: the middle half of the stated salaries; mark: the median. Only postings that state a salary; annual amounts divided by 12.`,
    body: ranges(rows, lang === "nl" ? "Salarisbereik per niveau" : "Salary range by level", tr.chart.noData,
                 (n) => fmtEuro(lang, n)),
    provenance: provenance(ctx, { sourceIds: [meta.vacancy_source], updated: vacancyUpdated(ctx), n: total,
                                  unit: lang === "nl" ? "vacatures met salaris" : "vacancies with a salary" }),
    table: table(lang === "nl" ? "Salaris" : "Salary",
      [tr.filters.seniority, "n", "25%", lang === "nl" ? "Mediaan" : "Median", "75%"],
      stats.map(({ lvl, s }) => [seniorityName(ctx, lvl), fmtInt(lang, s.n),
        s.p25 === null ? "–" : fmtEuro(lang, monthlyFromAnnual(s.p25)),
        s.median === null ? "–" : fmtEuro(lang, monthlyFromAnnual(s.median)),
        s.p75 === null ? "–" : fmtEuro(lang, monthlyFromAnnual(s.p75))])),
    badges: anyIndicative ? [indicativeBadge(ctx)] : [],
  });
}
