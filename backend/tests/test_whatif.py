"""F16 — what-if planner: copies the live run, never mutates it, replays on the one stage machine."""
import asyncio
import copy
import json
import random
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from backend.schemas.common import WhatIfRequest
from backend.services import ops_sim
from backend.services import person_ops as po
from backend.services.seed import RESCUE_TEAMS, ROADS
from backend.services.whatif import JobBusy, WhatIfJobs
from backend.simulation.engine import SCENARIOS, SimulationEngine


def _engine(n=6, age=80, policy="first_free"):
    """A live-like engine: `n` SOS rows queued just now, nothing awaited."""
    eng = SimulationEngine()
    eng.status = "running"
    eng.run_id = "SIM-TEST"
    eng.params = {**SCENARIOS["heavy_rainfall"]["defaults"], "dispatch_policy": policy, "tick_seconds": 2.0}
    eng._teams_cache = list(RESCUE_TEAMS)
    now = datetime.now(timezone.utc)
    for i in range(n):
        team = RESCUE_TEAMS[i % len(RESCUE_TEAMS)]
        row = {"citizen_name": f"Person {i}", "age": age, "water_level_note": "chest-deep", "people": 2,
               "lat": 28.62 + 0.004 * i, "lon": 77.22 + 0.003 * i, "cluster_id": team["team_id"],
               "assigned_team": team["name"], "assigned_team_name": team["name"]}
        po.ensure_ops(row, i + 1, queue_position=i + 1, at=now - timedelta(seconds=1))
        row["person_index"] = i + 1
        eng.contact_log.append(row)
    return eng


def _dump(x):
    return json.dumps(x, sort_keys=True, default=str)


def test_snapshot_and_play_never_touch_the_live_run():
    eng = _engine()
    snap = ops_sim.snapshot(eng)
    before = _dump(eng.contact_log), _dump(eng.shelter_overrides), _dump(eng.staging), set(eng.auto_blocked)
    for opt in ({"kind": "baseline"}, {"kind": "add_ambulances", "n": 3},
                {"kind": "close_shelter", "name": po.SHELTER_POOL[0]}, {"kind": "block_road", "road_id": ROADS[0]["road_id"]}):
        ops_sim.play_whatif(snap, opt, 30, random.Random(1))
    assert (_dump(eng.contact_log), _dump(eng.shelter_overrides), _dump(eng.staging), set(eng.auto_blocked)) == before
    assert eng.road_overrides == {}
    assert po.ambulance_pool() == po.AMBULANCE_POOL and po.route_chooser() == po.ROUTE_CHOOSER


def test_no_change_reproduces_the_live_plan_on_its_first_step():
    eng = _engine()
    snap = ops_sim.snapshot(eng)
    sim = ops_sim.play_whatif(snap, {"kind": "baseline"}, 0, random.Random(1), arrivals=False, keep_rows=True)["rows"]
    live = copy.deepcopy(eng.contact_log)
    with po.isolated(chooser="dijkstra"):
        po.advance_all(live, {**eng.ops_ctx(), "accept_mode": "auto"}, now=snap["taken_at"])
    pick = lambda rows: [(r["citizen_name"], r["ops_status"], r.get("unit_name"), r.get("shelter_name")) for r in rows]  # noqa: E731
    assert pick(sim) == pick(live)


def test_more_ambulances_never_slower_in_a_fixed_tiny_case():
    eng = _engine(n=14)  # 14 ambulance cases > 10 ambulances
    snap = ops_sim.snapshot(eng)
    runs = {k: [ops_sim.play_whatif(snap, o, 90, random.Random(i), arrivals=False) for i in range(2)]
            for k, o in (("baseline", {"kind": "baseline"}), ("plus", {"kind": "add_ambulances", "n": 4}))}
    s = ops_sim.whatif_summary(runs)
    assert s["plus"]["time_to_safe_censored_min"]["mean"] <= s["baseline"]["time_to_safe_censored_min"]["mean"]
    assert s["plus"]["vs_baseline"]["mean_diff_min"] <= 0
    assert s["baseline"]["synthetic_arrivals_per_run"] == 0


