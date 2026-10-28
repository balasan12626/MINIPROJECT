"""F1 — block a road → live reroute (person_ops.reroute + engine road state)."""
from datetime import timedelta

from backend.services import person_ops as po
from backend.services.seed import GRAPH_NODES, ROADS
from backend.simulation.engine import SimulationEngine
from backend.utils.geo import haversine_km

ITO = GRAPH_NODES["ITO"]
MAYUR = GRAPH_NODES["MAYUR"]
AZADPUR = GRAPH_NODES["AZADPUR"]
DU = GRAPH_NODES["DU"]


def _roads(blocked=()):
    out = [dict(r) for r in ROADS]
    for r in out:
        r["blocked"] = r["road_id"] in blocked
        r["accessible"] = not r["blocked"]
    return out


def _row(name, stage, start, person, shelter, now, frac=0.5):
    to_person = po.road_route(start, person, _roads())
    to_shelter = po.road_route(person, shelter, _roads())
    leg = to_shelter if stage == "to_shelter" else to_person
    secs = po.leg_seconds(leg["sim_minutes"])
    return {
        "citizen_name": name,
        "lat": person[0],
        "lon": person[1],
        "people": 2,
        "ops_status": stage,
        "ops_stage_at": po._iso(now - timedelta(seconds=secs * frac)),
        "ops_stage_seconds": secs,
        "unit_name": "Ambulance Unit 1",
        "unit_role": "ambulance",
        "unit_base": [start[0], start[1]],
        "shelter_name": "Test shelter",
        "shelter_lat": shelter[0],
        "shelter_lon": shelter[1],
        "route_to_person": to_person,
        "route_to_shelter": to_shelter,
        "journey": [],
    }


def test_position_on_is_linear_along_length():
    pts = [[0.0, 0.0], [0.0, 1.0], [0.0, 3.0]]
    mid = po.position_on(pts, 0.5)
    assert abs(mid[0]) < 1e-9 and abs(mid[1] - 1.5) < 1e-6
    assert po.position_on(pts, 0) == pts[0]
    assert po.position_on(pts, 1) == pts[-1]
    assert po.position_on([], 0.3) == []


def test_road_route_records_the_roads_it_uses():
    r = po.road_route(ITO, MAYUR, _roads())
    assert r["method"] != "direct"
    assert r["road_ids"], "graph routes must list their road ids"
    assert set(r["road_ids"]) <= {x["road_id"] for x in ROADS}


def test_blocked_road_reroutes_moving_unit_from_current_position():
    now = po._now()
    row = _row("A", "en_route", ITO, MAYUR, AZADPUR, now, frac=0.5)
    old = row["route_to_person"]
    cut = old["road_ids"][0]
    expected_pos = po.position_on(old["points"], po.leg_progress(row, now))

    changes = po.reroute([row], _roads({cut}), f"{cut} blocked", now=now)

    legs = {c["leg"] for c in changes}
    assert "route_to_person" in legs
    new = row["route_to_person"]
    assert cut not in new["road_ids"]
    # continues from where it is — not from the depot
    assert haversine_km(new["points"][0][0], new["points"][0][1], expected_pos[0], expected_pos[1]) < 0.01
    assert row["ops_stage_at"] == po._iso(now)
    assert row["ops_stage_seconds"] == po.leg_seconds(new["sim_minutes"])
    assert row["eta_min"] == new["sim_minutes"]
    assert any(j["event"] == "REROUTED" for j in row["journey"])
    assert row["reroutes"][-1]["blocked_roads"] == [cut]


def test_rows_not_using_the_road_and_finished_rows_are_untouched():
    now = po._now()
    far = _row("B", "en_route", AZADPUR, DU, AZADPUR, now)
    used = set(far["route_to_person"]["road_ids"]) | set(far["route_to_shelter"]["road_ids"])
    cut = next(r["road_id"] for r in ROADS if r["road_id"] not in used)
    done = _row("C", "en_route", ITO, MAYUR, ITO, now)
    done["ops_status"] = "rescued"
    before_far, before_done = dict(far["route_to_person"]), dict(done["route_to_person"])

    changes = po.reroute([far, done], _roads({cut}), "test", now=now)

    assert changes == []
    assert far["route_to_person"] == before_far
    assert done["route_to_person"] == before_done
    assert "reroutes" not in far and "reroutes" not in done


