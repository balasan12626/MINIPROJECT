"""F10 — road flood-time forecast from the engine's own closure rule, and routing around it."""
from backend.services import person_ops as po
from backend.services.seed import GRAPH_NODES, ROADS
from backend.simulation.engine import SimulationEngine


def _engine(scenario="road_blockage", blockage=0.1):
    eng = SimulationEngine()
    eng.run_id = "SIM-FC"
    eng.status = "running"
    eng.params = {"scenario": scenario, "road_blockage": blockage, "ticks": 36, "tick_seconds": 2.0}
    eng.tick = 0
    return eng


def _roads(blocked=()):
    out = [dict(r) for r in ROADS]
    for r in out:
        r["blocked"] = r["road_id"] in blocked
        r["accessible"] = not r["blocked"]
    return out


def test_forecast_follows_the_engine_rule_and_skips_closed_and_operator_roads():
    eng = _engine()
    eng.auto_blocked = {"R08"}
    eng.road_overrides = {"R04": False}
    fc = eng.road_forecast()
    assert "R08" not in fc and "R04" not in fc
    # every forecast closure is exactly where 0.85 - blockage(t) first drops to the road's exposure
    expo = {r["road_id"]: r["flood_exposure"] for r in ROADS}
    for rid, f in fc.items():
        k = f["closes_in_ticks"]
        b = eng._evolve(eng.tick + k)["blockage"]
        assert expo[rid] >= 0.85 - b
        if k > 1:
            assert expo[rid] < 0.85 - eng._evolve(eng.tick + k - 1)["blockage"]
        assert f["closes_in_sim_min"] == round(k * 2.0 * po.TIME_SCALE / 60.0, 1)
    # higher exposure never closes later
    ordered = sorted(fc.items(), key=lambda kv: -expo[kv[0]])
    ticks = [f["closes_in_ticks"] for _, f in ordered]
    assert ticks == sorted(ticks)
    assert fc, "a road-blockage scenario must forecast some closures"


def test_forecast_is_empty_when_no_run():
    eng = SimulationEngine()
    assert eng.road_forecast() == {}


def test_first_closed_road_uses_arrival_time():
    cand = {"lead_km": 0.0, "edge_seq": [("RA", 5.0), ("RB", 5.0)]}  # 5 weighted km = 12 min each
    assert po.first_closed_road(cand, {"RB": 30.0}) is None  # reach RB at 12 min, closes at 30
    assert po.first_closed_road(cand, {"RB": 10.0}) == "RB"
    assert po.first_closed_road(cand, {"RA": 5.0}, depart_min=6.0) == "RA"
    assert po.first_closed_road(cand, None) is None


def test_route_avoids_a_road_that_floods_before_the_unit_arrives():
    a, b = GRAPH_NODES["ITO"], GRAPH_NODES["MAYUR"]
    base = po.road_route(a, b, _roads())
    rid = base["road_ids"][0]
    r = po.road_route(a, b, _roads(), closing={rid: 0.0})
    note = r.get("flood_forecast")
    assert note, "the forecast must be recorded on the route"
    if "avoided" in note:
        assert rid in note["avoided"] and rid not in r["road_ids"]
    else:
        assert rid in note["risk"]  # no alternative: kept, and said so
    # a closure far in the future changes nothing
    far = po.road_route(a, b, _roads(), closing={rid: 10_000.0})
    assert far["road_ids"] == base["road_ids"] and "flood_forecast" not in far
