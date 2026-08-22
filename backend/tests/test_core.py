from backend.ml.features import build_feature_row, live_precip_to_t_days
from backend.optimization.solvers import benchmark_all, run_method
from backend.services.decision_engine import evaluate_policy
from backend.services.seed import SHELTERS, ZONES
from backend.services.shelter_engine import filter_shelters, score_shelter


def test_precip_accumulation():
    t = live_precip_to_t_days(10, [5, 5, 5])
    assert t["T1d"] == 10
    assert t["T2d"] == 15
    assert t["T3d"] == 20
    assert t["T10d"] > t["T3d"]


def test_feature_row_keys():
    row = build_feature_row(25.0, [10, 8, 6], month=7)
    assert row["month"] == 7
    assert row["is_monsoon"] == 1
    assert "T1d" in row and "log_T1d" in row
    assert "g_prior" in row
    assert "T1d_z" in row


def test_policy_monitor():
    r = evaluate_policy(0.42, True, True, True)
    assert r["action"] == "MONITOR"


def test_policy_review():
    r = evaluate_policy(0.55, True, True, True)
    assert r["action"] == "HUMAN_REVIEW"


def test_policy_auto():
    r = evaluate_policy(0.72, True, True, True)
    assert r["action"] == "AUTOMATED_RESPONSE"


def test_policy_gate_blocks_auto():
    r = evaluate_policy(0.72, True, True, False)
    assert r["action"] == "HUMAN_REVIEW"


def test_shelter_filter_drops_full():
    kept = filter_shelters(SHELTERS, 0.4)
    assert all(s["status"] != "full" for s in kept)
    assert all(s.get("flood_risk", 0) < 0.65 for s in kept)


def test_shelter_score_finite():
    s = score_shelter(SHELTERS[0], 28.65, 77.26, 4000, 0.4, 0.5)
    assert s["distance_km"] > 0
    assert s["score"] > 0


def test_optimization_runs():
    result = run_method("greedy", ZONES[:3], SHELTERS[:4], 0.4)
    assert result["method"] == "greedy"
    assert result["constraint_violations"] >= 0
    assert len(result["assignment"]) == 3


def test_optimization_benchmark_has_four_methods():
    bench = benchmark_all(ZONES[:3], SHELTERS[:4], 0.4)
    names = {r["method"] for r in bench["runs"]}
    assert "greedy" in names
    assert "dijkstra" in names
    assert "simulated_annealing" in names
    assert "qaoa_inspired" in names
