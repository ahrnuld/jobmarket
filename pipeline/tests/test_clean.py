from __future__ import annotations

import pytest

from jobmarket.clean import geo, language
from jobmarket.clean.normalise import normalise_employer, normalise_title


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Junior Java Developer (m/v/x)", "junior java developer"),
        ("Medior .NET Developer m/v", "medior .net developer"),
        ("PLC-programmeur", "plc programmeur"),
        ("Junior/Medior Front-end Developer", "junior medior front end developer"),
        ("C# / C++ Engineer (V/M/X)", "c# c++ engineer"),
        ("Azure Databricks Engineer (ID:", "azure databricks engineer"),
        ("Identity & Access Specialist", "identity access specialist"),
        ("Sr. Developer - Amsterdam", "sr developer amsterdam"),
    ],
)
def test_normalise_title(raw, expected):
    assert normalise_title(raw) == expected


def test_normalise_employer_drops_legal_form():
    assert normalise_employer("Voorbeeld Software B.V.") == normalise_employer(
        "voorbeeld software bv"
    )
    assert normalise_employer(None) == ""


@pytest.mark.parametrize(
    "area, raw, expected",
    [
        (
            ["Nederland", "Noord-Holland", "Haarlem"],
            None,
            ("Haarlem", "zuid-kennemerland-ijmond", "noord-holland"),
        ),
        (
            ["Nederland", "Noord-Holland", "Beverwijk", "Wijk aan Zee"],
            None,
            ("Beverwijk", "zuid-kennemerland-ijmond", "noord-holland"),
        ),
        (
            ["Nederland", "Noord-Holland", "Haarlemmermeer", "Hoofddorp"],
            None,
            ("Haarlemmermeer", "groot-amsterdam", "noord-holland"),
        ),
        (["Nederland", "Gelderland", "Bernheze"], None, ("Bernheze", None, "gelderland")),
        (["Nederland"], None, (None, None, None)),
        ([], "Alkmaar, Noord-Holland", ("Alkmaar", "noord-holland-noord", "noord-holland")),
    ],
)
def test_geo_resolve(ref, area, raw, expected):
    place = geo.resolve(area, raw, ref)
    assert (place.municipality, place.labour_market_region, place.province) == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Als developer werk je in een team aan de ontwikkeling van onze software.", "nl"),
        ("We are looking for a developer to join our team and work on the platform.", "en"),
        ("Python, Java", "unknown"),
        (None, "unknown"),
    ],
)
def test_language(text, expected):
    assert language.detect(text) == expected
