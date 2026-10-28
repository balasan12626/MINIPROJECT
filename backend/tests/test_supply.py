"""F28 — supply runs: Sphere-rate need, shared router (never over a closed road), off by default."""
from datetime import datetime, timedelta, timezone

from backend.services import person_ops as po
from backend.services import supply as sp
from backend.services.seed import RESCUE_TEAMS, ROADS

T0 = datetime(2026, 9, 24, 10, 0, 0, tzinfo=timezone.utc)
CFG = {"trucks": 1, "load_person_days": 100.0, "initial_stock_days": 0.0, "reorder_hours": 24.0}


def _rescued(name, shelter, people):
    return {"citizen_name": name, "ops_status": "rescued", "shelter_name": shelter, "people": people,
            "destination_kind": "shelter"}


def _ops():
    reg = po.shelter_registry()
    return sp.SupplyOps(CFG, list(RESCUE_TEAMS), reg, T0), reg


def test_off_by_default():
    assert sp.settings({}) is None and sp.settings({"supply": {"on": False}}) is None
    assert sp.settings({"supply": {"on": True}})["trucks"] == sp.DEFAULTS["trucks"]


def test_need_scales_with_delivered_people_at_sphere_rates():
    ops, reg = _ops()
    name = po.SHELTER_POOL[0]
    b1 = ops.board([_rescued("A", name, 4)], T0)["shelters"][0]
    b2 = ops.board([_rescued("A", name, 4), _rescued("B", name, 6)], T0)["shelters"][0]
    assert b1["need_water_l_per_day"] == 4 * 15.0 and b2["need_water_l_per_day"] == 10 * 15.0
    assert b2["need_food_kcal_per_day"] == 10 * 2100
    assert "Sphere" in ops.board([], T0)["rates_source"]


def test_truck_goes_to_the_emptiest_shelter_on_open_roads_and_delivers():
    ops, reg = _ops()
    name = po.SHELTER_POOL[0]
    rows = [_rescued("A", name, 5)]
    dispatched = 0
    for road in ROADS:  # close each road in turn: any dispatch must avoid it
        probe, _ = _ops()
        closed = {road["road_id"]}
        roads = [{**r, "blocked": r["road_id"] in closed, "accessible": r["road_id"] not in closed} for r in ROADS]
        if probe.step(rows, reg, roads, T0):
            dispatched += 1
            assert not set(probe.trucks[0]["leg"]["road_ids"]) & closed, "never routed over a closed road"
    assert dispatched > 0
    roads = [dict(r, blocked=False, accessible=True) for r in ROADS]
    ev = ops.step(rows, reg, roads, T0)
    t = ops.trucks[0]
    assert ev and ev[0]["dispatched_to"] == name and t["leg"]["to"] == name
    later = T0 + timedelta(seconds=t["leg"]["seconds"] + 1)
    ops.step(rows, reg, roads, later)
    assert ops.delivered_pd[name] == 100.0 and t["leg"] is None and t["trips"] == 1


def test_reroute_when_a_road_on_the_route_closes():
    ops, reg = _ops()
    name = po.SHELTER_POOL[0]
    roads = [dict(r, blocked=False, accessible=True) for r in ROADS]
    ops.step([_rescued("A", name, 5)], reg, roads, T0)
    used = ops.trucks[0]["leg"]["road_ids"]
    if not used:
        return  # trivial leg on one junction: nothing to close
    roads2 = [{**r, "blocked": r["road_id"] == used[0], "accessible": r["road_id"] != used[0]} for r in ROADS]
    out = ops.reroute(roads2, reg, T0 + timedelta(seconds=1))
    assert out and out[0]["truck"] == "Supply Truck 1"
    leg = ops.trucks[0]["leg"]
    assert leg is None or used[0] not in leg["road_ids"]
