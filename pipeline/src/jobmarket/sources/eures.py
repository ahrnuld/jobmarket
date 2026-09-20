"""EURES client: Dutch vacancies from the European Job Mobility Portal.

EURES publishes the vacancies the national employment services collect; for the Netherlands
that is UWV (connection point 42). Two calls per vacancy: a search page lists ids and summaries,
a detail call adds the city, the structured salary and the full text. Only vacancies we do not
already have get a detail call.

Why it is worth a second source (measured 2026-09-20): 6,034 ICT vacancies listed against
Adzuna's 3,226 in a year, descriptions of ~2,000 characters against Adzuna's hard 500, an ESCO
occupation per vacancy instead of our own keyword guess, and a NUTS 3 region, which in the
Netherlands is exactly the COROP area the map uses.

The portal's API needs no key. It is the one its own pages use: undocumented, so a change in the
response is a failed run, not wrong figures, and the previous snapshot stays published (NFR-07).

Personal data is never stored: the contact block (name, e-mail, telephone, street address of the
recruiter) is dropped here, before the record leaves this module (LR-03).
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime

from jobmarket.models import VacancyRecord

SEARCH_URL = "https://europa.eu/eures/api/jv-searchengine/public/jv-search/search"
DETAIL_URL = "https://europa.eu/eures/api/jv-searchengine/public/jv/id/"
RETRY_STATUSES = {429, 500, 502, 503, 504}
# How far back a run asks. The filter works on the moment a vacancy last changed, so a daily run
# with LAST_DAY also picks up older vacancies that were edited; they are ignored as duplicates.
PERIODS = {1: "LAST_DAY", 7: "LAST_WEEK", 30: "LAST_MONTH"}
TAGS = re.compile(r"<[^>]+>")


class EuresError(RuntimeError):
    pass


@dataclass
class EuresConfig:
    country: str = "nl"
    results_per_page: int = 50
    min_seconds_between_calls: float = 1.0
    max_calls_per_run: int = 500
    default_days: int = 1
    occupation_uris: list[str] = field(default_factory=list)

    @classmethod
    def from_settings(cls, ingestion_cfg: dict, occupation_uris: list[str]) -> EuresConfig:
        cfg = dict(ingestion_cfg.get("eures", {}))
        return cls(occupation_uris=occupation_uris, **cfg)


@dataclass
class FetchStats:
    calls: int = 0
    listed: int = 0  # vacancies the search returned
    details: int = 0  # vacancies we asked the details of
    budget_exhausted: bool = False
    budget_note: str | None = None


def _http_json(url: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Accept": "application/json"}
    if data:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(request, timeout=90) as response:
        return json.load(response)


def period_for(days: int) -> str:
    """The narrowest period that covers `days`."""
    for limit, name in PERIODS.items():
        if days <= limit:
            return name
    return "LAST_MONTH"


class EuresClient:
    def __init__(
        self,
        config: EuresConfig,
        http_json: Callable[..., dict] = _http_json,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ):
        if not config.occupation_uris:
            raise EuresError(
                "No ESCO occupations configured; run `jobmarket reference update-occupations`"
            )
        self.config = config
        self._http_json = http_json
        self._sleep = sleep
        self._clock = clock
        self._last_call: float | None = None
        self.stats = FetchStats()

    def _throttle(self) -> None:
        if self._last_call is not None:
            wait = self.config.min_seconds_between_calls - (self._clock() - self._last_call)
            if wait > 0:
                self._sleep(wait)
        self._last_call = self._clock()

    def _call(self, url: str, body: dict | None = None) -> dict:
        for attempt in range(4):
            self._throttle()
            self.stats.calls += 1
            try:
                return self._http_json(url, body)
            except urllib.error.HTTPError as exc:
                if exc.code in RETRY_STATUSES and attempt < 3:
                    self._sleep(10 * 2**attempt)
                    continue
                raise EuresError(f"HTTP {exc.code} for {url.split('?')[0]}: {exc.reason}") from None
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                if attempt < 3:
                    self._sleep(10 * 2**attempt)
                    continue
                raise EuresError(f"Request failed for {url.split('?')[0]}: {exc}") from None
        raise EuresError("Request failed after retries")  # pragma: no cover

    def _budget_left(self) -> bool:
        if self.stats.calls < self.config.max_calls_per_run:
            return True
        self.stats.budget_exhausted = True
        self.stats.budget_note = f"max_calls_per_run ({self.config.max_calls_per_run})"
        return False

    def search(self, days: int) -> Iterator[dict]:
        """Yield the summaries of the ICT vacancies changed within `days`, page by page."""
        page = 1
        while self._budget_left():
            body = {
                "resultsPerPage": self.config.results_per_page,
                "page": page,
                "sortSearch": "BEST_MATCH",
                "keywords": [],
                "locationCodes": [self.config.country],
                "occupationUris": self.config.occupation_uris,
                "publicationPeriod": period_for(days),
            }
            data = self._call(SEARCH_URL, body)
            results = data.get("jvs") or []
            self.stats.listed += len(results)
            yield from results
            if not results or page * self.config.results_per_page >= int(
                data.get("numberRecords") or 0
            ):
                return
            page += 1

    def detail(self, vacancy_id: str) -> dict:
        url = DETAIL_URL + urllib.parse.quote(vacancy_id, safe="") + "?requestLang=en"
        self.stats.details += 1
        return self._call(url)

    def fetch(
        self, days: int | None = None, known: set[str] | None = None
    ) -> Iterator[VacancyRecord]:
        """Records for the vacancies we do not have yet; known ids cost no detail call."""
        days = days or self.config.default_days
        known = known or set()
        for summary in self.search(days):
            vacancy_id = str(summary.get("id") or "")
            if not vacancy_id or vacancy_id in known:
                continue
            known.add(vacancy_id)
            if not self._budget_left():
                return
            record = to_record(summary, self.detail(vacancy_id))
            if record is not None:
                yield record


def _text(html: str | None) -> str | None:
    """Vacancy texts come as HTML fragments; we store plain text."""
    if not html:
        return None
    text = TAGS.sub(" ", html)
    for entity, char in (
        ("&nbsp;", " "),
        ("&amp;", "&"),
        ("&lt;", "<"),
        ("&gt;", ">"),
        ("&quot;", '"'),
        ("&#39;", "'"),
    ):
        text = text.replace(entity, char)
    return re.sub(r"[ \t]+", " ", text).strip() or None


def _date(milliseconds: int | None) -> str | None:
    if not milliseconds:
        return None
    return datetime.fromtimestamp(milliseconds / 1000, UTC).date().isoformat()


def _profile(detail: dict) -> dict:
    """The vacancy in one language; Dutch when there is one, else whatever is offered."""
    profiles = detail.get("jvProfiles") or {}
    return profiles.get("nl") or next(iter(profiles.values()), {})


def to_record(summary: dict, detail: dict) -> VacancyRecord | None:
    profile = _profile(detail)
    title = (profile.get("title") or summary.get("title") or "").strip()
    posted_at = _date(detail.get("creationDate") or summary.get("creationDate"))
    if not title or not posted_at:
        return None
    location = (profile.get("locations") or [{}])[0]
    city = (location.get("cityName") or "").strip()
    region = (location.get("region") or "").strip().lower()
    # The sources of a salary differ in period and kind; only a plain monthly or yearly base
    # pay is usable, and aggregate.annual_salary decides the unit as it does for other sources.
    salary = None
    for entry in (profile.get("offeredRemunerationPackage") or {}).get("salaries") or []:
        if entry.get("remunerationTypeCode") == "basepay" and entry.get("currencyCode") == "EUR":
            salary = entry.get("referenceSalary")
            break
    schedules = profile.get("positionScheduleCodes") or []
    return VacancyRecord(
        source_id="eures",
        external_id=str(summary.get("id") or detail.get("id")),
        title=title,
        posted_at=posted_at,
        # EURES carries no employer field; the name is usually somewhere in the text.
        employer=None,
        location_raw=city.title() or None,
        area=["Nederland"] + ([city.title()] if city else []),
        description=_text(profile.get("description") or summary.get("description")),
        # Every vacancy we ask for is filed by the source under an ICT occupation (see
        # occupations.py); the classifier treats that as the source saying "this is ICT".
        source_category="ict-occupation",
        salary_min=salary,
        salary_max=salary,
        salary_is_predicted=False,
        contract_time="full_time" if "fulltime" in schedules else None,
        url=f"https://europa.eu/eures/portal/jv-se/jv-details/{summary.get('id')}",
        region_code=region or None,
    )
