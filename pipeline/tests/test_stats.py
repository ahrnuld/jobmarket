from __future__ import annotations

import urllib.parse

import pytest

from jobmarket.config import REPO_ROOT
from jobmarket.db import connect, init_schema
from jobmarket.stats import load_series_config
from jobmarket.stats.cbs import CbsClient, parse_period
from jobmarket.stats.manual import ManualDataError, read_file
from jobmarket.stats.run import refresh_cbs, refresh_manual


def test_parse_period():
    assert parse_period("2025KW03") == ("2025Q3", "2025-07-01", "quarter")
    assert parse_period("2024JJ00") == ("2024", "2024-01-01", "year")
    assert parse_period("2024MM02") == ("2024-02", "2024-02-01", "month")
    assert parse_period("2023SJ00") is None


class FakeCbs:
    """Mimics the StatLine API, including its space-padded dimension keys."""

    def __init__(self):
        self.urls = []

    def __call__(self, url):
        self.urls.append(url)
        path = urllib.parse.urlparse(url).path
        if path.endswith("/TableInfos"):
            return {"value": [{"Modified": "2026-07-30T06:30:00"}]}
        if path.endswith("/Perioden"):
            return {
                "value": [
                    {"Key": "2026KW01", "Status": "Definitief"},
                    {"Key": "2026KW02", "Status": "Voorlopig"},
                ]
            }
        if path.endswith("/SBI2008PartBedrijvenOverheid"):
            return {"value": [{"Key": "391600  "}, {"Key": "T001081 "}]}
        if path.endswith("/TypedDataSet"):
            return {
                "value": [
                    {
                        "SBI2008PartBedrijvenOverheid": "391600  ",
                        "Perioden": "2026KW01",
                        "V_1": 20.5,
                    },
                    {
                        "SBI2008PartBedrijvenOverheid": "391600  ",
                        "Perioden": "2026KW02",
                        "V_1": 21.0,
                    },
                    {
                        "SBI2008PartBedrijvenOverheid": "391600  ",
                        "Perioden": "2025JJ00",
                        "V_1": 19.0,
                    },
                ],
                "odata.nextLink": None,
            }
        raise AssertionError(url)


SERIES = {
    "series_id": "test_series",
    "table": "80474ned",
    "measure": "V_1",
    "multiplier": 1000,
    "unit": "vacancies",
    "frequency": "quarter",
    "filters": {"SBI2008PartBedrijvenOverheid": "391600"},
}


def test_cbs_uses_padded_keys_and_marks_provisional():
    fake = FakeCbs()
    obs = CbsClient(fetch=fake).fetch_series(SERIES)
    typed_url = next(u for u in fake.urls if "TypedDataSet" in u)
    assert urllib.parse.quote("'391600  '") in typed_url
    assert [(o.period, o.value, o.note) for o in obs] == [
        ("2026Q1", 20500.0, None),
        ("2026Q2", 21000.0, "voorlopig"),
    ]  # yearly row skipped
    assert obs[0].published_at == "2026-07-30"


def test_cbs_unknown_key_fails_loudly():
    with pytest.raises(ValueError, match="not found"):
        CbsClient(fetch=FakeCbs()).fetch_series(
            {**SERIES, "filters": {"SBI2008PartBedrijvenOverheid": "999"}}
        )


def test_failed_cbs_run_keeps_old_data(conn, ref):
    refresh_cbs(conn, ref, {"cbs": [SERIES]}, CbsClient(fetch=FakeCbs()))
    broken = {"cbs": [{**SERIES, "filters": {"SBI2008PartBedrijvenOverheid": "999"}}]}
    result = refresh_cbs(conn, ref, broken, CbsClient(fetch=FakeCbs()))
    assert result.status == "failed"
    assert conn.execute("SELECT COUNT(*) FROM stat_observations").fetchone()[0] == 2


@pytest.fixture
def manual_series():
    cfg = load_series_config(REPO_ROOT / "data" / "reference")
    return {s["series_id"]: s for s in cfg["manual"]}


def test_shipped_manual_files_are_valid_real_and_sourced(ref, manual_series):
    files = list((REPO_ROOT / "data" / "manual").glob("*.csv"))
    assert files
    for path in files:
        rows = read_file(path, manual_series, ref)
        assert rows, path.name
        assert not any(o.is_sample for o in rows), f"{path.name} contains example values"
        assert all(o.source_url.startswith("https://") for o in rows)


