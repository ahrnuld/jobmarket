"""Classification of a single vacancy: ICT or not, seniority, programmes and skills.

Pure functions over text plus the reference data, so they are easy to test and to evaluate
against the labelled sample (TR-05). `run.classify_all` applies them to the database.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from jobmarket.reference import Reference

# Bump when rules in code change. Reference-data changes are tracked in git and the changelog.
CLASSIFIER_VERSION = "2026.09.1"

# "0-2 jaar werkervaring", "3+ years of experience", "minimaal 5 jaar relevante ervaring"
EXPERIENCE_YEARS = re.compile(
    r"(\d{1,2})\s*(?:\+|[-–]\s*\d{1,2}|\s(?:tot|to)\s+\d{1,2})?\s*(?:jaar|years?|yrs)\b"
    r"[^.;\n]{0,40}?(?:ervaring|experience)",
    re.IGNORECASE,
)
LEVEL_ORDER = ["junior", "medior", "senior"]


@dataclass
class Classification:
    is_ict: bool
    seniority: str
    programmes: dict[str, str] = field(default_factory=dict)  # programme id -> role family id
    skills: list[str] = field(default_factory=list)


def classify_seniority(title_norm: str, description: str | None, ref: Reference) -> str:
    in_title = {
        lvl.id
        for lvl in ref.seniority_levels
        if any(p.search(title_norm) for p in lvl.title_patterns)
    }
    if "internship" in in_title:
        return "internship"
    for level in LEVEL_ORDER:  # several levels in the title: the lowest one it is open to
        if level in in_title:
            return level
    text = description or ""
    for lvl in ref.seniority_levels:  # listed order: internship first
        if any(p.search(text) for p in lvl.description_patterns):
            return lvl.id
    years = [int(m.group(1)) for m in EXPERIENCE_YEARS.finditer(text)]
    if years:
        y = min(years)
        if y <= ref.junior_max_years:
            return "junior"
        if y <= ref.medior_max_years:
            return "medior"
        return "senior"
    return "unknown"


def classify_programmes(title_norm: str, ref: Reference) -> dict[str, str]:
    result: dict[str, str] = {}
    for family in ref.role_families:
        if any(p.search(title_norm) for p in family.title_patterns):
            for programme in family.programmes:
                result.setdefault(programme, family.id)
    return result


def extract_skills(title: str, description: str | None, ref: Reference) -> list[str]:
    text = f"{title}\n{description or ''}"
    return [s.id for s in ref.skills.values() if any(p.search(text) for p in s.patterns)]


def classify(
    title: str,
    title_norm: str,
    description: str | None,
    source_category: str | None,
    ref: Reference,
) -> Classification:
    programmes = classify_programmes(title_norm, ref)
    skills = extract_skills(title, description, ref)
    # ICT if the title matches a role family, or the source filed it under IT and the text
    # mentions at least one technical skill (the IT category also holds e.g. electricians).
    has_signal = any(ref.skills[s].ict_signal for s in skills)
    is_ict = bool(programmes) or (source_category == "it-jobs" and has_signal)
    return Classification(
        is_ict=is_ict,
        seniority=classify_seniority(title_norm, description, ref),
        programmes=programmes,
        skills=skills,
    )
