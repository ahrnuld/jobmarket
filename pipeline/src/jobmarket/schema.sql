-- Working store for the pipeline (SQLite). The public site never queries this database.
-- DR-01: every stored record carries source_id, retrieved_at and licence.
-- Durable trend history lives in data/aggregates/*.csv, not here: this file may be rebuilt.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER NOT NULL
);

-- Mirror of data/reference/sources.yaml, refreshed on every run (LR-01: licence terms per source).
CREATE TABLE IF NOT EXISTS sources (
    id                  TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    url                 TEXT NOT NULL,
    licence             TEXT NOT NULL,
    licence_url         TEXT,
    attribution         TEXT,
    raw_retention_days  INTEGER,          -- NULL = no raw text stored at all
    terms_checked_on    TEXT,             -- ISO date the owner last verified the terms
    release             TEXT NOT NULL     -- 'mvp' | 'phase2'
);

-- FR-20: ingestion status, errors and record counts per source.
CREATE TABLE IF NOT EXISTS ingestion_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id       TEXT NOT NULL REFERENCES sources(id),
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    status          TEXT NOT NULL CHECK (status IN ('running', 'success', 'failed')),
    records_fetched INTEGER NOT NULL DEFAULT 0,
    records_new     INTEGER NOT NULL DEFAULT 0,
    error           TEXT
);

-- One row per vacancy as received from a source, after PII scrubbing (LR-03).
-- description is set to NULL once the source's raw_retention_days has passed (DR-07).
CREATE TABLE IF NOT EXISTS vacancies (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id            TEXT NOT NULL REFERENCES sources(id),
    external_id          TEXT NOT NULL,
    run_id               INTEGER REFERENCES ingestion_runs(id),
    retrieved_at         TEXT NOT NULL,
    licence              TEXT NOT NULL,
    is_sample            INTEGER NOT NULL DEFAULT 0,   -- 1 = synthetic fixture data, never real

    title                TEXT NOT NULL,
    employer             TEXT,
    location_raw         TEXT,
    area_json            TEXT,               -- source-provided location hierarchy
    description          TEXT,               -- scrubbed text; purged after retention window
    description_purged_at TEXT,
    source_category      TEXT,
    posted_at            TEXT NOT NULL,      -- ISO date
    salary_min           REAL,
    salary_max           REAL,
    salary_is_predicted  INTEGER,            -- 1 = estimated by source, not stated in posting
    contract_time        TEXT,
    url                  TEXT,

    -- Derived by clean/ and classify/ (recomputed on every run)
    title_norm           TEXT,
    employer_norm        TEXT,
    location_norm        TEXT,
    municipality         TEXT,
    labour_market_region TEXT,
    province             TEXT,
    language             TEXT,               -- 'nl' | 'en' | 'unknown' (DR-06)
    duplicate_of         INTEGER REFERENCES vacancies(id),   -- DR-02
    is_ict               INTEGER,
    seniority            TEXT CHECK (seniority IN ('internship', 'junior', 'medior', 'senior', 'unknown')),
    classifier_version   TEXT,
    classified_at        TEXT,

    UNIQUE (source_id, external_id)
);

CREATE INDEX IF NOT EXISTS ix_vacancies_posted ON vacancies (posted_at);
CREATE INDEX IF NOT EXISTS ix_vacancies_dedupe ON vacancies (title_norm, employer_norm, location_norm);

-- DR-04: zero or more programmes per vacancy, via a role family.
CREATE TABLE IF NOT EXISTS vacancy_programmes (
    vacancy_id   INTEGER NOT NULL REFERENCES vacancies(id) ON DELETE CASCADE,
    programme_id TEXT NOT NULL,
    role_family  TEXT NOT NULL,
    PRIMARY KEY (vacancy_id, programme_id)
);

-- DR-05: skills linked to ESCO.
CREATE TABLE IF NOT EXISTS vacancy_skills (
    vacancy_id  INTEGER NOT NULL REFERENCES vacancies(id) ON DELETE CASCADE,
    skill_id    TEXT NOT NULL,
    esco_uri    TEXT,
    PRIMARY KEY (vacancy_id, skill_id)
);

-- Published statistics (CBS, UWV, ROA, HBO-Monitor). One row per observation.
CREATE TABLE IF NOT EXISTS stat_observations (
    source_id     TEXT NOT NULL REFERENCES sources(id),
    series_id     TEXT NOT NULL,          -- e.g. 'cbs_vacancies_ict'
    period        TEXT NOT NULL,          -- '2025Q3', '2025', '2025-2030'
    period_start  TEXT NOT NULL,          -- ISO date, for sorting and time filters
    region        TEXT NOT NULL DEFAULT 'NL',
    breakdown     TEXT NOT NULL DEFAULT '',   -- e.g. programme id or sector code
    value         REAL,
    unit          TEXT NOT NULL,
    sample_size   INTEGER,
    published_at  TEXT,                   -- date the source published the figure
    retrieved_at  TEXT NOT NULL,
    licence       TEXT NOT NULL,
    source_url    TEXT,
    is_sample     INTEGER NOT NULL DEFAULT 0,
    note          TEXT,
    PRIMARY KEY (source_id, series_id, period, region, breakdown)
);

-- Publication attempts; only validated snapshots reach the site (NFR-07).
CREATE TABLE IF NOT EXISTS snapshots (
    id                 TEXT PRIMARY KEY,   -- UTC timestamp
    created_at         TEXT NOT NULL,
    status             TEXT NOT NULL CHECK (status IN ('published', 'rejected')),
    validation_report  TEXT NOT NULL       -- JSON
);