def test_assigned_row_replans_both_legs_from_its_base():
    now = po._now()
    row = _row("D", "assigned", ITO, MAYUR, ITO, now)
    stage_at = row["ops_stage_at"]
    cut = row["route_to_person"]["road_ids"][0]
    po.reroute([row], _roads({cut}), "test", now=now)
    assert cut not in row["route_to_person"]["road_ids"]
    assert row["ops_stage_at"] == stage_at  # roll-out timer is not restarted
    assert abs(row["route_to_person"]["points"][0][0] - ITO[0]) < 1e-6


def test_reopen_only_switches_when_faster():
    now = po._now()
    row = _row("E", "en_route", ITO, MAYUR, ITO, now, frac=0.0)
    cut = row["route_to_person"]["road_ids"][0]
    po.reroute([row], _roads({cut}), "block", now=now)
    detour = row["route_to_person"]["sim_minutes"]
    changes = po.reroute([row], _roads(), "reopen", now=now, improve=True)
    for c in changes:
        assert c["new_minutes"] < c["old_minutes_left"] - po.REROUTE_GAIN_MIN + 1e-9
    if changes:
        assert row["route_to_person"]["sim_minutes"] < detour


def test_engine_override_beats_flood_rule_and_clear_hands_back():
    eng = SimulationEngine()
    eng.auto_blocked = {"R02"}
    assert next(r for r in eng.roads_now() if r["road_id"] == "R02")["blocked"]
    eng.road_overrides["R02"] = False
    r02 = next(r for r in eng.roads_now() if r["road_id"] == "R02")
    assert not r02["blocked"] and r02["source"] == "operator"
    eng.road_overrides.pop("R02")
    assert next(r for r in eng.roads_now() if r["road_id"] == "R02")["blocked"]
    status = {r["road_id"]: r for r in eng.road_status()}
    assert "segments" not in status["R02"], "road shapes are static: served by /api/cities/{id}, not every poll"
    from backend.geo.cities import LEGACY, view

    geo = view(LEGACY)["road_geometry"]
    assert all(geo.get(r["road_id"]) for r in ROADS), "map needs a shape for every road"


def test_seed_roads_are_never_mutated():
    eng = SimulationEngine()
    eng.road_overrides = {r["road_id"]: True for r in ROADS}
    eng.roads_now()
    assert not any(r["blocked"] for r in ROADS)


def test_mas_announces_road_block_and_playbook():
    from backend.agents.mas import MultiAgentSystem

    mas = MultiAgentSystem()
    change = {"citizen_name": "A", "unit_name": "Ambulance Unit 1", "leg": "route_to_person", "new_km": 3.2,
              "new_minutes": 9.0, "delta_minutes": 2.5, "from_current_position": True, "blocked_roads": ["R02"]}
    mas.announce_road("RUN", "R02", "NH-9 Geeta Colony", True, "operator", [change])
    kinds = [m["kind"] for m in mas.messages]
    assert "road" in kinds and "playbook" in kinds
    head = next(m for m in mas.messages if m["kind"] == "road")
    assert head["severity"] == "yellow" and "R02" in head["title"]
    assert any(m["title"] == "Rerouted" for m in mas.messages)
    n = len(mas.messages)
    mas.announce_road("RUN", "R02", "NH-9 Geeta Colony", False, "operator", [])
    assert len(mas.messages) == n + 1 and mas.messages[-1]["severity"] == "green"


def test_no_open_road_keeps_plan_and_alerts_then_reopen_replans():
    now = po._now()
    row = _row("F", "en_route", ITO, MAYUR, ITO, now, frac=0.3)
    old = dict(row["route_to_person"])
    every = {r["road_id"] for r in ROADS}
    changes = po.reroute([row], _roads(every), "all closed", now=now)
    assert changes and all(c.get("no_open_road") for c in changes)
    # never swap in a straight line that looks faster than the road
    assert row["route_to_person"] == old
    assert row["route_alert"]["leg"] in ("route_to_person", "route_to_shelter")
    assert any(j["event"] == "NO_OPEN_ROAD" for j in row["journey"])
    # same closure again: no duplicate alert
    assert po.reroute([row], _roads(every), "all closed", now=now) == []

    po.reroute([row], _roads(), "reopened", now=now, improve=True)
    assert "route_alert" not in row
    assert row["route_to_person"]["method"] != "direct"
