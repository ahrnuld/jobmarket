"""Tell Dutch and English postings apart (DR-06) by counting common function words."""

from __future__ import annotations

import re

_NL = set(
    "de het een en van je jij wij we ons onze is zijn voor met op in bij als dat die naar "
    "ook wat heb hebt heeft werk werken ervaring kennis functie vacature team jaar niet".split()
)
_EN = set(
    "the a an and of you we our is are for with on in at as that to your have has will "
    "work working experience knowledge role team years not".split()
)
# Words in both lists (in, is, team, we) cancel out.
_WORD = re.compile(r"[a-zà-ÿ]+")


def detect(text: str | None) -> str:
    if not text:
        return "unknown"
    words = _WORD.findall(text.lower())
    nl = sum(w in _NL for w in words)
    en = sum(w in _EN for w in words)
    if nl + en < 3:
        return "unknown"
    if nl >= en * 1.3:
        return "nl"
    if en >= nl * 1.3:
        return "en"
    return "unknown"
