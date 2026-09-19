from __future__ import annotations

import pytest

from jobmarket.config import REPO_ROOT
from jobmarket.db import connect, init_schema
from jobmarket.reference import load_reference, sync_sources


@pytest.fixture(scope="session")
def ref():
    """The real reference data from data/reference, so tests catch mistakes in those files."""
    return load_reference(REPO_ROOT / "data" / "reference")


@pytest.fixture
def conn(ref):
    c = connect(":memory:")
    init_schema(c)
    sync_sources(c, ref)
    yield c
    c.close()
