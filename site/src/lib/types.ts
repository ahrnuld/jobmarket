// Shapes of the files the pipeline publishes to public/data (see pipeline/src/jobmarket/publish.py).

export type Lang = "nl" | "en";
export type I18nText = Record<Lang, string>;

export interface MonthInfo {
  month: string; // "2026-08"
  partial: boolean;
}

export interface SourceInfo {
  id: string;
  name: string;
  url: string;
  licence: string;
  licence_url: string | null;
  attribution: string | null;
  terms_checked_on: string | null;
  used: boolean;
  last_success_at: string | null;
  last_run_status: string | null;
  last_error: string | null;
}

export interface Programme {
  id: string;
  name: I18nText;
  summary: I18nText;
  locations: string[];
}

export interface RoleFamily {
  id: string;
  name: I18nText;
  programmes: string[];
}

export interface SkillInfo {
  id: string;
  label: string;
  category: string;
  esco_uri: string | null;
  esco_label: string | null;
  esco_checked: boolean;
}

export interface GeoInfo {
  id: string; // "nl", "p:noord-holland", "r:groot-amsterdam"
  level: "country" | "province" | "region";
  name: I18nText;
  parent: string | null;
}

export interface ChangelogEntry {
  date: string;
  version: string;
  title: I18nText;
  body: I18nText;
  series_break: string[];
}

export interface Accuracy {
  measured_on: string;
  n: number;
  [metric: string]: unknown;
}

export interface Meta {
  snapshot_id: string;
  generated_at: string;
  production: boolean;
  dataset: "real" | "sample";
  classifier_version: string;
  min_sample_size: number;
  vacancy_source: string;
  vacancies: { months: MonthInfo[]; first_posted: string | null; last_posted: string | null };
  sources: SourceInfo[];
  programmes: Programme[];
  role_families: RoleFamily[];
  skills: SkillInfo[];
  geos: GeoInfo[];
  changelog: ChangelogEntry[];
  accuracy: Accuracy | null;
  validation: { ok: boolean; errors: string[]; warnings: string[] };
}

// Row tuples; month index points into meta.vacancies.months.
export type VacancyRow = [mi: number, programme: string, seniority: string, n: number];
export type SkillRow = [mi: number, programme: string, seniority: string, skill: string, n: number];
export type FamilyRow = [mi: number, programme: string, family: string, n: number];
export type TitleRow = [mi: number, programme: string, title: string, n: number];
export type SalaryRow = [mi: number, programme: string, seniority: string, bucket: number, n: number];

export interface GeoData {
  vacancies: VacancyRow[];
  skills: SkillRow[];
  families: FamilyRow[];
  titles: TitleRow[];
  salaries: SalaryRow[];
}

export interface StatSeries {
  source: string;
  origin?: string | null; // underlying source of a figure shown via another source
  unit: string;
  title: I18nText;
  note?: I18nText | null;
  frequency?: string;
  table?: string;
}

export interface Observation {
  series: string;
  source: string;
  period: string;
  start: string;
  region: string;
  breakdown: string;
  value: number | null;
  label: string | null;
  n: number | null;
  published: string | null;
  retrieved: string;
  url: string | null;
  sample: boolean;
  note: string | null;
}

export interface Stats {
  series: Record<string, StatSeries>;
  observations: Observation[];
}