def test_rescued_people_are_not_counted_and_arrivals_are_labelled():
    eng = _engine(n=3)
    eng.contact_log[0]["ops_status"] = "rescued"
    snap = ops_sim.snapshot(eng)
    snap["arrival_rate_per_wall_s"] = 0.2  # forced: 0.2 SOS per wall s
    out = ops_sim.play_whatif(snap, {"kind": "baseline"}, 30, random.Random(5))
    real = [p for p in out["people"] if not p["synthetic"]]
    assert len(real) == 2
    assert out["added_rows"] > 0 and sum(p["synthetic"] for p in out["people"]) == out["added_rows"]


def test_option_validation_and_schema_limits():
    assert ops_sim.validate_option({"kind": "close_shelter", "name": "Nowhere Hall"}).startswith("unknown shelter")
    assert ops_sim.validate_option({"kind": "block_road", "road_id": "ZZ99"}).startswith("unknown road")
    assert ops_sim.validate_option({"kind": "add_ambulances", "n": 3}) is None
    with pytest.raises(ValidationError):
        WhatIfRequest(options=[{"kind": "add_ambulances", "n": 11}])
    with pytest.raises(ValidationError):
        WhatIfRequest(options=[{"kind": "preposition", "on": True}] * 5)
    with pytest.raises(ValidationError):
        WhatIfRequest(runs=31)


@pytest.mark.asyncio
async def test_job_lifecycle_and_one_job_at_a_time():
    eng = _engine(n=4)
    jobs = WhatIfJobs()
    job = await jobs.submit(eng, [{"kind": "add_ambulances", "n": 2}], 15, 5, arrivals=False)
    assert job["status"] in ("queued", "running") and job["tick"] == 0
    with pytest.raises(JobBusy):
        await jobs.submit(eng, [], 15, 5)
    for _ in range(600):
        if job["status"] in ("done", "failed"):
            break
        await asyncio.sleep(0.05)
    assert job["status"] == "done", job.get("error")
    assert job["progress"] == 1.0
    labels = [o["label"] for o in job["results"]["options"]]
    assert labels == ["No change", "+2 ambulances"]
    assert "vs_baseline" in job["results"]["options"][1]
    json.dumps(job["results"], allow_nan=False)


@pytest.mark.asyncio
async def test_job_refuses_without_a_run_and_new_run_cancels():
    jobs = WhatIfJobs()
    with pytest.raises(ValueError):
        await jobs.submit(SimulationEngine(), [], 15, 5)
    eng = _engine(n=4)
    job = await jobs.submit(eng, [], 60, 30, arrivals=False)
    jobs.reset()
    for _ in range(600):
        if job["status"] in ("done", "failed"):
            break
        await asyncio.sleep(0.05)
    assert job["status"] == "failed" and "cancelled" in job["error"]
    assert jobs.last_done is None


@pytest.mark.asyncio
async def test_whatif_endpoints(monkeypatch):
    from httpx import ASGITransport, AsyncClient

    from backend.api import simulation as api
    from backend.main import app
    from backend.services import whatif

    eng = _engine(n=3)
    monkeypatch.setattr(api, "engine", eng)
    monkeypatch.setattr(whatif, "jobs", WhatIfJobs())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        bad = await c.post("/api/simulation/whatif", json={"options": [{"kind": "close_shelter", "name": "Nowhere"}]})
        assert bad.status_code == 400
        r = await c.post("/api/simulation/whatif", json={"options": [{"kind": "dispatch_policy", "policy": "optimal"}],
                                                         "horizon_min": 15, "runs": 5, "arrivals": False})
        assert r.status_code == 200, r.text
        jid = r.json()["job_id"]
        for _ in range(600):
            body = (await c.get(f"/api/simulation/whatif/{jid}")).json()
            if body["status"] in ("done", "failed"):
                break
            await asyncio.sleep(0.05)
        assert body["status"] == "done" and body["stale"] is False
        eng.tick = 5
        assert (await c.get(f"/api/simulation/whatif/{jid}")).json()["stale"] is True
        assert (await c.get("/api/simulation/whatif/nope")).status_code == 404
