"""F30 — duplicate SOS: suggested only, operator merges, history kept, unit freed."""
from datetime import datetime, timedelta, timezone

import pytest

from backend.services import person_ops as po
from backend.services.seed import RESCUE_TEAMS

T0 = datetime(2026, 9, 24, 10, 0, 0, tzinfo=timezone.utc)
TEAM = RESCUE_TEAMS[2]
CTX = {"teams": RESCUE_TEAMS}


def _row(name, lat=28.651, lon=77.262, at=T0, age=80, people=2, **kw):
    row = {"citizen_name": name, "age": age, "water_level_note": "chest-deep", "people": people, "lat": lat, "lon": lon,
           "cluster_id": "C1", "assigned_team": TEAM["name"], "assigned_team_name": TEAM["name"], **kw}
    po.ensure_ops(row, 1, queue_position=1, at=at)
    return row


def test_name_similarity():
    assert po.name_similarity("Priya Sharma", "priya  sharma!") == 1.0
    assert po.name_similarity("Priya Sharma", "Priya Sharmaa") >= 0.9
    assert po.name_similarity("Priya Sharma", "Rahul Verma") < 0.6


def test_thresholds_on_fixed_rows():
    near = 50 / 110_574.0  # 50 m north
    far = 120 / 110_574.0
    a = _row("Priya Sharma")
    b = _row("Priya Sharmaa", lat=28.651 + near, at=T0 + timedelta(seconds=5))  # 10 sim min later
    c = _row("Priya Sharma", lat=28.651 + far)  # too far
    d = _row("Rahul Verma", lat=28.651 + near / 2)  # near, different name
    e = _row("Priya Sharma", at=T0 + timedelta(seconds=15))  # 30 sim min later — outside the window
    f = _row("Someone Else", lat=28.651 + near, device_key="abc")
    g = _row("Another Name", device_key="abc")  # same phone
    pairs = {(x["a"], x["b"]) for x in po.duplicate_candidates([a, b, c, d, e, f, g])}
    assert ("Priya Sharma", "Priya Sharmaa") in pairs
    assert ("Someone Else", "Another Name") in pairs
    assert not any("Rahul Verma" in p for p in pairs)
    top = po.duplicate_candidates([a, b])[0]
    assert top["distance_m"] == pytest.approx(50, abs=1) and top["minutes_apart"] == 10.0
    assert "names" in " ".join(top["reasons"])


def test_merge_frees_the_unit_and_keeps_history():
    a = _row("Priya Sharma", people=2)
    b = _row("Priya Sharmaa", people=3)
    rows = [a, b]
    po.advance_all(rows, CTX, now=T0 + timedelta(seconds=po.DISPATCH_SECONDS + 0.5))
    assert b["ops_status"] == "assigned"
    unit = b["unit_name"]
    rec = po.merge_rows(rows, "Priya Sharma", "Priya Sharmaa", at=T0 + timedelta(seconds=4))
    assert rec["freed_unit"] == unit
    assert b["ops_status"] == "merged" and b["merged_into"] == "Priya Sharma"
    assert any(j["event"] == "MERGED" for j in b["journey"]) and len(b["journey"]) >= 3, "history kept"
    assert a["people"] == 3 and a["merged_from"] == ["Priya Sharmaa"]
    assert unit not in po._busy_ambulances(rows)
    po.advance_all(rows, CTX, now=T0 + timedelta(minutes=30))
    assert b["ops_status"] == "merged", "a merged row never re-enters the stage machine"
    assert po.duplicate_candidates(rows) == []
    with pytest.raises(ValueError):
        po.merge_rows(rows, "Priya Sharma", "Priya Sharmaa")
    with pytest.raises(KeyError):
        po.merge_rows(rows, "Priya Sharma", "Nobody")


@pytest.mark.asyncio
async def test_not_a_duplicate_stops_reflagging_and_merge_endpoint():
    from httpx import ASGITransport, AsyncClient

    from backend.api import simulation as api
    from backend.main import app
    from backend.simulation.engine import SimulationEngine

    eng = SimulationEngine()
    eng.status, eng.run_id = "running", "SIM-DUP"
    eng._teams_cache = list(RESCUE_TEAMS)
    now = datetime.now(timezone.utc)
    eng.contact_log = [_row("Asha Devi", at=now), _row("Asha Devi.", at=now), _row("Ravi Kumar", lat=28.70, at=now),
                       _row("Ravi Kumarr", lat=28.70, at=now)]
    import backend.api.simulation as sim_api

    orig = sim_api.engine
    sim_api.engine = eng
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            st = (await c.get("/api/simulation/state")).json()
            assert len(st["duplicate_candidates"]) == 2
            st = (await c.post("/api/simulation/sos/not-duplicate", json={"a": "Ravi Kumar", "b": "Ravi Kumarr"})).json()
            assert [d["a"] for d in st["duplicate_candidates"]] == ["Asha Devi"]
            r = await c.post("/api/simulation/sos/merge", json={"keep": "Asha Devi", "drop": "Asha Devi."})
            assert r.status_code == 200 and r.json()["merge"]["drop"] == "Asha Devi."
            assert r.json()["duplicate_candidates"] == []
            assert (await c.post("/api/simulation/sos/merge", json={"keep": "Asha Devi", "drop": "Nobody"})).status_code == 404
            assert (await c.post("/api/simulation/sos/merge", json={"keep": "Asha Devi", "drop": "Asha Devi."})).status_code == 409
    finally:
        sim_api.engine = orig
    assert api is sim_api
