"""F25 — crew shifts and fuel: derived from the unit's own legs, assumed rules, default off."""
import random
from datetime import datetime, timedelta, timezone

from backend.services import ops_sim
from backend.services import person_ops as po
from backend.services.seed import RESCUE_TEAMS

T0 = datetime(2026, 9, 24, 10, 0, 0, tzinfo=timezone.utc)
TEAM = RESCUE_TEAMS[2]
RULES = {"on": True, "shift_max_min": 60.0, "rest_min": 120.0, "range_km": 1000.0, "refuel_min": 20.0}


def _done(unit, at, minutes, km=5.0):
    """A completed job of `unit` dropped off at `at` with `minutes` of driving."""
    return {"citizen_name": f"done {at.isoformat()}", "ambulance_name": unit, "unit_name": unit, "ops_status": "rescued",
            "timestamps": {"rescued": at.isoformat()},
            "route_to_person": {"sim_minutes": minutes / 2, "km": km / 2},
            "route_to_shelter": {"sim_minutes": minutes / 2, "km": km / 2}}


def _queued(name="Caller", age=80):
    row = {"citizen_name": name, "age": age, "water_level_note": "chest-deep", "people": 1, "lat": 28.651, "lon": 77.262,
           "cluster_id": "C1", "assigned_team": TEAM["name"], "assigned_team_name": TEAM["name"]}
    po.ensure_ops(row, 1, queue_position=1, at=T0)
    return row


def test_rules_off_is_todays_behaviour():
    rows = [_done(po.AMBULANCE_POOL[0], T0, 500)]
    assert po.crew_state(po.AMBULANCE_POOL[0], rows, None, T0) == {"state": "ok"}
    assert po.unavailable_units(rows, {}, T0) == {}


def test_unit_rests_after_the_shift_and_comes_back():
    u = po.AMBULANCE_POOL[0]
    rows = [_done(u, T0, 40), _done(u, T0 + timedelta(seconds=30), 30)]  # 70 min ≥ 60 → rest 120 sim min = 60 wall s
    rules = po.crew_rules({"crew_rules": RULES})
    s = po.crew_state(u, rows, rules, T0 + timedelta(seconds=40))
    assert s["state"] == "resting" and s["left_min"] == 100.0
    assert po.crew_state(u, rows, rules, T0 + timedelta(seconds=91))["state"] == "ok"


def test_refuel_after_the_range():
    u = po.AMBULANCE_POOL[1]
    rows = [_done(u, T0, 10, km=1200)]
    s = po.crew_state(u, rows, po.crew_rules({"crew_rules": RULES}), T0 + timedelta(seconds=5))
    assert s["state"] == "refuelling" and s["left_min"] == 10.0


def test_resting_unit_is_never_dispatched(monkeypatch):
    monkeypatch.setattr(po, "AMBULANCE_POOL", ["Ambulance Unit 1"])
    u = "Ambulance Unit 1"
    rows = [_done(u, T0 - timedelta(seconds=10), 90)]
    q = _queued()
    rows.append(q)
    ctx = {"teams": RESCUE_TEAMS, "crew_rules": RULES}
    po.advance_all(rows, ctx, now=T0 + timedelta(seconds=po.DISPATCH_SECONDS + 1))
    assert q["ops_status"] == "queued" and "off duty" in q["ops_wait_reason"]
    pos = po.ambulance_positions(rows, ctx, T0 + timedelta(seconds=5))
    assert pos[u]["status"] == "resting"
    # rest ends 120 sim min = 60 wall s after the drop-off: assigned AT that moment, not before
    po.advance_all(rows, ctx, now=T0 + timedelta(seconds=200))
    assert q["ops_status"] != "queued"
    assigned = po._parse(q["timestamps"]["assigned"])
    assert assigned >= T0 + timedelta(seconds=50)
    fleet = po.fleet_board(rows[:1], ctx)
    assert fleet["crew_rules"]["shift_max_min"] == 60.0 and "assumed" in fleet["crew_rules_source"]


def test_long_instance_and_rules_on_off_play_the_same_people():
    inst = ops_sim.make_long_instance(random.Random(2), hours=6, per_hour=4)
    assert inst["callers"] and all(c["arrive_s"] > 0 for c in inst["callers"])
    pol = ops_sim.POLICIES["first_free"]
    off = ops_sim.play(inst, pol, horizon_s=600)
    on = ops_sim.play(inst, pol, crew={"on": True, **po.CREW_DEFAULTS}, horizon_s=600)
    assert len(off["people"]) == len(on["people"]) == len(inst["callers"])
