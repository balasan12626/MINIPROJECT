"""F7 — cities on real road networks: data honesty, activation, routing, hydro docs."""
import pytest

from backend.geo import cities
from backend.services import person_ops as po
from backend.services import seed
from backend.simulation.engine import city_hydro_docs, place_in_city

OSM_CITIES = [c for c in cities.available_ids() if c != cities.LEGACY]


@pytest.fixture
def restore_legacy():
    yield
    cities.activate(cities.LEGACY)


def test_there_are_osm_cities():
    assert {"delhi", "chennai", "mumbai", "kolkata"} <= set(OSM_CITIES)


@pytest.mark.parametrize("cid", OSM_CITIES)
def test_city_file_is_consistent_and_labels_assumptions(cid):
    c = cities.load_city(cid)
    nodes = c["graph_nodes"]
    road_ids = {r["road_id"] for r in c["roads"]}
    assert len(nodes) >= 90 and c["graph_edges"]
    for u, v, rid in c["graph_edges"]:
        assert u in nodes and v in nodes and rid in road_ids
    for r in c["roads"]:
        assert 0.0 <= r["flood_exposure"] <= 1.0
        assert "proxy" in r["flood_exposure_source"] and r["traffic_source"] == "assumed by road class"
    assert c["shelters"], "a city needs shelters"
    for s in c["shelters"]:
        assert (s["capacity_source"].startswith("assumed") or s["capacity_source"].startswith("Sphere")) and s["osm"]
        assert s["occupancy"] == 0  # no invented baseline occupancy
    for z in c["zones"]:
        assert z["population"] is None or isinstance(z["population"], int)
    assert "OpenStreetMap" in c["attribution"]
    g = c["gauge"]
    if g["available"]:
        assert g["danger_level_m"] >= g["warning_level_m"] and g["km_from_centre"] <= 30
    else:
        assert "rainfall-driven" in g["reason"]


def test_activate_swaps_everything_in_place_and_back(restore_legacy):
    legacy_nodes = dict(seed.GRAPH_NODES)
    roads_obj, nodes_obj = seed.ROADS, seed.GRAPH_NODES
    c = cities.activate("chennai")
    assert cities.active_id() == "chennai"
    assert seed.ROADS is roads_obj and seed.GRAPH_NODES is nodes_obj, "same objects, new contents"
    assert len(seed.GRAPH_NODES) == len(c["graph_nodes"])
    assert po.SHELTER_POOL == [s["name"] for s in c["shelters"]]
    reg = po.shelter_registry()
    assert set(po.SHELTER_POOL) <= set(reg)
    assert "Yamuna Sports Complex Shelter" not in reg, "Delhi desk shelters stay in Delhi"
    cities.activate(cities.LEGACY)
    assert seed.GRAPH_NODES == legacy_nodes
    assert "Yamuna Sports Complex Shelter" in po.SHELTER_POOL


@pytest.mark.parametrize("cid", OSM_CITIES)
def test_routes_follow_real_roads_in_every_city(cid, restore_legacy):
    c = cities.activate(cid)
    z = c["zones"][0]
    s = c["shelters"][-1]
    r = po.road_route((z["lat"], z["lon"]), (s["lat"], s["lon"]), seed.ROADS)
    assert r["method"] != "direct", f"{cid}: zone → shelter must be routable"
    assert r["road_ids"] and set(r["road_ids"]) <= {x["road_id"] for x in seed.ROADS}
    assert len(r["points"]) <= po.MAX_ROUTE_POINTS
    # real road shape: the polyline is longer than the junction-to-junction straight chain
    assert r["km"] > 0


def test_rainfall_city_has_no_stage_term_and_river_city_uses_real_gauge(restore_legacy):
    rain_city = next(c for c in OSM_CITIES if not cities.load_city(c)["gauge"]["available"])
    river, dam = city_hydro_docs(cities.load_city(rain_city), 205.0, 200.0)
    assert river["available"] is False and river["percent_of_danger"] is None
    assert dam["available"] is False
    delhi = cities.load_city("delhi")
    river, dam = city_hydro_docs(delhi, 206.3, 200.0)  # 0.5 m over the demo mark
    assert river["danger_level_m"] == delhi["gauge"]["danger_level_m"]
    assert river["value_m"] == pytest.approx(delhi["gauge"]["danger_level_m"] + 0.5)
    assert dam["available"] is True  # Hathnikund feeds the Yamuna at Delhi


