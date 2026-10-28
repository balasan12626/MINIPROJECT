"""F27 — shelter capacity from OSM building size and the Sphere living-space standard."""
import importlib.util
import math
from pathlib import Path

import pytest

from backend.geo import cities

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("sc", ROOT / "scripts" / "build_shelter_capacity.py")
sc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sc)


def _square(lat, lon, side_m):
    dlat = side_m / 110_574.0
    dlon = side_m / (111_320.0 * math.cos(math.radians(lat)))
    return [{"lat": lat, "lon": lon}, {"lat": lat, "lon": lon + dlon}, {"lat": lat + dlat, "lon": lon + dlon},
            {"lat": lat + dlat, "lon": lon}]


def test_area_of_a_known_square():
    pts = [(g["lat"], g["lon"]) for g in _square(25.6, 85.1, 100.0)]
    assert sc.polygon_area_m2(pts) == pytest.approx(10_000.0, rel=0.002)


def test_capacity_formula_levels_and_citation():
    b1 = {"type": "way", "geometry": _square(25.6, 85.1, 100.0), "tags": {"building": "school", "building:levels": "3"}}
    b2 = {"type": "way", "geometry": _square(25.61, 85.1, 50.0), "tags": {"building": "yes"}}
    cap = sc.capacity_from([b1, b2])
    floor = 10_000 * 3 + 2_500 * 1
    assert cap["floor_area_m2"] == pytest.approx(floor, rel=0.003)
    assert cap["capacity"] == math.floor(cap["floor_area_m2"] * sc.USABLE_SHARE / 3.5)
    assert cap["capacity_source"] == "Sphere standard from OSM footprint"
    assert "1 of 2" in cap["levels_source"] and cap["usable_share_source"].startswith("assumed")
    assert "Sphere Handbook 2018" in cap["capacity_citation"]["standard"] and "3.5" in cap["capacity_citation"]["figure"]
    assert sc.capacity_from([]) is None


def test_point_in_polygon():
    ring = [(0.0, 0.0), (0.0, 1.0), (1.0, 1.0), (1.0, 0.0)]
    assert sc.inside((0.5, 0.5), ring) and not sc.inside((1.5, 0.5), ring)


@pytest.mark.parametrize("cid", [c for c in cities.available_ids() if c != cities.LEGACY])
def test_every_shelter_says_how_its_capacity_was_made(cid):
    for s in cities.load_city(cid)["shelters"]:
        src = s["capacity_source"]
        assert src.startswith("assumed") or src == "Sphere standard from OSM footprint"
        if src.startswith("Sphere"):
            assert s["area_m2"] > 0 and s["m2_per_person"] == 3.5 and s["capacity_citation"]["url"]
            assert s["capacity"] == math.floor(s["floor_area_m2"] * s["usable_share"] / s["m2_per_person"])
