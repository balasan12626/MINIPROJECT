"""F32 — fair dispatch: λ = 0 is exactly `optimal`; λ > 0 favours the longest-waiting group; sweep has every λ."""
import importlib.util
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.services import ops_sim
from backend.services import person_ops as po
from backend.services.seed import RESCUE_TEAMS

ROOT = Path(__file__).resolve().parents[2]
T0 = datetime(2026, 9, 24, 10, 0, 0, tzinfo=timezone.utc)


def _row(name, age, lat, lon, at, idx):
    team = RESCUE_TEAMS[2]
    row = {"citizen_name": name, "age": age, "water_level_note": "chest-deep", "people": 1, "lat": lat, "lon": lon,
           "cluster_id": "C1", "assigned_team": team["name"], "assigned_team_name": team["name"]}
    po.ensure_ops(row, idx, queue_position=1, at=at)
    row["person_index"] = idx
    return row


def test_lambda_zero_is_exactly_optimal():
    inst = ops_sim.make_instance(random.Random(5), 6, 3)
    a = ops_sim.play(inst, {"dispatch_policy": "optimal", "preposition": False})
    b = ops_sim.play(inst, {"dispatch_policy": "fair", "preposition": False, "fair_lambda": 0.0})
    assert json.dumps(a["people"], sort_keys=True) == json.dumps(b["people"], sort_keys=True)


def test_large_lambda_serves_the_longest_waiting_group_first(monkeypatch):
    monkeypatch.setattr(po, "AMBULANCE_POOL", ["Ambulance Unit 1"])
    # An elderly caller who has waited long, far away; a chest-deep caller who just called, close by.
    old = _row("Waited long", 80, 28.70, 77.23, T0, 2)
    old["timestamps"]["queued"] = (T0 - timedelta(seconds=60)).isoformat()  # in the queue 120 sim min already
    new = _row("Just called", 30, 28.63, 77.24, T0, 1)
    ctx = {"teams": RESCUE_TEAMS, "dispatch_policy": "fair", "fair_lambda": 20.0}
    po.advance_all([new, old], ctx, now=T0 + timedelta(seconds=po.DISPATCH_SECONDS + 0.5))
    assert old["ops_status"] == "assigned" and new["ops_status"] == "queued"
    assert "Fair dispatch" in new["ops_wait_reason"] or "busy" in new["ops_wait_reason"]
    assert old["dispatch_choice"]["policy"] == "fair" and old["dispatch_choice"]["lambda"] == 20.0


def test_sweep_has_every_lambda():
    spec = importlib.util.spec_from_file_location("mc32", ROOT / "scripts" / "monte_carlo_ops.py")
    mc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mc)
    from backend.geo import cities

    try:
        out = mc.fairness_sweep(cities.LEGACY, runs=1, seed_=3, n_sos=4, surge=2, lambdas=[0.0, 1.0, 4.0])
    finally:
        cities.activate(cities.LEGACY)
    names = [p["point"] for p in out["curve"]]
    assert names == ["first_free", "optimal", "fair λ=0", "fair λ=1", "fair λ=4"]
    by = {p["point"]: p for p in out["curve"]}
    assert by["fair λ=0"]["mean_time_to_safety_min"] == by["optimal"]["mean_time_to_safety_min"]
    json.dumps(out, allow_nan=False)