HEADER = (
    "source_id,series_id,period,region,breakdown,value,value_label,unit,sample_size,"
    "published_at,source_url,is_sample,note\n"
)
SK = "studiekeuze123"


def test_manual_file_with_error_is_rejected(tmp_path, ref, manual_series):
    path = tmp_path / f"{SK}.csv"
    path.write_text(
        HEADER
        + f"{SK},sk_starting_salary,2024,NL,informatica,3100,,eur_month_gross,120,2025-06-01,"
        "https://x.nl,0,\n"
        + f"{SK},sk_starting_salary,24,NL,wiskunde,abc,,eur_month_gross,,juni,,2,\n"
        + f"{SK},sk_occupation,2026,NL,informatica,52,,percent,,2026-09-19,https://x.nl,0,\n",
        encoding="utf-8",
    )
    with pytest.raises(ManualDataError) as exc:
        read_file(path, manual_series, ref)
    message = str(exc.value)
    for fragment in [
        "period",
        "programme id",
        "not a number",
        "published_at",
        "source_url",
        "is_sample",
        "<programme id>/<item>",
    ]:
        assert fragment in message


def test_manual_accepts_national_average_and_items(tmp_path, ref, manual_series):
    path = tmp_path / f"{SK}.csv"
    path.write_text(
        HEADER + f"{SK},sk_starting_salary,2026,NL,hbo-bachelor,2773,,eur_month_gross,,2026-09-19,"
        "https://x.nl,0,\n"
        + f"{SK},sk_occupation,2026,NL,informatica/Softwareontwikkelaars,52,,percent,,"
        "2026-09-19,https://x.nl,0,\n",
        encoding="utf-8",
    )
    rows = read_file(path, manual_series, ref)
    assert [o.breakdown for o in rows] == ["hbo-bachelor", "informatica/Softwareontwikkelaars"]


def _stats_conn(ref):
    conn = connect(":memory:")
    init_schema(conn)
    from jobmarket.reference import sync_sources

    sync_sources(conn, ref)
    return conn


def test_manual_refresh_replaces_source_rows(tmp_path, ref):
    conn = _stats_conn(ref)
    cfg = load_series_config(REPO_ROOT / "data" / "reference")
    (tmp_path / f"{SK}.csv").write_text(
        HEADER + f"{SK},sk_outlook,2028,NL,informatica,,goed,label,,2025-12-01,https://roa.nl,0,\n",
        encoding="utf-8",
    )
    results = refresh_manual(conn, ref, cfg, tmp_path)
    assert [(r.source_id, r.status, r.rows) for r in results] == [(SK, "success", 1)]
    row = conn.execute("SELECT value_label, period_start FROM stat_observations").fetchone()
    assert tuple(row) == ("goed", "2028-01-01")


def test_removed_manual_file_drops_its_rows(tmp_path, ref):
    conn = _stats_conn(ref)
    conn.execute(
        "INSERT INTO stat_observations (source_id, series_id, period, period_start, unit, "
        "retrieved_at, licence, is_sample) VALUES ('hbo_monitor', 'old', '2024', '2024-01-01', "
        "'percent', '2026-01-01', 'x', 1), ('cbs', 'kept', '2024', '2024-01-01', 'persons', "
        "'2026-01-01', 'x', 0)"
    )
    cfg = load_series_config(REPO_ROOT / "data" / "reference")
    refresh_manual(conn, ref, cfg, tmp_path)  # no CSV files at all
    left = [r[0] for r in conn.execute("SELECT source_id FROM stat_observations")]
    assert left == ["cbs"]


def test_schema_migration_from_version_1(tmp_path):
    db = tmp_path / "old.sqlite"
    conn = connect(db)
    conn.executescript(
        "CREATE TABLE schema_version (version INTEGER NOT NULL);"
        "INSERT INTO schema_version VALUES (1);"
        "CREATE TABLE stat_observations (source_id TEXT, series_id TEXT, period TEXT, "
        "period_start TEXT, region TEXT, breakdown TEXT, value REAL, unit TEXT, sample_size INT, "
        "published_at TEXT, retrieved_at TEXT, licence TEXT, source_url TEXT, is_sample INT, "
        "note TEXT, PRIMARY KEY (source_id, series_id, period, region, breakdown));"
    )
    init_schema(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(stat_observations)")}
    assert "value_label" in cols
    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 5
