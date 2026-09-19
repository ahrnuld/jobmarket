"""Admin mapping corrections (FR-21), stored append-only in data/corrections.yaml.

A correction targets every vacancy with a given normalised title and overrides what the rules
decided. They are applied after classification on every run, in file order, so a later entry
wins over an earlier one. The file doubles as the correction log: who, when, what and why.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml

from jobmarket.classify import Classification
from jobmarket.clean.normalise import normalise_title
from jobmarket.reference import SENIORITY_LEVELS, Reference

TYPES = ("programme", "seniority", "skill_add", "skill_remove", "not_ict")


class CorrectionError(ValueError):
    pass


@dataclass(frozen=True)
class Correction:
    date: str
    author: str
    type: str
    match: str  # normalised title
    value: tuple[str, ...]
    reason: str


def _validate(entry: dict, ref: Reference, i: int) -> Correction:
    where = f"corrections.yaml entry {i + 1}"
    for key in ("date", "author", "type", "match", "reason"):
        if not entry.get(key):
            raise CorrectionError(f"{where}: missing {key}")
    ctype = entry["type"]
    if ctype not in TYPES:
        raise CorrectionError(f"{where}: type must be one of {TYPES}")
    raw = entry.get("value")
    values = tuple(raw) if isinstance(raw, list) else ((raw,) if raw else ())
    if ctype == "programme":
        unknown = set(values) - set(ref.programmes)
        if unknown:
            raise CorrectionError(f"{where}: unknown programme(s) {sorted(unknown)}")
    elif ctype == "seniority":
        if len(values) != 1 or values[0] not in SENIORITY_LEVELS:
            raise CorrectionError(f"{where}: seniority value must be one of {SENIORITY_LEVELS}")
    elif ctype in ("skill_add", "skill_remove"):
        unknown = set(values) - set(ref.skills)
        if not values or unknown:
            raise CorrectionError(f"{where}: unknown or missing skill(s) {sorted(unknown)}")
    return Correction(
        date=str(entry["date"]),
        author=str(entry["author"]),
        type=ctype,
        match=normalise_title(str(entry["match"])),
        value=values,
        reason=str(entry["reason"]),
    )


def load_corrections(path: Path, ref: Reference) -> list[Correction]:
    if not path.is_file():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [_validate(e, ref, i) for i, e in enumerate(data.get("corrections") or [])]


def index_by_title(corrections: list[Correction]) -> dict[str, list[Correction]]:
    index: dict[str, list[Correction]] = {}
    for c in corrections:
        index.setdefault(c.match, []).append(c)
    return index


def apply(result: Classification, corrections: list[Correction]) -> Classification:
    for c in corrections:
        if c.type == "programme":
            result.programmes = {p: "admin-correction" for p in c.value}
            if c.value:
                result.is_ict = True
        elif c.type == "seniority":
            result.seniority = c.value[0]
        elif c.type == "skill_add":
            result.skills = sorted(set(result.skills) | set(c.value))
        elif c.type == "skill_remove":
            result.skills = [s for s in result.skills if s not in c.value]
        elif c.type == "not_ict":
            result.is_ict = False
            result.programmes = {}
    return result


def append_correction(path: Path, ref: Reference, entry: dict) -> Correction:
    """Validate and append one correction to the YAML file, keeping the header comments."""
    entry = {"date": date.today().isoformat(), **entry}
    existing = load_corrections(path, ref)
    correction = _validate(entry, ref, len(existing))
    text = path.read_text(encoding="utf-8") if path.is_file() else "corrections: []\n"
    if "corrections: []" in text:
        text = text.replace("corrections: []", "corrections:")
    item = yaml.safe_dump([entry], allow_unicode=True, sort_keys=False, width=100)
    text = text.rstrip("\n") + "\n" + "".join(f"  {line}\n" for line in item.splitlines())
    path.write_text(text, encoding="utf-8")
    return correction
