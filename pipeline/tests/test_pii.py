from __future__ import annotations

import pytest

from jobmarket.clean.pii import scrub


@pytest.mark.parametrize(
    "text, leaked",
    [
        ("Mail naar s.devries@voorbeeld.nl voor info.", "s.devries@voorbeeld.nl"),
        ("Bel 06-12345678.", "12345678"),
        ("Bel 06 1234 5678.", "1234 5678"),
        ("Telefoon 020 123 4567.", "123 4567"),
        ("Bel +31 6 98765432.", "98765432"),
        ("Call +31 (0)20 765 4321.", "765 4321"),
        ("Neem contact op met Sanne de Vries via mail.", "Sanne"),
        ("Contactpersoon: Pieter van den Berg, telefoon", "Pieter"),
        ("Bel onze recruiter Fatima El Amrani op", "Fatima"),
        ("Bel Sanne de Vries op 06-12345678.", "Sanne"),
        ("Mail met Ahmed Yilmaz voor info.", "Ahmed"),
        ("Questions? Contact Emma Jansen at", "Emma"),
        ("Recruiter: Jan-Willem Bakker", "Bakker"),
        ("Voor meer informatie bij Kees Smit terecht", "Kees"),
    ],
)
def test_personal_data_is_removed(text, leaked):
    assert leaked not in scrub(text)


@pytest.mark.parametrize(
    "text",
    [
        "Salaris tussen € 3.500 en € 4.800 per maand, 2 tot 5 jaar ervaring.",
        "Neem contact op met ons team via het formulier.",
        "Contact our HR department.",
        "Werken met Python, Java en C# sinds 2019 (32 tot 40 uur).",
    ],
)
def test_ordinary_text_is_left_alone(text):
    assert scrub(text) == text


def test_none_and_empty():
    assert scrub(None) is None
    assert scrub("") == ""
