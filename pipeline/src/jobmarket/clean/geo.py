"""Resolve a vacancy's location to municipality, COROP area, labour market region and province.

Used by the region filter (FR-07) and the map. The lookup goes through the generated municipality
table (data/reference/municipalities.csv), which also holds names that no longer exist, because
vacancy sources keep using them.
"""

from __future__ import annotations

from dataclasses import dataclass

from jobmarket.reference import Reference
from jobmarket.reference_geo import normalise_name


def _clean_name(name: str) -> str:
    """Adzuna writes "Provincie Utrecht" to tell the province from the city of the same name."""
    name = name.strip()
    return name[len("Provincie ") :] if name.lower().startswith("provincie ") else name


@dataclass(frozen=True)
class Place:
    municipality: str | None
    labour_market_region: str | None
    province: str | None
    corop: str | None = None


def resolve(area: list[str], location_raw: str | None, ref: Reference) -> Place:
    """`area` is the source's hierarchy, e.g. ["Nederland", "Noord-Holland", "Haarlem"].

    Level 1 is the province, level 2 the municipality, deeper levels are districts or villages.
    Villages are also tried against the municipality table, as are the parts of `location_raw`
    ("Wijk aan Zee, Beverwijk"), for sources without a hierarchy.
    """
    province = None
    if len(area) > 1:
        province = ref.province_index.get(normalise_name(_clean_name(area[1])))

    candidates = [_clean_name(a) for a in area[2:]]
    if location_raw:
        candidates += [_clean_name(p) for p in location_raw.split(",")]
    for name in candidates:
        municipality = ref.municipalities.get(normalise_name(name))
        if municipality:
            if province and municipality.province != province:
                continue  # same place name in another province
            return Place(
                municipality.name, municipality.region, municipality.province, municipality.corop
            )

    if province is None and location_raw:
        for part in location_raw.split(","):
            province = ref.province_index.get(normalise_name(_clean_name(part))) or province
    return Place(_clean_name(area[2]) if len(area) > 2 else None, None, province, None)
