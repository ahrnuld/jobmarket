// Interface texts in Dutch and English (FR-10). Page-level prose lives in the page files.

import type { Lang } from "./lib/types";

export const LANGS: Lang[] = ["nl", "en"];

const strings = {
  siteName: { nl: "ICT-arbeidsmarkt voor hbo-studenten", en: "ICT job market for HBO students" },
  siteShort: { nl: "ICT-arbeidsmarkt", en: "ICT job market" },
  skipToContent: { nl: "Naar de inhoud", en: "Skip to content" },
  nav: {
    dashboard: { nl: "Overzicht", en: "Overview" },
    programmes: { nl: "Opleidingen", en: "Programmes" },
    map: { nl: "Kaart", en: "Map" },
    skills: { nl: "Skills", en: "Skills" },
    salaries: { nl: "Salarissen", en: "Salaries" },
    trends: { nl: "Trends", en: "Trends" },
    internships: { nl: "Stages", en: "Internships" },
    data: { nl: "Data", en: "Data" },
    methodology: { nl: "Methode", en: "Method" },
    about: { nl: "Over", en: "About" },
  },
  otherLanguage: { nl: "English", en: "Nederlands" },
  independent: {
    nl: "Onafhankelijk initiatief, niet van of namens een hogeschool.",
    en: "Independent initiative, not by or on behalf of any university of applied sciences.",
  },
  filters: {
    label: { nl: "Filters", en: "Filters" },
    region: { nl: "Regio", en: "Region" },
    period: { nl: "Periode", en: "Period" },
    seniority: { nl: "Niveau", en: "Level" },
    programme: { nl: "Opleiding", en: "Programme" },
    allProgrammes: { nl: "Alle ICT-vacatures", en: "All ICT vacancies" },
    loading: { nl: "Gegevens laden…", en: "Loading data…" },
    loadError: {
      nl: "Deze selectie kon niet worden geladen. De getoonde cijfers horen bij de vorige selectie.",
      en: "This selection could not be loaded. The figures shown belong to the previous selection.",
    },
  },
  periods: {
    "3m": { nl: "Laatste 3 maanden", en: "Last 3 months" },
    "6m": { nl: "Laatste 6 maanden", en: "Last 6 months" },
    "12m": { nl: "Laatste 12 maanden", en: "Last 12 months" },
    all: { nl: "Alles sinds de start", en: "All since the start" },
  },
  seniority: {
    all: { nl: "Alle niveaus", en: "All levels" },
    entry: { nl: "Stage + junior", en: "Internship + junior" },
    internship: { nl: "Stage", en: "Internship" },
    junior: { nl: "Junior", en: "Junior" },
    medior: { nl: "Medior", en: "Medior" },
    senior: { nl: "Senior", en: "Senior" },
    unknown: { nl: "Niveau onbekend", en: "Level unknown" },
  },
  levels: {
    country: { nl: "Land", en: "Country" },
    province: { nl: "Provincies", en: "Provinces" },
    region: { nl: "Arbeidsmarktregio's", en: "Labour market regions" },
  },
  chart: {
    source: { nl: "Bron", en: "Source" },
    updated: { nl: "bijgewerkt", en: "updated" },
    basedOn: { nl: "gebaseerd op", en: "based on" },
    vacancies: { nl: "vacatures", en: "vacancies" },
    vacancy: { nl: "vacature", en: "vacancy" },
    records: { nl: "records", en: "records" },
    showTable: { nl: "Toon als tabel", en: "Show as table" },
    indicative: { nl: "Indicatief", en: "Indicative" },
    indicativeExplain: {
      nl: "Gebaseerd op minder dan {min} records: behandel dit als een aanwijzing, niet als een vaststaand cijfer.",
      en: "Based on fewer than {min} records: treat this as a hint, not an established figure.",
    },
    sample: { nl: "Voorbeelddata", en: "Example data" },
    sampleExplain: {
      nl: "Dit zijn geen echte cijfers. Ze staan er om de pagina te kunnen tonen tot de echte cijfers zijn ingevoerd.",
      en: "These are not real figures. They are shown so the page works until the real figures are entered.",
    },
    partial: { nl: "deels", en: "partial" },
    partialExplain: {
      nl: "Lichtere kolommen zijn maanden die nog niet compleet zijn (de lopende maand, of de maand waarin de reeks begon).",
      en: "Lighter columns are months that are not complete (the current month, or the month the series started in).",
    },
    provisional: { nl: "voorlopig", en: "provisional" },
    noData: { nl: "Geen gegevens voor deze selectie.", en: "No data for this selection." },
    month: { nl: "Maand", en: "Month" },
    count: { nl: "Aantal", en: "Count" },
    share: { nl: "Aandeel", en: "Share" },
    change: { nl: "Verschil", en: "Change" },
    vsPrevious: { nl: "t.o.v. vorige periode", en: "vs previous period" },
    noPrevious: { nl: "geen vergelijking: te weinig historie", en: "no comparison: not enough history" },
    period: { nl: "Periode", en: "Period" },
    value: { nl: "Waarde", en: "Value" },
  },
  banner: {
    sampleVacancies: {
      nl: "Let op: de vacaturecijfers op deze site zijn synthetische voorbeelddata, geen echte vacatures.",
      en: "Note: the vacancy figures on this site are synthetic example data, not real vacancies.",
    },
    preview: {
      nl: "Testversie: de methode is nog niet getoetst op een handmatig gelabelde steekproef en sommige bronnen bevatten nog voorbeeldwaarden.",
      en: "Test version: the method has not yet been checked against a manually labelled sample and some sources still contain example values.",
    },
    seriesStart: {
      nl: "De vacaturereeks begint op {date}. Trends over langere perioden worden zichtbaar naarmate er meer maanden bijkomen.",
      en: "The vacancy series starts on {date}. Trends over longer periods become visible as more months are added.",
    },
  },
  footer: {
    dataBy: { nl: "Vacaturedata", en: "Vacancy data" },
    snapshot: { nl: "Gegevens van", en: "Data as of" },
    noTracking: {
      nl: "Deze site gebruikt geen cookies en volgt je niet.",
      en: "This site uses no cookies and does not track you.",
    },
    report: { nl: "Fout gezien? Meld het", en: "Spotted an error? Report it" },
    download: { nl: "Data downloaden (CSV)", en: "Download data (CSV)" },
  },
};

export type Strings = typeof strings;

export function t(lang: Lang) {
  // Resolve every { nl, en } leaf to the chosen language, keeping the nested structure.
  const pick = (node: unknown): unknown => {
    if (node && typeof node === "object" && "nl" in node && "en" in node) {
      return (node as Record<Lang, string>)[lang];
    }
    return Object.fromEntries(Object.entries(node as object).map(([k, v]) => [k, pick(v)]));
  };
  return pick(strings) as Resolved<Strings>;
}

type Resolved<T> = T extends { nl: string; en: string }
  ? string
  : { [K in keyof T]: Resolved<T[K]> };

export function fill(template: string, values: Record<string, string | number>): string {
  return template.replace(/\{(\w+)\}/g, (_, k) => String(values[k] ?? `{${k}}`));
}

/** Path helpers: every page exists under /nl/ and /en/. */
export function path(lang: Lang, ...parts: string[]): string {
  const rest = parts.filter(Boolean).join("/");
  return `/${lang}/${rest ? rest + "/" : ""}`;
}

export function otherLang(lang: Lang): Lang {
  return lang === "nl" ? "en" : "nl";
}
