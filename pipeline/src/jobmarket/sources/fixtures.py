"""Deterministic synthetic vacancies (source 'fixture').

These are NOT real vacancies. They exist so the pipeline, tests and site can be developed and
demonstrated without API access, and they deliberately contain the awkward cases the pipeline must
handle: reposted duplicates, personal data in the text, non-ICT noise in the IT category, Dutch and
English postings, vague seniority, missing salaries. Everything is flagged is_sample=True, and the
site labels any figure built from them as sample data.
"""

from __future__ import annotations

import random
from collections.abc import Iterator
from datetime import date, timedelta

from jobmarket.models import VacancyRecord

# (title template, weight). {lvl} is replaced by a seniority word or removed.
TITLES_NL = [
    ("{lvl}Software Developer", 10),
    ("{lvl}Java Ontwikkelaar", 5),
    ("{lvl}.NET Developer", 6),
    ("{lvl}Python Developer", 4),
    ("{lvl}Full-Stack Developer", 6),
    ("{lvl}Front-end Developer", 5),
    ("{lvl}Back-end Ontwikkelaar", 3),
    ("{lvl}Mobile App Developer", 2),
    ("{lvl}Data Engineer", 4),
    ("{lvl}DevOps Engineer", 4),
    ("{lvl}Cloud Engineer", 3),
    ("{lvl}Security Specialist", 2),
    ("{lvl}Test Automation Engineer", 2),
    ("{lvl}Business Analist", 4),
    ("{lvl}Functioneel Beheerder", 5),
    ("{lvl}Informatieanalist", 3),
    ("{lvl}ERP Consultant", 3),
    ("{lvl}Data Analist", 5),
    ("{lvl}BI Consultant", 2),
    ("Product Owner", 2),
    ("{lvl}IT Projectleider", 1),
    ("{lvl}Embedded Software Engineer", 3),
    ("{lvl}PLC-programmeur", 3),
    ("{lvl}IoT Engineer", 1),
    ("{lvl}Netwerkbeheerder", 3),
    ("{lvl}Systeembeheerder", 3),
    ("Stagiair Softwareontwikkeling", 2),
    ("Afstudeerstage Data Science", 1),
    ("Stage Business IT", 1),
    ("Werkstudent IT Support", 1),
    ("Traineeship IT", 1),
]
# Non-ICT titles that show up in Adzuna's IT category (observed in the real feed).
NOISE_TITLES = [
    ("Werkvoorbereider", 2),
    ("Elektromonteur", 2),
    ("Accountmanager IT", 1),
    ("Business Developer", 1),
    ("Monteur Beveiligingssystemen", 1),
]

LEVEL_WORDS = [("", 55), ("Junior ", 18), ("Medior ", 12), ("Senior ", 13), ("Lead ", 2)]

SKILLS_BY_HINT = {
    "Developer": [
        "Java",
        "C#",
        ".NET",
        "JavaScript",
        "TypeScript",
        "React",
        "Angular",
        "SQL",
        "Git",
        "Azure",
        "Docker",
        "Scrum",
        "REST API's",
        "Python",
        "PHP",
        "Vue.js",
    ],
    "Ontwikkelaar": ["Java", "Spring Boot", "SQL", "Git", "Scrum", "Kotlin", "Docker"],
    "Data": [
        "Python",
        "SQL",
        "Power BI",
        "Spark",
        "Azure",
        "dbt",
        "machine learning",
        "Excel",
        "datamodellering",
        "generative AI",
    ],
    "DevOps": ["Kubernetes", "Terraform", "Azure DevOps", "CI/CD", "Linux", "AWS", "Docker"],
    "Cloud": ["Azure", "AWS", "Terraform", "Kubernetes", "Linux", "networking"],
    "Security": ["security", "ISO 27001", "NIS2", "Linux", "SOC"],
    "Test": ["Selenium", "Cypress", "test automation", "Java", "CI/CD", "Scrum"],
    "Analist": ["requirements", "BPMN", "SQL", "Agile", "stakeholders", "user stories"],
    "Beheerder": ["TOPdesk", "SQL", "ITIL", "Office 365", "stakeholders", "Excel"],
    "Consultant": ["SAP", "Exact Online", "AFAS", "Dynamics 365", "procesverbetering", "Excel"],
    "Product": ["Scrum", "stakeholders", "user stories", "Agile", "Jira"],
    "Projectleider": ["Prince2", "projectmanagement", "stakeholders", "Agile"],
    "Embedded": ["C++", "embedded C", "RTOS", "firmware", "Python", "Linux", "elektronica"],
    "PLC": ["PLC", "SCADA", "Siemens TIA", "Codesys", "robotica"],
    "IoT": ["IoT", "Python", "Azure", "embedded C", "MQTT"],
    "beheerder": [
        "Windows Server",
        "Active Directory",
        "Microsoft 365",
        "networking",
        "Cisco",
        "Linux",
        "Intune",
    ],
    "Stage": ["Python", "Java", "SQL", "Scrum", "Git"],
    "IT": ["Windows Server", "Microsoft 365", "Excel"],
}
# Skills whose share rises or falls over time, so the trends page has something to show.
RISING = {"generative AI", "Kubernetes", "Terraform", "NIS2"}
FALLING = {"PHP", "Angular"}

