"""F23 — early evacuation warnings: from the F10 forecast, once per zone, compliance assumed + swept."""
import copy
import importlib.util
import json
import random
from pathlib import Path

import pytest

from backend.agents import mas as mas_mod
from backend.agents.mas import MultiAgentSystem
from backend.services import ops_sim
from backend.services.seed import ROADS, ZONES
from backend.simulation.engine import SCENARIOS, SimulationEngine

ROOT = Path(__file__).resolve().parents[2]


def test_zone_road_membership_and_warn_times():
    zr = ops_sim.zone_road_ids(
        [{"zone_id": "Z", "lat": 28.60, "lon": 77.20}],
        [{"road_id": "A", "lat": 28.605, "lon": 77.20}, {"road_id": "B", "lat": 28.70, "lon": 77.20}],
    )
    assert zr == {"Z": ["A"]}
    w = ops_sim.zone_warn_times({"A": 20.0, "B": 1.0}, 15.0, zr)
    assert w == {"Z": 5.0}
    assert ops_sim.zone_warn_times({"A": 3.0}, 15.0, zr) == {"Z": 0.0}, "never before t=0"
    assert ops_sim.warned_zone_near(28.601, 77.2, 6.0, w, [{"zone_id": "Z", "lat": 28.60, "lon": 77.20}]) == "Z"
    assert ops_sim.warned_zone_near(28.601, 77.2, 4.0, w, [{"zone_id": "Z", "lat": 28.60, "lon": 77.20}]) is None


def test_warning_fires_once_per_zone_and_playbook_once():
    m = MultiAgentSystem()
    w = [{"zone_id": "Z1", "name": "Zone one", "closes_in_min": 12.0, "road_name": "Ring Road", "population": 1200},
         {"zone_id": "Z2", "name": "Zone two", "closes_in_min": 0.0, "road_name": "Bridge", "population": None}]
    assert m.announce_zone_warnings("R1", w) == 2
    assert m.announce_zone_warnings("R1", w) == 0, "no repeat on the next poll / tick"
    texts = [x["text"] for x in m.messages]
    assert any("Zone one" in t and "~12 min" in t and "1,200 people" in t for t in texts)
    assert any("Zone two" in t and "already flooding" in t for t in texts)
    playbook = [x for x in m.messages if x["kind"] == "playbook"]
    assert len(playbook) == len([a for a in mas_mod.PLAYBOOK["actions"]["ZONE_WARNING"].values() if a])


def test_engine_warns_at_the_lead_time(monkeypatch):
    eng = SimulationEngine()
    eng.params = {**SCENARIOS["heavy_rainfall"]["defaults"], "scenario": "heavy_rainfall"}
    eng.status, eng.run_id = "running", "R"
    z = ZONES[0]
    rid = ops_sim.zone_road_ids()[str(z["zone_id"])][0]
    monkeypatch.setattr(eng, "road_forecast", lambda: {rid: {"closes_in_ticks": 5, "closes_in_sim_min": 20.0}})
    monkeypatch.setitem(mas_mod.PLAYBOOK, "warning_lead_min", 30)
    got = [w for w in eng.zone_warnings() if w["zone_id"] == str(z["zone_id"])]
    assert got and got[0]["closes_in_min"] == 20.0 and got[0]["road_id"] == rid
    monkeypatch.setitem(mas_mod.PLAYBOOK, "warning_lead_min", 10)
    assert not [w for w in eng.zone_warnings() if w["zone_id"] == str(z["zone_id"]) and w["road_id"] == rid]


def test_playbook_lead_is_editable_and_bounded():
    saved = copy.deepcopy(mas_mod.PLAYBOOK)
    try:
        assert mas_mod.set_playbook({"warning_lead_min": 45})["warning_lead_min"] == 45
        assert mas_mod.set_playbook({"warning_lead_min": 9999})["warning_lead_min"] == 240
        assert "ZONE_WARNING" in mas_mod.load_playbook({})["actions"]
    finally:
        mas_mod.PLAYBOOK = saved


def test_compliance_zero_is_todays_result_exactly_and_avoids_only_late_callers():
    inst = ops_sim.make_instance(random.Random(11), 4, 6)
    assert ops_sim.avoided_by_warning(inst, 0.0, 30) == set()
    gone = ops_sim.avoided_by_warning(inst, 1.0, 600)  # everyone near a warned zone leaves
    first = {c["citizen_name"] for c in inst["callers"] if c["arrive_s"] == 0}
    assert not gone & first, "callers already in the queue cannot be avoided"
    assert gone <= {c["citizen_name"] for c in inst["callers"]}


def test_sweep_json_has_every_level(tmp_path):
    spec = importlib.util.spec_from_file_location("mc23", ROOT / "scripts" / "monte_carlo_ops.py")
    mc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mc)
    from backend.geo import cities

    try:
        out = mc.warning_sweep(cities.LEGACY, runs=1, seed_=3, n_sos=3, surge=3, levels=[0.0, 0.5, 1.0])
    finally:
        cities.activate(cities.LEGACY)
    assert [p["compliance"] for p in out["curve"]] == [0.0, 0.5, 1.0]
    assert out["compliance_source"].startswith("assumed")
    assert out["curve"][0]["sos_avoided_per_run"] == 0
    json.dumps(out, allow_nan=False)
