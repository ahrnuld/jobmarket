"""Source-independent record types passed between pipeline stages."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class VacancyRecord:
    """One vacancy as delivered by a source, before cleaning.

    Sources map their own format onto this; everything after ingestion only sees this type,
    so adding a second vacancy source (risk mitigation in REQUIREMENTS.md section 9) means writing
    one new adapter.
    """

    source_id: str
    external_id: str
    title: str
    posted_at: str  # ISO date
    employer: str | None = None
    location_raw: str | None = None
    area: list[str] = field(default_factory=list)  # e.g. ["Nederland", "Noord-Holland", "Haarlem"]
    description: str | None = None
    source_category: str | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    salary_is_predicted: bool | None = None
    contract_time: str | None = None
    url: str | None = None
    is_sample: bool = False
