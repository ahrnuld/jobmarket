"""Remove personal data from vacancy text before it is stored (LR-03).

Removes e-mail addresses, phone numbers and the names of contact persons. Names cannot be
recognised reliably in general, so this targets the places where recruiter names actually appear:
after phrases like "neem contact op met", "contactpersoon:", "bel ... op", "contact ... at".
The tests in tests/test_pii.py hold the cases this must handle; add a case whenever a leak is found.
"""

from __future__ import annotations

import re

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+", re.UNICODE)

# Dutch numbers: 06-12345678, 06 1234 5678, 020-1234567, 020 123 4567, +31 6 12345678,
# +31 (0)20 123 4567, 0031 20 1234567. At least 9 digits, so years and salaries are left alone.
PHONE = re.compile(r"(?<![\w+])(?:\+|00)?(?:31[\s-]?(?:\(0\)[\s-]?)?|0)(?:[\s-]?\d){8,10}(?!\d)")

# Name: 1-3 capitalised words, optionally with Dutch particles (van, de, der, den, ter, el, ...).
_PARTICLE = r"(?:van|de|der|den|ter|ten|te|het|in\s+'t|el|al|da|di|le|la)"
_CAP = r"[A-Z][a-zà-ÿ'’]+(?:-[A-Z][a-zà-ÿ'’]+)*"  # also Jan-Willem
NAME = rf"{_CAP}(?:\s+(?:{_PARTICLE}\s+)*{_CAP}){{0,2}}"

_INTRO = [
    r"contact\s+op\s+met",
    r"contactpersoon\s*(?:is|:)?",
    r"(?:bel|mail|app)(?:\s+dan)?(?:\s+met)?(?:\s+(?:onze|de))?(?:\s+(?:recruiter|"
    r"corporate\s+recruiter|talent\s+acquisition\s+specialist|hr[- ]adviseur|manager))?",
    r"(?:recruiter|contact(?:\s+person)?)\s*(?:is|:)",
    r"(?:contact|ask\s+for|reach\s+out\s+to|call|email)(?:\s+our\s+recruiter)?",
    r"(?:onze\s+)?recruiter",
    r"informatie\s+bij",
]
# Intro phrases are case-insensitive; the name itself must be capitalised.
CONTACT_NAME = re.compile(rf"\b((?i:{'|'.join(_INTRO)})\s*:?\s+)({NAME})")

# Capitalised words that follow an intro phrase but are not names.
_NOT_NAMES = {
    "Ons",
    "Onze",
    "De",
    "Het",
    "Een",
    "Our",
    "The",
    "Us",
    "HR",
    "Recruitment",
    "Team",
    "Wij",
    "We",
    "Je",
    "Jij",
    "U",
    "You",
    "Dan",
    "Via",
    "Voor",
    "Bij",
    "Met",
}


def _replace_name(match: re.Match) -> str:
    intro, name = match.group(1), match.group(2)
    if name.split()[0] in _NOT_NAMES:
        return match.group(0)
    return f"{intro}[naam]"


def scrub(text: str | None) -> str | None:
    if not text:
        return text
    text = EMAIL.sub("[e-mail]", text)
    text = PHONE.sub("[telefoon]", text)
    text = CONTACT_NAME.sub(_replace_name, text)
    return text
