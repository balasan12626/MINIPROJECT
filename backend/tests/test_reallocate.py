"""F2 — close / shrink a shelter → live reallocation (person_ops.reallocate + engine.set_shelter)."""
import asyncio
from datetime import timedelta

from backend.services import person_ops as po
from backend.services.seed import GRAPH_NODES, ROADS
from backend.simulation.engine import SimulationEngine
from backend.utils.geo import haversine_km

ITO = GRAPH_NODES["ITO"]
DU = "Delhi University Sports Complex"
CHHATRASAL = "Chhatrasal Stadium"


def _roads(blocked=()):
    out = [dict(r) for r in ROADS]
    for r in out:
        r["blocked"] = r["road_id"] in blocked
        r["accessible"] = not r["blocked"]
    return out


def _row(name, stage, shelter_name, now, person=(28.68, 77.21), frac=0.5, people=2, assigned_at=None):
    s = po.shelter_registry()[shelter_name]
    to_person = po.road_route(ITO, person, _roads())
    to_shelter = po.road_route(person, (s["lat"], s["lon"]), _roads())
    leg = to_shelter if stage == "to_shelter" else to_person
    secs = po.leg_seconds(leg["sim_minutes"])
    return {
        "citizen_name": name,
        "lat": person[0],
        "lon": person[1],
        "people": people,
        "person_index": int(name[-1]) if name[-1].isdigit() else 1,
        "ops_status": stage,
        "ops_stage_at": po._iso(now - timedelta(seconds=secs * frac)),
        "ops_stage_seconds": secs,
        "unit_name": "Ambulance Unit 1",
        "unit_role": "ambulance",
        "unit_base": [ITO[0], ITO[1]],
        "shelter_name": shelter_name,
        "shelter_lat": s["lat"],
        "shelter_lon": s["lon"],
        "route_to_person": to_person,
        "route_to_shelter": to_shelter,
        "timestamps": {"assigned": po._iso(assigned_at or now)},
        "journey": [],
    }


def test_closing_a_shelter_moves_active_rows_and_never_rescued_ones():
    now = po._now()
    a = _row("A1", "assigned", DU, now)
    b = _row("B2", "en_route", DU, now)
    done = _row("C3", "en_route", DU, now)
    done["ops_status"] = "rescued"
    ov = {DU: {"closed": True}}

    changes = po.reallocate([a, b, done], ov, _roads(), "DU closed", now=now)

    assert {c["citizen_name"] for c in changes} == {"A1", "B2"}
    expected = po._pick_shelter(a, [a, b, done], ov)["name"]
    for r in (a, b):
        assert r["shelter_name"] not in (DU, None)
        assert any(j["event"] == "SHELTER_CHANGED" for j in r["journey"])
        assert r["shelter_changes"][-1]["old_shelter"] == DU
        s = po.shelter_registry()[r["shelter_name"]]
        assert r["route_to_shelter"]["points"][-1] == [round(s["lat"], 6), round(s["lon"], 6)]
    assert a["shelter_name"] == expected
    assert done["shelter_name"] == DU and "shelter_changes" not in done


def test_group_on_board_continues_from_current_position():
    now = po._now()
    row = _row("D1", "to_shelter", DU, now, frac=0.4)
    pos = po.position_on(row["route_to_shelter"]["points"], po.leg_progress(row, now))

    po.reallocate([row], {DU: {"closed": True}}, _roads(), "DU closed", now=now)

    start = row["route_to_shelter"]["points"][0]
    assert haversine_km(start[0], start[1], pos[0], pos[1]) < 0.01
    assert row["ops_stage_at"] == po._iso(now)
    assert row["ops_stage_seconds"] == po.leg_seconds(row["route_to_shelter"]["sim_minutes"])
    assert row["eta_to_shelter_min"] == row["route_to_shelter"]["sim_minutes"]


def test_capacity_cut_releases_the_newest_allocations_first():
    now = po._now()
    old = _row("E1", "assigned", DU, now, assigned_at=now - timedelta(seconds=30))
    new = _row("F2", "assigned", DU, now, assigned_at=now)
    occ = po.shelter_registry()[DU]["occupancy"]
    ov = {DU: {"capacity": occ + 2}}  # room for exactly one 2-person group

    changes = po.reallocate([old, new], ov, _roads(), "DU shrunk", now=now)

    assert [c["citizen_name"] for c in changes] == ["F2"]
    assert old["shelter_name"] == DU
    assert new["shelter_name"] != DU


