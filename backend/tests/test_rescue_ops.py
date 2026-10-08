"""Rescue stage machine (person_ops), SOS endpoint, child definition, arena ETAs."""

from datetime import datetime, timedelta, timezone

import pytest

from backend.schemas.common import CitizenSosRequest
from backend.services import person_ops
from backend.services.demo_extras import medical_triage
from backend.services.person_ops import (
    AMBULANCE_POOL,
    DISPATCH_SECONDS,
    MOBILISE_SECONDS,
    advance_all,
    ensure_ops,
    leg_seconds,
    shelter_registry,
)
from backend.services.priority import needs_ambulance, vulnerability_label
from backend.services.seed import RESCUE_TEAMS

T0 = datetime(2026, 9, 24, 10, 0, 0, tzinfo=timezone.utc)
TEAM = RESCUE_TEAMS[2]  # Delhi Police Disaster Cell ITO


def _row(name="Priya Sharma", age=29, water="knee-deep", people=3, lat=28.651, lon=77.262, at=T0):
    row = {
        "citizen_name": name,
        "age": age,
        "water_level_note": water,
        "people": people,
        "lat": lat,
        "lon": lon,
        "cluster_id": "C1",
        "assigned_team": TEAM["name"],
        "assigned_team_name": TEAM["name"],
    }
    ensure_ops(row, 1, queue_position=1, at=at)
    return row


def _parse(ts):
    return datetime.fromisoformat(ts)


def test_every_pool_shelter_resolves_to_coordinates():
    reg = shelter_registry()
    for name in person_ops.SHELTER_POOL:
        assert name in reg, name


def test_stage_timing_follows_route_travel_time():
    row = _row()
    ctx = {"teams": RESCUE_TEAMS}
    # Nothing due before the dispatch slot.
    assert advance_all([row], ctx, now=T0 + timedelta(seconds=DISPATCH_SECONDS - 0.5)) == 0
    assert row["ops_status"] == "queued"

    advance_all([row], ctx, now=T0 + timedelta(seconds=DISPATCH_SECONDS))
    assert row["ops_status"] == "assigned"
    leg1 = row["route_to_person"]
    assert leg1["km"] > 0 and leg1["sim_minutes"] > 0
    assert row["eta_min"] == leg1["sim_minutes"]

    advance_all([row], ctx, now=T0 + timedelta(seconds=DISPATCH_SECONDS + MOBILISE_SECONDS))
    assert row["ops_status"] == "en_route"
    assert row["ops_stage_seconds"] == pytest.approx(leg_seconds(leg1["sim_minutes"]))
    # en_route length is the route's travel time, NOT a fixed 12 s step
    assert row["ops_stage_seconds"] != 12.0

    # Catch-up after a long polling gap: timestamps are stamped when DUE.
    advance_all([row], ctx, now=T0 + timedelta(hours=3))
    assert row["ops_status"] == "rescued"
    ts = row["timestamps"]
    en_route_at = _parse(ts["en_route"])
    to_shelter_at = _parse(ts["to_shelter"])
    assert (to_shelter_at - en_route_at).total_seconds() == pytest.approx(leg_seconds(leg1["sim_minutes"]), abs=1e-3)
    order = [_parse(ts[s]) for s in ("queued", "assigned", "en_route", "to_shelter", "rescued")]
    assert order == sorted(order)


def test_route_is_a_real_polyline_from_base_to_person():
    row = _row()
    advance_all([row], {"teams": RESCUE_TEAMS}, now=T0 + timedelta(seconds=DISPATCH_SECONDS))
    pts = row["route_to_person"]["points"]
    assert pts[0] == [TEAM["lat"], TEAM["lon"]]
    assert pts[-1] == [row["lat"], row["lon"]]
    assert row["unit_base"] == [TEAM["lat"], TEAM["lon"]]


def test_ambulance_only_for_vulnerable_people():
    child = _row("Kabir Singh", age=8, water="ankle-deep")
    adult = _row("Vivek Nair", age=33, water="knee-deep")
    chest = _row("Arjun Das", age=47, water="chest-deep")
    rows = [child, adult, chest]
    advance_all(rows, {"teams": RESCUE_TEAMS}, now=T0 + timedelta(seconds=DISPATCH_SECONDS))
    assert child["unit_role"] == "ambulance" and child["ambulance_name"] in AMBULANCE_POOL
    assert chest["unit_role"] == "ambulance"
    assert adult["unit_role"] == "rescue"
    assert adult["ambulance_name"] is None
    assert adult["unit_name"] == TEAM["name"]


def test_ambulances_are_exclusive_and_queue_waits():
    rows = [_row(f"Child {i}", age=6) for i in range(len(AMBULANCE_POOL) + 1)]
    advance_all(rows, {"teams": RESCUE_TEAMS}, now=T0 + timedelta(seconds=DISPATCH_SECONDS))
    assigned = [r for r in rows if r["ops_status"] == "assigned"]
    assert len(assigned) == len(AMBULANCE_POOL)
    assert len({r["ambulance_name"] for r in assigned}) == len(AMBULANCE_POOL)
    waiting = [r for r in rows if r["ops_status"] == "queued"]
    assert len(waiting) == 1 and "ambulances busy" in waiting[0]["ops_wait_reason"]
    # Once someone is delivered, the waiting child gets the freed ambulance.
    advance_all(rows, {"teams": RESCUE_TEAMS}, now=T0 + timedelta(hours=6))
    assert all(r["ops_status"] == "rescued" for r in rows)


