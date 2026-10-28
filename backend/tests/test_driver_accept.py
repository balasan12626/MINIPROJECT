"""F3 — driver app Accept / Reject (person_ops.accept / reject / timeout + engine endpoints)."""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from backend.services import person_ops as po
from backend.services.seed import RESCUE_TEAMS
from backend.simulation.engine import SimulationEngine

T0 = datetime(2026, 9, 24, 10, 0, 0, tzinfo=timezone.utc)
TEAM = RESCUE_TEAMS[2]
MANUAL = {"teams": RESCUE_TEAMS, "accept_mode": "manual"}
AUTO = {"teams": RESCUE_TEAMS}


def _row(name="Priya Sharma", age=80, people=2):
    row = {
        "citizen_name": name,
        "age": age,  # elderly → needs an ambulance
        "water_level_note": "chest-deep",
        "people": people,
        "lat": 28.651,
        "lon": 77.262,
        "cluster_id": "C1",
        "assigned_team": TEAM["name"],
        "assigned_team_name": TEAM["name"],
    }
    po.ensure_ops(row, 1, queue_position=1, at=T0)
    return row


def _assigned(ctx):
    row = _row()
    po.advance_all([row], ctx, now=T0 + timedelta(seconds=po.DISPATCH_SECONDS))
    assert row["ops_status"] == "assigned"
    return row


def test_manual_mode_holds_assigned_until_accept():
    row = _assigned(MANUAL)
    t_assigned = T0 + timedelta(seconds=po.DISPATCH_SECONDS)
    po.advance_all([row], MANUAL, now=t_assigned + timedelta(seconds=po.MOBILISE_SECONDS + 5))
    assert row["ops_status"] == "assigned", "manual mode must not auto-accept after roll-out"

    po.accept(row, MANUAL, at=t_assigned + timedelta(seconds=8))
    assert row["ops_status"] == "en_route"
    assert row["driver_accepted"] and row["accepted_at"]
    assert row["accepted_via"] == "driver app"
    assert row["timestamps"]["accepted"] == row["accepted_at"]
    assert any(j["event"] == "ACCEPTED" and "driver app" in j["detail"] for j in row["journey"])


def test_reject_offers_the_job_to_another_unit_and_excludes_the_first():
    row = _assigned(MANUAL)
    first = row["unit_name"]
    rec = po.reject(row, [row], MANUAL, at=T0 + timedelta(seconds=5), reason="vehicle fault")
    assert row["ops_status"] == "assigned"
    assert row["unit_name"] != first and row["unit_name"] in po.AMBULANCE_POOL
    assert first in row["rejected_units"]
    assert rec["next_unit"] == row["unit_name"]
    assert row["timestamps"]["rejected"]
    assert any(j["event"] == "REJECTED" and "vehicle fault" in j["detail"] for j in row["journey"])
    # the rejected ambulance is free again on the fleet board
    fleet = {a["name"]: a for a in po.fleet_board([row])["ambulances"]}
    assert fleet[first]["status"] == "free"


def test_no_answer_times_out_and_reassigns():
    row = _assigned(MANUAL)
    first = row["unit_name"]
    t_assigned = T0 + timedelta(seconds=po.DISPATCH_SECONDS)
    po.advance_all([row], MANUAL, now=t_assigned + timedelta(seconds=po.ACCEPT_TIMEOUT_SECONDS + 0.1))
    assert first in row["rejected_units"]
    assert row["rejections"][0]["reason"] == po.NO_ANSWER
    assert row["ops_status"] == "assigned" and row["unit_name"] != first


def test_every_ambulance_rejecting_holds_the_job_in_the_queue():
    row = _row()
    row["rejected_units"] = list(po.AMBULANCE_POOL)
    po.advance_all([row], MANUAL, now=T0 + timedelta(seconds=po.DISPATCH_SECONDS))
    assert row["ops_status"] == "queued"
    assert "rejected" in row["ops_wait_reason"]


def test_rescue_team_reject_falls_back_to_another_depot():
    row = _row(age=30)
    row["water_level_note"] = "ankle-deep"
    row["needs_ambulance"] = False  # standard adult, shallow water → rescue team
    po.advance_all([row], MANUAL, now=T0 + timedelta(seconds=po.DISPATCH_SECONDS))
    assert row["unit_role"] == "rescue" and row["unit_name"] == TEAM["name"]
    po.reject(row, [row], MANUAL, at=T0 + timedelta(seconds=5))
    assert row["ops_status"] == "assigned"
    assert row["unit_name"] != TEAM["name"]
    assert row["unit_base_name"] == row["unit_name"]


def test_accept_on_a_moved_job_raises():
    row = _assigned(MANUAL)
    po.accept(row, MANUAL)
    with pytest.raises(ValueError):
        po.accept(row, MANUAL)
    with pytest.raises(ValueError):
        po.reject(row, [row], MANUAL)


def test_auto_mode_unchanged():
    row = _assigned(AUTO)
    po.advance_all([row], AUTO, now=T0 + timedelta(seconds=po.DISPATCH_SECONDS + po.MOBILISE_SECONDS))
    assert row["ops_status"] == "en_route"
    assert row["accepted_via"] == "auto"
    assert "rejected_units" not in row


def test_unit_view_shows_request_with_countdown():
    row = _assigned(MANUAL)
    now = T0 + timedelta(seconds=po.DISPATCH_SECONDS + 5)
    view = po.unit_view([row], row["unit_name"], "manual", now=now)
    assert view["status"] == "request"
    assert view["job"]["citizen_name"] == "Priya Sharma"
    assert view["job"]["seconds_left"] == pytest.approx(po.ACCEPT_TIMEOUT_SECONDS - 5)
    assert view["job"]["route_to_person"]["points"]
    other = next(a for a in po.AMBULANCE_POOL if a != row["unit_name"])
    assert po.unit_view([row], other, "manual", now=now)["status"] == "free"


def test_engine_driver_answer_and_double_tap_409():
    eng = SimulationEngine()
    eng.accept_mode = "manual"
    eng._teams_cache = list(RESCUE_TEAMS)
    row = _row()
    row["ops_stage_at"] = po._iso(po._now() - timedelta(seconds=po.DISPATCH_SECONDS + 0.1))
    eng.contact_log = [row]
    unit_view = eng.unit_view(next(iter(po.AMBULANCE_POOL)))
    assert unit_view is not None
    unit = row["unit_name"]
    assert row["ops_status"] == "assigned"

    st = asyncio.run(eng.driver_answer(unit, True))
    assert row["ops_status"] == "en_route"
    assert st["accept_mode"] == "manual"
    with pytest.raises(LookupError):
        asyncio.run(eng.driver_answer(unit, True))
    assert eng.unit_view("Not A Unit") is None


def test_mas_reports_reject_and_repeated_no_answer_red():
    from backend.agents.mas import MultiAgentSystem

    row = _assigned(MANUAL)
    t = T0 + timedelta(seconds=po.DISPATCH_SECONDS)
    po.advance_all([row], MANUAL, now=t + timedelta(seconds=po.ACCEPT_TIMEOUT_SECONDS + 0.1))
    po.advance_all([row], MANUAL, now=t + timedelta(seconds=2 * po.ACCEPT_TIMEOUT_SECONDS + 0.2))
    assert len(row["rejections"]) == 2
    mas = MultiAgentSystem()
    mas._on_person(row)
    titles = [m["title"] for m in mas.messages]
    assert titles.count("No answer → reassigned") == 2
    assert any(m["severity"] == "red" for m in mas.messages if m["title"] == "No answer → reassigned")
