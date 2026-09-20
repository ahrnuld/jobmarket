from __future__ import annotations

import shutil

import pytest

from jobmarket.config import REPO_ROOT
from jobmarket.reference import ReferenceError, load_reference


def test_real_reference_data_loads(ref):
    assert set(ref.programmes) == {
        "informatica",
        "business-it-management",
        "technische-informatica",
    }
    assert {"adzuna", "cbs", "roa", "hbo_monitor", "esco", "uwv"} <= set(ref.sources)
    assert len(ref.skills) >= 50


def test_every_programme_has_a_role_family(ref):
    covered = {p for rf in ref.role_families for p in rf.programmes}
    assert covered == set(ref.programmes)


def test_all_noord_holland_focus_cities_are_mapped(ref):
    for city in ["alkmaar", "haarlem", "amsterdam"]:
        municipality = ref.municipalities[city]
        assert ref.regions[municipality.region].province == "noord-holland"
        assert ref.corops[municipality.corop].province == "noord-holland"


def test_every_municipality_has_a_known_corop_region_and_province(ref):
    assert len(ref.corops) == 40
    for municipality in ref.municipalities.values():
        assert municipality.corop in ref.corops
        # Municipalities abolished before the 2014 labour market regions have no region.
        assert municipality.region is None or municipality.region in ref.regions
        assert municipality.province in ref.provinces


def test_municipalities_that_no_longer_exist_are_still_found(ref):
    # Sources keep using names of merged municipalities; the table covers 2010 onwards.
    assert ref.municipalities["naarden"].corop == "het-gooi-en-vechtstreek"
    assert ref.municipalities["sneek"].province == "friesland"


def test_province_aliases(ref):
    assert ref.province_index["north holland"] == "noord-holland"


def test_invalid_pattern_is_reported(tmp_path):
    ref_dir = tmp_path / "reference"
    shutil.copytree(REPO_ROOT / "data" / "reference", ref_dir)
    skills = ref_dir / "skills.yaml"
    skills.write_text(
        "skills:\n  - { id: bad, label: Bad, category: x, patterns: ['(unclosed'] }\n",
        encoding="utf-8",
    )
    with pytest.raises(ReferenceError, match="invalid pattern"):
        load_reference(ref_dir)


def test_unknown_programme_in_role_family_is_reported(tmp_path):
    ref_dir = tmp_path / "reference"
    shutil.copytree(REPO_ROOT / "data" / "reference", ref_dir)
    path = ref_dir / "programmes.yaml"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "programmes: [informatica]", "programmes: [wiskunde]", 1
        ),
        encoding="utf-8",
    )
    with pytest.raises(ReferenceError, match="unknown programme"):
        load_reference(ref_dir)
