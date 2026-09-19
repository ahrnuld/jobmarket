"""Normalisation of titles, employers and locations (input for deduplication and classification)."""

from __future__ import annotations

import re
import unicodedata

# Gender and diversity markers: (m/v), (m/v/x), m/v/d, (v/m/x), (f/m/d), (h/f), (all genders)...
GENDER_MARKER = re.compile(
    r"\(?\b[mvfxdhw](?:\s*/\s*[mvfxdhw]){1,3}\b\)?|\((?:all genders|alle genders|m/w/d|x/v/m)\)",
    re.IGNORECASE,
)
# Reference codes that some sites append: "(ID: 1234)", "(ID:", "vacature 12345", "#1234"
REFERENCE_CODE = re.compile(r"\(?\bid\s*:\s*[\w-]*\)?|\bvacature(nummer)?\s*\d+|#\d+", re.I)
# Characters kept: letters, digits, spaces and the symbols in c#, c++, .net
NON_TITLE_CHARS = re.compile(r"[^\w\s#+.]", re.UNICODE)
LEGAL_FORMS = re.compile(
    r"\b(b\.?\s?v\.?|n\.?\s?v\.?|v\.?o\.?f\.?|holding|group|groep|nederland|netherlands|the)\b",
    re.I,
)


def _strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def normalise_title(title: str) -> str:
    t = GENDER_MARKER.sub(" ", title)
    t = REFERENCE_CODE.sub(" ", t)
    t = t.lower().replace("-", " ").replace("/", " ").replace("|", " ")
    t = NON_TITLE_CHARS.sub(" ", t)
    t = re.sub(r"(?<!\w)\.(?!net\b)|\.(?=\s|$)", " ", t)  # stray dots, but keep ".net"
    return " ".join(t.split())


def normalise_employer(employer: str | None) -> str:
    if not employer:
        return ""
    e = _strip_accents(employer.lower())
    e = LEGAL_FORMS.sub(" ", e)
    e = re.sub(r"[^\w\s]", " ", e)
    return " ".join(e.split())


def normalise_location(municipality: str | None, province: str | None) -> str:
    return (municipality or province or "nl").lower()
