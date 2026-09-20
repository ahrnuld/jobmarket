"""Classification of a single vacancy: ICT or not, seniority, programmes and skills.

Pure functions over text plus the reference data, so they are easy to test and to evaluate
against the labelled sample (TR-05). `run.classify_all` applies them to the database.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from jobmarket.reference import Reference

# Bump when rules in code change. Reference-data changes are tracked in git and the changelog.
CLASSIFIER_VERSION = "2026.09.2"

# "0-2 jaar werkervaring", "3+ years of experience", "minimaal 5 jaar relevante ervaring"
EXPERIENCE_YEARS = re.compile(
    r"(\d{1,2})\s*(?:\+|[-–]\s*\d{1,2}|\s(?:tot|to)\s+\d{1,2})?\s*(?:jaar|years?|yrs)\b"
    r"[^.;\n]{0,40}?(?:ervaring|experience)",
    re.IGNORECASE,
)
LEVEL_ORDER = ["junior", "medior", "senior"]

# Vacancy titles are often plural ("Software Engineers - diverse branches", "Java Developers",
# "Business Analisten"), while the role family and exclusion patterns are written in the
# singular. Only these role nouns lose their plural ending, including as the tail of a compound
# ("systeembeheerders", "accountmanagers"), so a word that merely ends in -s or -en ("devops",
# "business", "data", "binnen") is left alone.
ROLE_NOUNS = [
    "developer",
    "engineer",
    "consultant",
    "designer",
    "manager",
    "tester",
    "administrator",
    "scientist",
    "analyst",
    "architect",
    "specialist",
    "ontwikkelaar",
    "programmeur",
    "beheerder",
    "adviseur",
    "analist",
    "monteur",
    "medewerker",
]
_PLURAL_RE = re.compile(rf"\b(\w*?(?:{'|'.join(ROLE_NOUNS)}))(?:s|en)\b")


def singularise(title_norm: str) -> str:
    """Title with plural role nouns in the singular, so one pattern covers both forms."""
    return _PLURAL_RE.sub(lambda m: m.group(1), title_norm)


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


def matching_families(title_norm: str, ref: Reference) -> list[str]:
    title = singularise(title_norm)
    return [f.id for f in ref.role_families if any(p.search(title) for p in f.title_patterns)]


def classify_programmes(title_norm: str, ref: Reference) -> dict[str, str]:
    families = {f.id: f for f in ref.role_families}
    result: dict[str, str] = {}
    for family_id in matching_families(title_norm, ref):
        for programme in families[family_id].programmes:
            result.setdefault(programme, family_id)
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
    families = matching_families(title_norm, ref)
    programmes = classify_programmes(title_norm, ref)
    skills = extract_skills(title, description, ref)
    # ICT if the title matches a role family, or the source filed the vacancy under ICT *and*
    # the text names a technical skill, and the title is not an excluded non-ICT role. Neither
    # source label is enough on its own: Adzuna's IT category also holds electricians and sales
    # jobs at software companies, and the ESCO occupation EURES carries is assigned at the
    # source, where a sewer cleaner and a category manager also ended up under an ICT occupation.
    has_signal = any(ref.skills[s].ict_signal for s in skills)
    excluded = any(p.search(singularise(title_norm)) for p in ref.exclude_title_patterns)
    by_source = source_category in ("it-jobs", "ict-occupation") and has_signal
    is_ict = bool(families) or (by_source and not excluded)
    return Classification(
        is_ict=is_ict,
        seniority=classify_seniority(title_norm, description, ref),
        programmes=programmes,
        skills=skills,
    )
