"""F34 — hindsight regret: frames → instance is faithful; the hindsight bound is never beaten."""
import importlib.util
import random
from datetime import timedelta
from pathlib import Path

from backend.services import ops_sim
from backend.services import person_ops as po
from backend.services.replay import ROW_KEYS
from backend.services.seed import ROADS

ROOT = Path(__file__).resolve().parents[2]
POL = {"dispatch_policy": "optimal", "preposition": False}


def _recorded_run():
    inst = ops_sim.make_instance(random.Random(9), 5, 3)
    rids = [r["road_id"] for r in ROADS]
    # the frames below record closures only, so the recorded run has no mid-run shelter closure
    inst = {**inst, "closure_schedule": [(30.0, rids[:2]), (90.0, rids[2:3])], "shelter_schedule": [], "shelter_closed": None}
    po.ROUTE_CHOOSER = "dijkstra"
    try:
        out = ops_sim.play(inst, POL, keep_rows=True)
    finally:
        po.ROUTE_CHOOSER = "qaoa"
    return inst, out


def _frames(inst, rows):
    """What engine._record would have stored: one frame per closure + a final frame."""
    frames, closed = [], []
    times = [s for s, _ in inst["closure_schedule"]] + [600.0]
    for seq, s in enumerate(times, 1):
        closed = sorted({rid for t, ids in inst["closure_schedule"] if t <= s for rid in ids})
        frames.append({"run_id": "SIM-T", "seq": seq, "at": (ops_sim.T0 + timedelta(seconds=s)).isoformat(), "city": "delhi_seed",
                       "citizens": [{k: r.get(k) for k in ROW_KEYS if r.get(k) is not None} for r in rows],
                       "roads_closed": closed, "shelter_overrides": {}, "dispatch_policy": "optimal", "preposition": False})
    return frames


def test_frames_rebuild_the_same_instance_and_replay_is_faithful():
    inst, out = _recorded_run()
    rebuilt = ops_sim.from_frames(_frames(inst, out["rows"]))
    assert sorted((c["citizen_name"], round(c["arrive_s"], 3)) for c in rebuilt["callers"]) == \
        sorted((c["citizen_name"], round(c["arrive_s"], 3)) for c in inst["callers"])
    assert rebuilt["closure_schedule"][0][1] == inst["closure_schedule"][0][1]
    spec = importlib.util.spec_from_file_location("rg", ROOT / "scripts" / "regret_runs.py")
    rg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rg)
    po.ROUTE_CHOOSER = "dijkstra"
    try:
        res = rg.regret_of(rebuilt)
    finally:
        po.ROUTE_CHOOSER = "qaoa"
    assert res["fidelity"]["policy"] == "optimal" and res["fidelity"]["people_compared"] > 0
    assert res["fidelity"]["mean_abs_diff_min"] <= 0.5, res["fidelity"]


def test_hindsight_bound_is_never_beaten():
    inst, out = _recorded_run()
    lb = ops_sim.hindsight_bound(inst)
    for p in out["people"]:
        if p["safe_min"] is not None and lb.get(p["citizen_name"]) is not None:
            assert lb[p["citizen_name"]] <= p["safe_min"] + 1e-6, p
    assert any(v is not None for v in lb.values())
