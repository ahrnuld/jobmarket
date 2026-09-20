from __future__ import annotations

import pytest

from jobmarket.clean.geo import resolve
from jobmarket.ingest import ingest
from jobmarket.process import process
from jobmarket.sources.eures import EuresClient, EuresConfig, period_for, to_record

# Shapes recorded from the API on 2026-09-20, trimmed to the fields we read.
SUMMARY = {
    "id": "NThlNWVkN2MtMjU3Ni0xY2YyLWUwNjMgNDI=",
    "title": "SAP Product Architect Finance",
    "creationDate": 1786583656918,
    "locationMap": {"NL": ["NL423"]},
}
DETAIL = {
    "id": SUMMARY["id"],
    "creationDate": 1786583656918,
    "source": "NL",
    "jvProfiles": {
        "nl": {
            "title": "SAP Product Architect Finance",
            "description": "Boels Rental <br> Sittard &nbsp;&amp; co<br>Je werkt met SAP en Azure.",
            "positionScheduleCodes": ["fulltime"],
            "locations": [
                {
                    "countryCode": "nl",
                    "region": "nl423",
                    "cityName": "SITTARD",
                    "postalCode": "6136GV",
                }
            ],
            "offeredRemunerationPackage": {
                "salaries": [
                    {
                        "referenceSalary": 4823.0,
                        "currencyCode": "EUR",
                        "remunerationTypeCode": "basepay",
                    }
                ]
            },
            # Never stored: the recruiter's name, e-mail and address (LR-03).
            "personContacts": [
                {
                    "givenName": "Jan",
                    "familyName": "Jansen",
                    "communications": {"emails": [{"uri": "jan@example.nl"}]},
                }
            ],
        }
    },
}


def test_record_keeps_the_figures_and_drops_the_contact():
    record = to_record(SUMMARY, DETAIL)
    assert record.source_id == "eures"
    assert record.external_id == SUMMARY["id"]
    assert record.posted_at == "2026-08-13"
    assert record.location_raw == "Sittard"
    assert record.region_code == "nl423"
    assert record.salary_min == record.salary_max == 4823.0
    assert record.salary_is_predicted is False
    assert record.contract_time == "full_time"
    assert record.description == "Boels Rental Sittard & co Je werkt met SAP en Azure."
    assert "jan@example.nl" not in str(record)
    assert "Jansen" not in str(record)
    assert record.source_category == "ict-occupation"


def test_a_vacancy_without_a_title_or_date_is_skipped():
    assert to_record({"id": "x"}, {"jvProfiles": {"nl": {"title": ""}}}) is None
    assert to_record({"id": "x", "title": "Developer"}, {"jvProfiles": {}}) is None


@pytest.mark.parametrize(
    "days, expected",
    [(1, "LAST_DAY"), (2, "LAST_WEEK"), (7, "LAST_WEEK"), (8, "LAST_MONTH"), (60, "LAST_MONTH")],
)
def test_period_for(days, expected):
    assert period_for(days) == expected


class FakeApi:
    """Two pages of results; the detail call answers for any id."""

    def __init__(self, total=3):
        self.total = total
        self.searches = 0
        self.details: list[str] = []

    def __call__(self, url, body=None):
        if body is not None:
            self.searches += 1
            page = body["page"]
            start = (page - 1) * body["resultsPerPage"]
            jvs = [
                {**SUMMARY, "id": f"id-{i}", "title": f"Developer {i}"}
                for i in range(start, min(start + body["resultsPerPage"], self.total))
            ]
            return {"numberRecords": self.total, "jvs": jvs}
        self.details.append(url)
        return DETAIL


def _client(api, **over):
    config = EuresConfig(
        occupation_uris=["http://data.europa.eu/esco/occupation/x"],
        results_per_page=2,
        min_seconds_between_calls=0,
        **over,
    )
    return EuresClient(config, http_json=api, sleep=lambda s: None)


def test_pages_until_the_last_result():
    api = FakeApi(total=3)
    records = list(_client(api).fetch(days=1))
    assert [r.external_id for r in records] == ["id-0", "id-1", "id-2"]
    assert api.searches == 2  # two pages of two


def test_vacancies_we_already_have_cost_no_detail_call():
    api = FakeApi(total=3)
    records = list(_client(api).fetch(days=1, known={"id-0", "id-1"}))
    assert [r.external_id for r in records] == ["id-2"]
    assert len(api.details) == 1


def test_a_run_stops_at_its_call_cap():
    api = FakeApi(total=100)
    client = _client(api, max_calls_per_run=3)
    list(client.fetch(days=1))
    assert client.stats.calls == 3
    assert client.stats.budget_exhausted


def test_missing_occupations_are_refused():
    with pytest.raises(Exception, match="update-occupations"):
        EuresClient(EuresConfig())


def test_a_nuts3_code_puts_a_vacancy_on_the_map(ref):
    """EURES names a NUTS 3 region, which in the Netherlands is a COROP area."""
    place = resolve(["Nederland"], None, ref, "nl423")
    assert (place.corop, place.province) == ("zuid-limburg", "limburg")
    assert place.municipality is None  # a COROP area is bigger than a municipality
    # A place name we do know still wins: it gives the municipality and the region as well.
    known = resolve(["Nederland", "Noord-Holland", "Alkmaar"], "Alkmaar", ref, "nl321")
    assert (known.municipality, known.corop) == ("Alkmaar", "alkmaar-en-omgeving")


def test_the_same_vacancy_from_two_sources_counts_once(conn, ref):
    """EURES carries no employer; without this the same posting would count twice."""
    from jobmarket.models import VacancyRecord

    common = {
        "title": "Java Developer",
        "posted_at": "2026-09-10",
        "location_raw": "Haarlem",
        "area": ["Nederland", "Noord-Holland", "Haarlem"],
        "description": "Java en SQL.",
        "source_category": "it-jobs",
    }
    ingest(
        conn,
        "adzuna",
        [VacancyRecord(source_id="adzuna", external_id="a1", employer="ACME", **common)],
        ref,
    )
    ingest(
        conn,
        "eures",
        [
            VacancyRecord(
                source_id="eures",
                external_id="e1",
                employer=None,
                **{**common, "source_category": "ict-occupation"},
            )
        ],
        ref,
    )
    process(conn, ref, [])
    unique = conn.execute(
        "SELECT COUNT(*) FROM vacancies WHERE is_ict = 1 AND duplicate_of IS NULL"
    ).fetchone()[0]
    assert unique == 1