EMPLOYERS = [
    "Voorbeeld Software B.V.",
    "Demo Data Solutions BV",
    "Fictief ICT Groep N.V.",
    "Testbedrijf Automatisering",
    "Sample Systems Nederland",
    "Proef Consultancy BV",
    "Nep Logistiek B.V.",
    "Voorbeeldgemeente",
    "Demo Bank N.V.",
    "Fictieve Zorggroep",
    "Proefwerk Industrie BV",
    "Oefen Energie B.V.",
    "Sample Webbureau",
    "Voorbeeld Retail Groep",
]

LOCATIONS = [  # (area list, weight)
    (["Nederland", "Noord-Holland", "Amsterdam"], 26),
    (["Nederland", "Noord-Holland", "Haarlem"], 7),
    (["Nederland", "Noord-Holland", "Alkmaar"], 5),
    (["Nederland", "Noord-Holland", "Haarlemmermeer", "Hoofddorp"], 4),
    (["Nederland", "Noord-Holland", "Zaanstad"], 2),
    (["Nederland", "Noord-Holland", "Hilversum"], 2),
    (["Nederland", "Noord-Holland", "Hoorn"], 1),
    (["Nederland", "Noord-Holland", "Den Helder"], 1),
    (["Nederland", "Utrecht", "Utrecht"], 14),
    (["Nederland", "Zuid-Holland", "Rotterdam"], 12),
    (["Nederland", "Zuid-Holland", "Den Haag"], 9),
    (["Nederland", "Noord-Brabant", "Eindhoven"], 8),
    (["Nederland", "Gelderland", "Arnhem"], 3),
    (["Nederland", "Overijssel", "Enschede"], 2),
    (["Nederland", "Groningen", "Groningen"], 3),
    (["Nederland", "Flevoland", "Almere"], 2),
    (["Nederland"], 2),
]

CONTACT_NL = [
    "Vragen? Neem contact op met Sanne de Vries via s.devries@voorbeeld.invalid of 06-12345678.",
    "Contactpersoon: Pieter van den Berg, telefoon 020 123 4567.",
    "Solliciteer direct of bel onze recruiter Fatima El Amrani op +31 6 98765432.",
]
CONTACT_EN = [
    "Questions? Contact Emma Jansen at emma.jansen@example.invalid or +31 (0)20 765 4321."
]


def _pick(rng: random.Random, weighted: list[tuple]) -> tuple:
    return rng.choices(weighted, weights=[w for *_, w in weighted], k=1)[0]


def _skills_for(title: str) -> list[str]:
    for hint, skills in SKILLS_BY_HINT.items():
        if hint in title:
            return skills
    return SKILLS_BY_HINT["Developer"]