def test_one_child_definition_everywhere():
    from backend.services.algorithm_arena import evaluate_policies
    from backend.thresholds import CHILD_MAX_AGE

    below = {"citizen_name": "A", "age": CHILD_MAX_AGE - 1, "water_level_note": "ankle"}
    at_limit = {"citizen_name": "B", "age": CHILD_MAX_AGE, "water_level_note": "ankle"}
    assert vulnerability_label(below) == "child" and medical_triage(below) == "child"
    assert vulnerability_label(at_limit) != "child" and medical_triage(at_limit) != "child"
    assert needs_ambulance(below) and not needs_ambulance(at_limit)
    pol = evaluate_policies(dual={}, physics={"flood_probability": 0.5}, ml_p=0.5, citizens=[below, at_limit], shelters=[])
    assert pol["priority_citizens"] == ["A"]


def test_sos_schema_accepts_age():
    body = CitizenSosRequest(citizen_name="Test", age=7, people=3)
    assert body.model_dump()["age"] == 7


@pytest.mark.asyncio
async def test_add_sos_appends_without_wiping_progress(monkeypatch):
    import backend.agents.dialogue as dialogue
    from backend.simulation import engine as engine_mod

    async def _noop(*_a, **_k):
        return {}

    monkeypatch.setattr(engine_mod, "run_pipeline", _noop)
    monkeypatch.setattr(engine_mod.hub, "broadcast", _noop)
    monkeypatch.setattr(dialogue, "talk_with_citizen", _noop)
    monkeypatch.setattr(engine_mod, "_canonical_ml", lambda rain: ({}, {}))
    monkeypatch.setattr(engine_mod.SimulationEngine, "_evolve", lambda self: {})

    eng = engine_mod.SimulationEngine()
    eng.run_id = "SIM-TEST"
    eng._teams_cache = list(RESCUE_TEAMS)
    eng.clusters = {
        "clusters": [
            {"cluster_id": "C1", "lat": 28.63, "lon": 77.24, "sos_count": 1, "people": 3,
             "assigned_team": "RT-03", "assigned_team_name": TEAM["name"], "priority_queue": [], "members": []},
            {"cluster_id": "C2", "lat": 28.71, "lon": 77.11, "sos_count": 0, "people": 0,
             "assigned_team": "RT-04", "assigned_team_name": "SDRF North District", "priority_queue": [], "members": []},
        ]
    }
    started = datetime.now(timezone.utc) - timedelta(seconds=DISPATCH_SECONDS + MOBILISE_SECONDS + 0.5)
    progressed = _row("Priya Sharma", at=started)
    advance_all([progressed], {"teams": RESCUE_TEAMS})
    assert progressed["ops_status"] == "en_route"
    progressed["person_index"] = 1
    eng.contact_log = [progressed]
    eng.citizens = [dict(progressed)]

    st = await eng.add_citizen_sos(
        {"citizen_name": "Priya Sharma", "age": 7, "people": 2, "lat": 28.632, "lon": 77.245, "water_level_note": "knee-deep"}
    )
    names = [r["citizen_name"] for r in eng.contact_log]
    assert names == ["Priya Sharma", "Priya Sharma (2)"]  # appended, unique key
    assert eng.contact_log[0] is progressed
    assert eng.contact_log[0]["ops_status"] in {"en_route", "to_shelter", "rescued"}  # not wiped
    new = eng.contact_log[1]
    assert new["age"] == 7 and new["vulnerability"] == "child"
    assert new["ops_status"] == "queued"
    assert new["cluster_id"] == "C1" and new["assigned_team_name"] == TEAM["name"]
    assert st["added_citizen_name"] == "Priya Sharma (2)"
    card = st["pipeline"]["clusters"][0] if st.get("pipeline") else eng.clusters["clusters"][0]
    assert card["sos_count"] == 2


def test_route_travel_time_is_sane():
    from backend.services.route_engine import build_graph, path_payload
    from backend.services.seed import ROADS

    g = build_graph(ROADS)
    p = path_payload(g, ["ITO", "RAJGHAT", "GEETA"])
    # ~4 km of weighted road should be minutes, not hours (was 17 min/km).
    assert p["travel_time_min"] < 30


def test_arena_star_equals_referee_pick():
    from backend.services.algorithm_arena import run_algorithm_arena
    from backend.services.citizens import roster

    out = run_algorithm_arena({"pipeline": {}, "params": {}, "history": [], "citizens": roster(6)})
    winners = [r for r in out["scoreboard"] if r["winner"]]
    assert len(winners) == 1
    assert winners[0]["method"] == out["winner_method"]
    assert winners[0]["label"] in out["agent_verdict"]["rescue_agent"]
    for r in out["scoreboard"]:
        assert r["avg_eta_min"] < 240, r
