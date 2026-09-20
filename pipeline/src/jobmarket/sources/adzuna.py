"""Adzuna job search API client (https://developer.adzuna.com/).

Credentials come from ADZUNA_APP_ID / ADZUNA_APP_KEY and are never logged: every error message
passes through `_redact` first.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

from jobmarket.models import VacancyRecord

API_BASE = "https://api.adzuna.com/v1/api/jobs"
RETRY_STATUSES = {429, 500, 502, 503, 504}


class AdzunaError(RuntimeError):
    pass


@dataclass
class AdzunaConfig:
    app_id: str
    app_key: str
    country: str = "nl"
    results_per_page: int = 50
    min_seconds_between_calls: float = 3.0
    max_calls_per_run: int = 250
    max_calls_per_day: int | None = None
    max_calls_per_week: int | None = None
    max_calls_per_month: int | None = None
    default_days: int = 8
    queries: list[dict] = field(default_factory=list)

    @classmethod
    def from_settings(cls, settings, ingestion_cfg: dict) -> AdzunaConfig:
        cfg = dict(ingestion_cfg.get("adzuna", {}))
        return cls(app_id=settings.adzuna_app_id, app_key=settings.adzuna_app_key, **cfg)


@dataclass
class FetchStats:
    calls: int = 0
    per_query: dict[str, int] = field(default_factory=dict)
    budget_exhausted: bool = False
    budget_note: str | None = None  # which limit stopped the fetch


def _http_get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


class AdzunaClient:
    def __init__(
        self,
        config: AdzunaConfig,
        http_get: Callable[[str], dict] = _http_get_json,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        budget=None,
    ):
        if not (config.app_id and config.app_key):
            raise AdzunaError("Adzuna credentials missing: set ADZUNA_APP_ID and ADZUNA_APP_KEY")
        self.config = config
        self._http_get = http_get
        self._sleep = sleep
        self._clock = clock
        self._last_call: float | None = None
        self.budget = budget  # jobmarket.budget.Budget, or None for no cross-run accounting
        self.stats = FetchStats()

    def _redact(self, text: str) -> str:
        for secret in (self.config.app_key, self.config.app_id):
            if secret:
                text = text.replace(secret, "***")
        return text

    def _throttle(self) -> None:
        if self._last_call is not None:
            wait = self.config.min_seconds_between_calls - (self._clock() - self._last_call)
            if wait > 0:
                self._sleep(wait)
        self._last_call = self._clock()

    def _get(self, path: str, params: dict) -> dict:
        query = urllib.parse.urlencode(
            {"app_id": self.config.app_id, "app_key": self.config.app_key, **params}
        )
        url = f"{API_BASE}/{self.config.country}/{path}?{query}"
        for attempt in range(4):
            self._throttle()
            self.stats.calls += 1
            if self.budget is not None:
                self.budget.spend()
            try:
                return self._http_get(url)
            except urllib.error.HTTPError as exc:
                if exc.code in RETRY_STATUSES and attempt < 3:
                    self._sleep(10 * 2**attempt)
                    continue
                raise AdzunaError(
                    self._redact(f"HTTP {exc.code} for {path}: {exc.reason}")
                ) from None
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                if attempt < 3:
                    self._sleep(10 * 2**attempt)
                    continue
                raise AdzunaError(self._redact(f"Request failed for {path}: {exc}")) from None
        raise AdzunaError(f"Request failed for {path} after retries")  # pragma: no cover

    def search(self, query_id: str, params: dict, days: int) -> Iterator[dict]:
        """Yield raw result dicts for one query, page by page, within the call budget."""
        page = 1
        seen = 0
        while True:
            if self.stats.calls >= self.config.max_calls_per_run:
                self.stats.budget_exhausted = True
                self.stats.budget_note = f"max_calls_per_run ({self.config.max_calls_per_run})"
                return
            if self.budget is not None and not self.budget.allow():
                self.stats.budget_exhausted = True
                self.stats.budget_note = f"plan limit reached ({self.budget.describe()})"
                return
            data = self._get(
                f"search/{page}",
                {
                    **params,
                    "results_per_page": self.config.results_per_page,
                    "max_days_old": days,
                    "sort_by": "date",
                    "content-type": "application/json",
                },
            )
            results = data.get("results") or []
            self.stats.per_query[query_id] = self.stats.per_query.get(query_id, 0) + len(results)
            yield from results
            seen += len(results)
            if not results or seen >= int(data.get("count") or 0):
                return
            page += 1

    def fetch(self, days: int | None = None) -> Iterator[VacancyRecord]:
        """Run all configured queries; a vacancy found by several queries is yielded once."""
        days = days or self.config.default_days
        yielded: set[str] = set()
        for q in self.config.queries:
            params = {k: " ".join(str(v).split()) for k, v in q.get("params", {}).items()}
            for raw in self.search(q["id"], params, days):
                ext_id = str(raw.get("id"))
                if ext_id in yielded:
                    continue
                yielded.add(ext_id)
                yield to_record(raw)


def _num(value) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def to_record(raw: dict) -> VacancyRecord:
    location = raw.get("location") or {}
    predicted = raw.get("salary_is_predicted")
    return VacancyRecord(
        source_id="adzuna",
        external_id=str(raw["id"]),
        title=(raw.get("title") or "").strip(),
        posted_at=(raw.get("created") or "")[:10],
        employer=((raw.get("company") or {}).get("display_name") or None),
        location_raw=location.get("display_name"),
        area=list(location.get("area") or []),
        description=raw.get("description"),
        source_category=(raw.get("category") or {}).get("tag"),
        salary_min=_num(raw.get("salary_min")),
        salary_max=_num(raw.get("salary_max")),
        salary_is_predicted=None if predicted is None else str(predicted) == "1",
        contract_time=raw.get("contract_time"),
        url=raw.get("redirect_url"),
    )
