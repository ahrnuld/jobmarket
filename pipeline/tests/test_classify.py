from __future__ import annotations

import pytest

from jobmarket.classify import classify, classify_programmes, classify_seniority, extract_skills
from jobmarket.clean.normalise import normalise_title


def seniority(ref, title, description=None):
    return classify_seniority(normalise_title(title), description, ref)


@pytest.mark.parametrize(
    "title, description, expected",
    [
        ("Stagiair Softwareontwikkeling", None, "internship"),
        ("Afstudeerstage Data Science", None, "internship"),
        ("Internship Backend Developer", None, "internship"),
        ("Junior Java Developer", None, "junior"),
        ("Traineeship IT", None, "junior"),
        ("Medior .NET Developer", None, "medior"),
        ("Senior Full-Stack Engineer", None, "senior"),
        ("Lead Software Engineer", None, "senior"),
        ("Junior/Medior Developer", None, "junior"),  # lowest level it is open to
        ("Developer", "Je hebt 0-2 jaar werkervaring.", "junior"),
        ("Developer", "You have 3+ years of professional experience.", "medior"),
        ("Developer", "Minimaal 6 jaar relevante ervaring.", "senior"),
        ("Developer", "Ben je pas afgestudeerd? Welkom!", "junior"),
        ("Developer", "Werk 32 tot 40 uur per week.", "unknown"),
        ("Developer", None, "unknown"),
    ],
)
def test_seniority(ref, title, description, expected):
    assert seniority(ref, title, description) == expected


@pytest.mark.parametrize(
    "title, expected",
    [
        ("Junior Java Developer (m/v/x)", {"informatica"}),
        ("Front-end Developer", {"informatica"}),
        ("Systeem Ontwikkelaar", {"informatica"}),
        ("Medior Low-code Developer ServiceNow", {"informatica"}),
        ("Functioneel Beheerder", {"business-it-management"}),
        ("Business Analist", {"business-it-management"}),
        ("Data Analist", {"business-it-management"}),
        ("Data Engineer", {"informatica"}),
        ("PLC-programmeur", {"technische-informatica"}),
        ("Embedded Software Engineer", {"technische-informatica"}),
        ("DevOps Engineer", {"informatica", "technische-informatica"}),
        ("Netwerkbeheerder", {"technische-informatica"}),  # compound word, no space
        ("Business Developer", set()),  # sales, not ICT
        ("Werkvoorbereider", set()),
    ],
)
def test_programmes(ref, title, expected):
    assert set(classify_programmes(normalise_title(title), ref)) == expected


def test_skills_from_title_and_text(ref):
    skills = extract_skills(
        "Senior C# Developer",
        "Je werkt met .NET, Azure, Kubernetes en SQL. Kennis van JavaScript is een pré.",
        ref,
    )
    assert {"csharp", "dotnet", "azure", "kubernetes", "sql", "javascript"} <= set(skills)
    assert "java" not in skills  # 'JavaScript' must not count as Java


def test_skill_patterns_avoid_common_false_positives(ref):
    skills = extract_skills(
        "Monteur", "Je werkt in een team en hebt rijbewijs B. C-rijbewijs.", ref
    )
    assert skills == []


def test_ict_requires_role_family_or_it_category_with_tech_skill(ref):
    def is_ict(title, desc, cat):
        return classify(title, normalise_title(title), desc, cat, ref).is_ict

    assert is_ict("Java Developer", None, "unknown")
    assert is_ict("IT Support Professional", "Beheer van Windows Server en Intune.", "it-jobs")
    assert not is_ict("Werkvoorbereider", "Planning en montage. Excel.", "it-jobs")
    assert not is_ict("Accountmanager", "Kennis van Python.", "sales-jobs")
