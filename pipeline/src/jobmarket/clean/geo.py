"""Resolve a vacancy's location to municipality, labour market region and province (FR-07)."""

from __future__ import annotations

from dataclasses import dataclass

from jobmarket.reference import Reference


def _strip_prefix(name: str) -> str:
    """Adzuna writes "Provincie Utrecht" to tell the province from the city of the same name."""
    name = name.strip().lower()
    return name.removeprefix("provincie ").strip()


def _clean_name(name: str) -> str:
    name = name.strip()
    return name[len("Provincie ") :] if name.lower().startswith("provincie ") else name


@dataclass(frozen=True)
class Place:
    municipality: str | None
    labour_market_region: str | None
    province: str | None


def resolve(area: list[str], location_raw: str | None, ref: Reference) -> Place:
    """`area` is the source's hierarchy, e.g. ["Nederland", "Noord-Holland", "Haarlem"].

    Level 1 is the province, level 2 the municipality, deeper levels are districts or villages.
    Villages are also tried against the municipality list, as are the parts of `location_raw`
    ("Wijk aan Zee, Beverwijk"), for sources that have no hierarchy.
    """
    province = None
    if len(area) > 1:
        province = ref.province_index.get(_strip_prefix(area[1]))

    # Adzuna sometimes prefixes municipalities too ("Provincie Utrechtse Heuvelrug").
    candidates = [_clean_name(a) for a in area[2:]]
    if location_raw:
        candidates += [_clean_name(p) for p in location_raw.split(",")]
    for name in candidates:
        region_id = ref.municipality_index.get(name.lower())
        if region_id:
            region = ref.regions[region_id]
            if province and province != region.province:
                continue  # same place name in another province
            return Place(name, region_id, region.province)

    municipality = _clean_name(area[2]) if len(area) > 2 else None
    if province is None and location_raw:
        for part in location_raw.split(","):
            province = ref.province_index.get(_strip_prefix(part)) or province
    return Place(municipality, None, province)
