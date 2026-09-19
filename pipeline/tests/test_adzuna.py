from __future__ import annotations

import io
import urllib.error
import urllib.parse

import pytest

from jobmarket.sources.adzuna import AdzunaClient, AdzunaConfig, AdzunaError, to_record

SECRET_KEY = "k" * 32
SECRET_ID = "i" * 8


def raw(i, **extra):
    return {
        "id": str(i),
        "title": f"Developer {i}",
        "created": "2026-09-15T17:51:23Z",
        "company": {"display_name": "Voorbeeld BV"},
        "location": {"display_name": "Haarlem", "area": ["Nederland", "Noord-Holland", "Haarlem"]},
        "description": "Je werkt met Python…",
        "category": {"tag": "it-jobs"},
        "salary_min": 40000,
        "salary_max": 50000,
        "salary_is_predicted": "0",
        "redirect_url": "https://www.adzuna.nl/details/1",
        **extra,
    }


class FakeHttp:
    """Serves pages from a dict keyed by (query marker, page)."""

    def __init__(self, pages, fail_with=None):
        self.pages = pages
        self.calls = []
        self.fail_with = fail_with

    def __call__(self, url):
        self.calls.append(url)
        if self.fail_with:
            err = self.fail_with.pop(0) if self.fail_with else None
            if err:
                raise err
        parsed = urllib.parse.urlparse(url)
        params = dict(urllib.parse.parse_qsl(parsed.query))
        page = int(parsed.path.rsplit("/", 1)[1])
        key = "cat" if "category" in params else "kw"
        return self.pages.get((key, page), {"count": 0, "results": []})


def client(http, **cfg):
    config = AdzunaConfig(
        app_id=SECRET_ID,
        app_key=SECRET_KEY,
        min_seconds_between_calls=0,
        queries=[
            {"id": "it-category", "params": {"category": "it-jobs"}},
            {"id": "ict-keywords", "params": {"what_or": "developer  ontwikkelaar\n java"}},
        ],
        **cfg,
    )
    return AdzunaClient(config, http_get=http, sleep=lambda s: None)


def test_pages_and_deduplicates_across_queries():
    http = FakeHttp(
        {
            ("cat", 1): {"count": 3, "results": [raw(1), raw(2)]},
            ("cat", 2): {"count": 3, "results": [raw(3)]},
            ("kw", 1): {"count": 2, "results": [raw(3), raw(4)]},
        }
    )
    c = client(http)
    ids = [r.external_id for r in c.fetch(days=8)]
    assert ids == ["1", "2", "3", "4"]
    assert c.stats.calls == 3
    assert "max_days_old=8" in http.calls[0]
    assert "what_or=developer+ontwikkelaar+java" in http.calls[2]  # whitespace collapsed


def test_call_budget_is_respected():
    http = FakeHttp({("cat", p): {"count": 1000, "results": [raw(p)]} for p in range(1, 20)})
    c = client(http, max_calls_per_run=5)
    assert len(list(c.fetch())) == 5
    assert c.stats.budget_exhausted


def test_errors_never_contain_credentials():
    err = urllib.error.HTTPError(
        f"https://api.adzuna.com/?app_id={SECRET_ID}&app_key={SECRET_KEY}",
        401,
        f"Unauthorised key {SECRET_KEY}",
        {},
        io.BytesIO(b""),
    )
    c = client(FakeHttp({}, fail_with=[err]))
    with pytest.raises(AdzunaError) as exc_info:
        list(c.fetch())
    assert SECRET_KEY not in str(exc_info.value)
    assert SECRET_ID not in str(exc_info.value)


def test_retries_on_rate_limit():
    err = urllib.error.HTTPError("u", 429, "Too Many Requests", {}, io.BytesIO(b""))
    http = FakeHttp({("cat", 1): {"count": 1, "results": [raw(1)]}}, fail_with=[err, None])
    assert [r.external_id for r in client(http).fetch()] == ["1"]


def test_missing_credentials():
    with pytest.raises(AdzunaError, match="credentials"):
        AdzunaClient(AdzunaConfig(app_id="", app_key=""))


def test_to_record_maps_fields():
    rec = to_record(raw(7, salary_is_predicted="1", company=None))
    assert rec.external_id == "7"
    assert rec.posted_at == "2026-09-15"
    assert rec.area == ["Nederland", "Noord-Holland", "Haarlem"]
    assert rec.employer is None
    assert rec.salary_is_predicted is True
    assert rec.source_category == "it-jobs"
