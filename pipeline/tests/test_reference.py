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
        region = ref.regions[ref.municipality_index[city]]
        assert region.province == "noord-holland"


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
