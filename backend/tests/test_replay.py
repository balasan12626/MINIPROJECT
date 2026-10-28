"""F5 — replay frames (memory fallback when Mongo is off), paging, playbook persistence."""
import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from backend.agents import mas as mas_mod
from backend.database import mongo
from backend.main import app
from backend.services import replay
from backend.services import person_ops as po
from backend.services.seed import RESCUE_TEAMS
from backend.simulation.engine import SimulationEngine


def _engine(run_id="SIM-REPLAY"):
    eng = SimulationEngine()
    eng.run_id = run_id
    eng.status = "running"
    eng.params = {"scenario": "heavy_rainfall"}
    eng._teams_cache = list(RESCUE_TEAMS)
    row = {"citizen_name": "Asha", "age": 70, "people": 2, "lat": 28.651, "lon": 77.262,
           "assigned_team_name": RESCUE_TEAMS[2]["name"], "assigned_team": RESCUE_TEAMS[2]["name"]}
    po.ensure_ops(row, 1)
    eng.contact_log = [row]
    eng.history = [{"tick": 0, "flood_probability": 0.62, "rainfall_mm": 120, "river_m": 205.1, "dam_m": 204.2}]
    return eng


def test_frames_fall_back_to_memory_when_mongo_is_off():
    assert not mongo.is_connected()
    store = replay.ReplayStore()
    eng = _engine()
    eng.mas._say("manager", "administrator", "hello", key="k1")
    for i in range(3):
        eng.tick = i
        asyncio.run(store.record(eng, "tick"))
    assert [f["seq"] for f in store.frames] == [1, 2, 3]
    f = store.frames[-1]
    assert f["citizens"][0]["citizen_name"] == "Asha"
    assert f["probability"] == 0.62 and f["cause"] == "tick"
    assert "multi_agent" not in f and "history" not in f, "frames must stay compact"
    # MAS messages drained once, not duplicated per frame
    assert [m["text"] for m in store.messages] == ["hello"]
    runs = asyncio.run(store.list_runs())
    assert runs["persisted"] is False and runs["runs"][0]["run_id"] == "SIM-REPLAY"
    assert runs["runs"][0]["frames"] == 3


def test_ring_buffer_is_bounded_and_resets_on_a_new_run():
    store = replay.ReplayStore()
    eng = _engine()
    for _ in range(replay.RING_FRAMES + 5):
        asyncio.run(store.record(eng, "tick"))
    assert len(store.frames) == replay.RING_FRAMES
    asyncio.run(store.record(_engine("SIM-NEXT"), "tick"))
    assert store.run_id == "SIM-NEXT" and len(store.frames) == 1


def test_frames_page_by_seq():
    store = replay.ReplayStore()
    eng = _engine()
    for _ in range(10):
        asyncio.run(store.record(eng, "tick"))
    page = asyncio.run(store.frames_page("SIM-REPLAY", 3, 6, 100))
    assert [f["seq"] for f in page["frames"]] == [3, 4, 5, 6]
    assert page["total"] == 10
    page = asyncio.run(store.frames_page("SIM-REPLAY", 8, None, 2))
    assert [f["seq"] for f in page["frames"]] == [8, 9]
    assert asyncio.run(store.frames_page("OTHER", 1, None, 5))["frames"] == []


@pytest.mark.asyncio
async def test_runs_endpoints_serve_the_live_store(monkeypatch):
    store = replay.ReplayStore()
    monkeypatch.setattr(replay, "store", store)
    eng = _engine("SIM-API")
    for _ in range(4):
        await store.record(eng, "tick")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        runs = (await c.get("/api/simulation/runs")).json()
        assert runs["runs"][0]["run_id"] == "SIM-API"
        frames = (await c.get("/api/simulation/runs/SIM-API/frames", params={"start": 2, "limit": 2})).json()
        assert [f["seq"] for f in frames["frames"]] == [2, 3] and frames["persisted"] is False
        assert (await c.get("/api/simulation/runs/NOPE")).status_code == 404
        pdf = await c.get("/api/simulation/runs/SIM-API/report.pdf")
        assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"


def test_playbook_round_trips_through_settings(monkeypatch):
    saved: dict = {}

    async def upsert(coll, query, doc):
        saved[(coll, query["_id"])] = dict(doc)
        return True

    async def find_latest(coll, query):
        return saved.get((coll, query["_id"]))

    async def delete_many(coll, query):
        return 1 if saved.pop((coll, query["_id"]), None) is not None else 0

    monkeypatch.setattr(mongo, "upsert", upsert)
    monkeypatch.setattr(mongo, "find_latest", find_latest)
    monkeypatch.setattr(mongo, "delete_many", delete_many)
    try:
        edited = mas_mod.set_playbook({"actions": {"READY": {"manager": "Edited by operator"}}})
        assert asyncio.run(replay.save_playbook(edited))
        mas_mod.set_playbook({"reset": True})  # simulate a restart: memory back to defaults
        assert mas_mod.get_playbook()["actions"]["READY"]["manager"] != "Edited by operator"
        assert asyncio.run(replay.load_playbook())
        pb = mas_mod.get_playbook()
        assert pb["actions"]["READY"]["manager"] == "Edited by operator"
        assert "SHELTER_CLOSED" in pb["actions"], "triggers added later keep their defaults"
        # reset removes the stored copy
        asyncio.run(replay.save_playbook(None))
        assert not saved
        assert asyncio.run(replay.load_playbook()) is False
    finally:
        mas_mod.set_playbook({"reset": True})


def test_engine_records_a_frame_on_operator_actions(monkeypatch):
    store = replay.ReplayStore()
    monkeypatch.setattr(replay, "store", store)
    eng = _engine("SIM-ACT")
    asyncio.run(eng.set_shelter("Chhatrasal Stadium", closed=True))
    assert store.frames and store.frames[-1]["cause"].startswith("shelter Chhatrasal Stadium")
    assert store.frames[-1]["shelter_overrides"]["Chhatrasal Stadium"]["closed"] is True