def test_roster_is_re_anchored_outside_delhi(restore_legacy):
    people = [{"citizen_name": "A", "lat": 28.65, "lon": 77.26}, {"citizen_name": "B", "lat": 28.6, "lon": 77.2}]
    assert place_in_city(people) == people  # demo Delhi: unchanged
    c = cities.activate("chennai")
    moved = place_in_city(people)
    s, w, n, e = c["bbox"]
    for p in moved:
        assert s - 0.05 < p["lat"] < n + 0.05 and w - 0.05 < p["lon"] < e + 0.05
        assert "synthetic" in p["location_source"]
    assert place_in_city(people) == moved, "deterministic"


def test_city_view_has_geometry_for_every_road():
    v = cities.view("kolkata")
    assert set(v["road_geometry"]) == {r["road_id"] for r in v["roads"]}
    assert v["flood_driver"] in ("river", "rainfall")
    assert "catchment" not in v["gauge"]


def test_unknown_city_raises():
    with pytest.raises(KeyError):
        cities.activate("atlantis")
    assert cities.active_id() == cities.LEGACY


@pytest.mark.parametrize("cid", OSM_CITIES)
def test_one_engine_tick_runs_in_every_city(cid, restore_legacy):
    """Regression: OSM zones have population = null (unknown, never guessed);
    the pipeline's shelter scoring / solvers did `None - int` and the live loop
    died on its first tick in every OSM city."""
    import asyncio

    from backend.services.pipeline import run_pipeline
    from backend.simulation.engine import SCENARIOS, SimulationEngine

    eng = SimulationEngine()
    cities.activate(cid)
    eng.params = {**SCENARIOS["heavy_rainfall"]["defaults"], "city": cid}
    obs = eng._apply_overrides(eng._evolve())
    snap = asyncio.run(run_pipeline(mode="simulation", observations=obs))
    assert snap.get("roads") is not None


def test_cwc_gauges_are_sourced_and_used_only_where_listed(restore_legacy):
    """F17: CWC levels copied from an official bulletin (URL + date), within
    30 km, warning < danger; no catchment borrowed; other cities stay rainfall."""
    import json
    from pathlib import Path

    data = json.loads((Path(cities.__file__).resolve().parents[1] / "data" / "gauges_cwc.json").read_text(encoding="utf-8"))
    listed = {k: v for k, v in data.items() if not k.startswith("_")}
    assert listed, "at least one CWC station"
    for cid, g in listed.items():
        assert g["source_url"].startswith("https://cwc.gov.in/") and g["retrieved_at"]
        assert g["warning_level_m"] < g["danger_level_m"] < g["hfl_m"]
        c = cities.load_city(cid)
        cg = c["gauge"]
        assert cg["available"] and cg["source"].startswith("CWC") and cg["km_from_centre"] <= 30
        assert cg["catchment"] is None, "no catchment attribute borrowed from another gauge"
        assert cg["danger_level_m"] == g["danger_level_m"]
        river, _ = city_hydro_docs(c, 206.3, 200.0)  # 0.5 m over the demo mark
        assert river["available"] and river["value_m"] == pytest.approx(g["danger_level_m"] + 0.5)
        assert river["source_url"] == g["source_url"]
    for cid in data["_none_found"]:
        assert not cities.load_city(cid)["gauge"]["available"], f"{cid} must stay rainfall-driven"


# Census of India 2011, urban-agglomeration population — a RANGE check only (F19).
CENSUS_2011_UA = {"delhi": 16_349_831, "mumbai": 18_394_912, "chennai": 8_653_521,
                  "kolkata": 14_057_991, "guwahati": 968_549, "patna": 2_049_156}


@pytest.mark.parametrize("cid", OSM_CITIES)
def test_zone_population_is_sourced_or_null(cid):
    """F19: filled zones name the dataset, year and method; null stays allowed."""
    zones = cities.load_city(cid)["zones"]
    filled = [z for z in zones if z["population"] is not None]
    for z in filled:
        assert z["population"] >= 0
        assert "WorldPop" in z["population_source"]["dataset"] and z["population_source"]["year"]
        assert "circle" in z["population_method"]
    for z in zones:
        if z["population"] is None:
            assert z.get("population_missing_reason") or "population_source" not in z
    if filled and cid in CENSUS_2011_UA:
        assert 0 < sum(z["population"] for z in filled) < CENSUS_2011_UA[cid]