def _description(rng: random.Random, title: str, level: str, english: bool, progress: float) -> str:
    pool = _skills_for(title)
    skills = []
    for s in pool:
        p = 0.45
        if s in RISING:
            p = 0.1 + 0.6 * progress
        elif s in FALLING:
            p = 0.6 - 0.45 * progress
        if rng.random() < p:
            skills.append(s)
    skills = skills or pool[:2]
    years = {"Junior ": "0-2", "Medior ": "3-5", "Senior ": "6+", "Lead ": "8+"}.get(level)
    if english:
        text = (
            f"We are looking for a {title.strip()} to join our team. You work with "
            f"{', '.join(skills)}. "
        )
        if years:
            text += f"You have {years} years of experience. "
        elif rng.random() < 0.3:
            text += "Recent graduates are welcome. "
        text += "Fluent English is required. "
        if rng.random() < 0.25:
            text += rng.choice(CONTACT_EN) + " "
    else:
        text = (
            f"Als {title.strip()} werk je in een team aan uitdagende projecten. Je werkt met "
            f"{', '.join(skills)}. "
        )
        if years:
            text += f"Je hebt {years} jaar werkervaring. "
        elif rng.random() < 0.3:
            text += "Ben je pas afgestudeerd? Dan ben je van harte welkom. "
        if rng.random() < 0.5:
            text += "Goede beheersing van de Nederlandse taal is een vereiste. "
        if rng.random() < 0.25:
            text += rng.choice(CONTACT_NL) + " "
    # Mimic the Adzuna API, which truncates descriptions at ~500 characters.
    return text[:497] + "…" if len(text) > 500 else text


def _salary(rng: random.Random, level: str, title: str) -> tuple[float | None, float | None]:
    if rng.random() > 0.4:  # most postings state no salary
        return None, None
    if "tage" in title or "Werkstudent" in title:
        # Internship allowances are stated per month, like real postings ("€ 500 stagevergoeding").
        lo = float(rng.choice([300, 400, 450, 500, 600]))
        return lo, lo + rng.choice([0, 100, 150])
    base = {"Junior ": 38000, "Medior ": 50000, "Senior ": 64000, "Lead ": 75000}.get(level, 48000)
    lo = round(base * rng.uniform(0.85, 1.05), -2)
    return lo, round(lo * rng.uniform(1.1, 1.3), -2)


def generate(
    n: int = 6000, months: int = 24, end: date | None = None, seed: int = 2026
) -> Iterator[VacancyRecord]:
    rng = random.Random(seed)
    end = end or date.today()
    span_days = months * 30
    produced = 0
    while produced < n:
        age = int(span_days * (rng.random() ** 1.15))  # slightly more recent ads: growing volume
        posted = end - timedelta(days=age)
        progress = 1 - age / span_days
        noise = rng.random() < 0.08
        if noise:
            title, _ = _pick(rng, NOISE_TITLES)
            level = ""
        else:
            template, _ = _pick(rng, TITLES_NL)
            level = _pick(rng, LEVEL_WORDS)[0] if "{lvl}" in template else ""
            title = template.replace("{lvl}", level)
            if rng.random() < 0.15:
                title += rng.choice([" (m/v/x)", " m/v", " (v/m/x)", " - Amsterdam"])
        english = rng.random() < 0.3
        area, _ = _pick(rng, LOCATIONS)
        smin, smax = _salary(rng, level, title)
        rec = VacancyRecord(
            source_id="fixture",
            external_id=f"fx-{seed}-{produced}",
            title=title,
            posted_at=posted.isoformat(),
            employer=rng.choice(EMPLOYERS),
            location_raw=", ".join(reversed(area[1:])) or "Nederland",
            area=list(area),
            description=(
                f"Als {title} ben je verantwoordelijk voor planning, montage en onderhoud op "
                "locatie bij onze klanten. Rijbewijs B is een vereiste."
                if noise
                else _description(rng, title, level, english, progress)
            ),
            source_category="it-jobs" if (noise or rng.random() < 0.4) else "unknown",
            salary_min=smin,
            salary_max=smax,
            salary_is_predicted=False if smin else None,
            contract_time="full_time",
            url=None,
            is_sample=True,
        )
        yield rec
        produced += 1
        # About 8% get reposted (new id, same content) within a few weeks: tests deduplication.
        if produced < n and rng.random() < 0.08:
            repost_date = min(end, posted + timedelta(days=rng.randint(3, 25)))
            yield VacancyRecord(
                **{
                    **rec.__dict__,
                    "external_id": f"fx-{seed}-{produced}",
                    "posted_at": repost_date.isoformat(),
                }
            )
            produced += 1
