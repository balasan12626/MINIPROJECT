"""F29 — silent zones from flooded towers (synthetic towers; real data needs OPENCELLID_TOKEN)."""
import pytest

from backend.agents.mas import MultiAgentSystem
from backend.services import towers as tw

LAT, LON = 25.60, 85.13
CITY = {"id": "testcity", "bbox": [25.58, 85.10, 25.62, 85.16],
        "zones": [{"zone_id": "Z1", "name": "Low ward", "lat": 25.60, "lon": 85.13},
                  {"zone_id": "Z2", "name": "High ward", "lat": 25.61, "lon": 85.15}]}


def _t(lat, lon, exp, radio="LTE"):
    return {"lat": lat, "lon": lon, "radio": radio, "flood_exposure": exp}


def test_flooded_follows_the_road_rule():
    t = _t(LAT, LON, 0.70)
    assert not tw.flooded(t, 0.10) and tw.flooded(t, 0.15)


def test_flooded_tower_makes_silence_only_where_no_other_tower_covers():
    cells = tw.grid(CITY["bbox"])
    low = _t(LAT, LON, 0.9)  # flooded at any blockage
    assert tw.silent_cells([low], 0.0, cells), "alone, its whole circle goes silent"
    backup = _t(LAT, LON, 0.1)  # dry tower on the same spot covers the same circle
    assert tw.silent_cells([low, backup], 0.0, cells) == []
    partial = _t(LAT, LON + 0.012, 0.1)  # dry tower ~1.2 km east covers only part
    s = tw.silent_cells([low, partial], 0.0, cells)
    assert s and len(s) < len(tw.silent_cells([low], 0.0, cells))
    assert all(p[1] < LON + 0.005 for p in s), "the silent part is the side the dry tower does not reach"
    assert tw.silent_cells([_t(LAT, LON, 0.1)], 0.0, cells) == [], "no flooded tower → nothing silent"


def test_silent_zones_view_and_feature_off(monkeypatch):
    assert tw.silent_zones({**CITY, "id": "no_such_city"}, 0.5) is None, "no towers file → feature off"
    monkeypatch.setattr(tw, "load_towers", lambda cid: {"towers": [_t(LAT, LON, 0.9)], "attribution": "© OpenCelliD"})
    v = tw.silent_zones(CITY, 0.0)
    assert v["towers_flooded"] == 1 and v["zones"][0]["zone_id"] == "Z1"
    assert v["zones"][0]["area_km2"] > 0 and "modelled" in v["label"] and "assumed" in v["coverage_source"]
    assert tw.is_silent(LAT, LON, v) and not tw.is_silent(25.619, 85.159, v)


def test_mas_announces_each_silent_area_once():
    m = MultiAgentSystem()
    view = {"zones": [{"zone_id": "Z1", "name": "Low ward", "area_km2": 2.5}]}
    assert m.announce_silent_zones("R", view) == 1
    assert m.announce_silent_zones("R", view) == 0
    assert m.announce_silent_zones("R", None) == 0
    assert any("SILENT AREA near Low ward" in x["text"] for x in m.messages)


@pytest.mark.asyncio
async def test_patrol_sends_the_nearest_free_ambulance():
    from backend.services.seed import RESCUE_TEAMS
    from backend.simulation.engine import SimulationEngine

    eng = SimulationEngine()
    eng.status, eng.run_id = "running", "R"
    eng._teams_cache = list(RESCUE_TEAMS)
    eng.silent_view = {"zones": [{"zone_id": "Z1", "name": "ITO", "centre": [28.6284, 77.2410], "area_km2": 1.0}]}
    out = await eng.send_patrol("Z1")
    unit = out["patrol"]["unit"]
    assert eng.staging[unit]["label"].startswith("patrol") and eng.staging[unit]["points"]
    with pytest.raises(KeyError):
        await eng.send_patrol("nope")