def test_every_shelter_closed_flags_wait_and_holds_delivery():
    now = po._now()
    row = _row("G1", "to_shelter", DU, now, frac=0.2)
    ov = {n: {"closed": True} for n in po.SHELTER_POOL}

    changes = po.reallocate([row], ov, _roads(), "all closed", now=now)

    assert changes and changes[0]["no_seats"]
    assert row["shelter_wait"] and row["ops_wait_reason"] == po.NO_SEATS_REASON
    assert any(j["event"] == "SHELTER_WAIT" for j in row["journey"])
    # the unit keeps the group: no delivery even long after the leg ended
    po.advance_all([row], {"shelter_overrides": ov}, now=now + timedelta(hours=2))
    assert row["ops_status"] == "to_shelter"
    # repeated pass does not repeat the journey entry
    po.reallocate([row], ov, _roads(), "all closed", now=now)
    assert sum(j["event"] == "SHELTER_WAIT" for j in row["journey"]) == 1

    # reopen one shelter → the waiting group moves there
    ov.pop(CHHATRASAL)
    moved = po.reallocate([row], ov, _roads(), "Chhatrasal reopened", now=now)
    assert moved and row["shelter_name"] == CHHATRASAL
    assert "shelter_wait" not in row and "ops_wait_reason" not in row


def test_unreachable_shelter_moves_only_when_another_is_reachable():
    now = po._now()
    row = _row("H1", "assigned", DU, now)
    row["route_alert"] = {"leg": "route_to_shelter", "roads": ["R01"], "reason": "test"}
    every = {r["road_id"] for r in ROADS}
    # nothing reachable: keep the plan
    assert po.reallocate([row], {}, _roads(every), "all roads closed", now=now) == []
    assert row["shelter_name"] == DU
    # roads open: moved to another shelter, alert cleared
    changes = po.reallocate([row], {}, _roads(), "roads open", now=now)
    assert changes and row["shelter_name"] != DU and "route_alert" not in row


def test_board_shows_closed_shelter_with_no_free_seats():
    row = _row("I1", "rescued", DU, po._now())
    board = {s["name"]: s for s in po.shelter_allocation_board([row], {DU: {"closed": True}})}
    assert board[DU]["closed"] is True and board[DU]["seats_left"] == 0
    assert board[DU]["delivered_this_run"] == 2  # delivered before closure stays counted
    assert board[CHHATRASAL]["closed"] is False


def test_closed_shelter_is_never_picked_at_allocation():
    row = {"lat": 28.6886, "lon": 77.2095, "people": 1}  # standing at DU
    assert po._pick_shelter(row, [row])["name"] == DU
    assert po._pick_shelter(row, [row], {DU: {"closed": True}})["name"] != DU


def test_engine_set_shelter_close_reopen_and_reset():
    eng = SimulationEngine()
    now = po._now()
    eng.contact_log = [_row("J1", "assigned", DU, now)]

    st = asyncio.run(eng.set_shelter(DU, closed=True))
    assert eng.contact_log[0]["shelter_name"] != DU
    board = {s["name"]: s for s in st["shelter_allocation"]}
    assert board[DU]["closed"] and board[DU]["moved_away"] == 1
    assert any(m["title"].startswith("Shelter closed") for m in st["multi_agent"]["messages"])

    base = po.shelter_registry()[DU]["base_capacity"]
    asyncio.run(eng.set_shelter(DU, capacity=10))
    asyncio.run(eng.set_shelter(DU, clear=True))
    reg = po.shelter_registry(eng.shelter_overrides)[DU]
    assert reg["capacity"] == base and not reg["closed"]
    assert len(eng.shelter_log) == 3


def test_mas_shelter_playbook_exists():
    from backend.agents.mas import DEFAULT_PLAYBOOK

    assert "SHELTER_CLOSED" in DEFAULT_PLAYBOOK["actions"]
