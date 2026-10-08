"""Cross-panel consistency guards.

These pin the invariants that were violated before the canonical-threshold /
single-inference work: the Arena and the pipeline must never report different
RF/XGB values or contradictory autonomy verdicts for the same run.
"""

from backend.services.algorithm_arena import evaluate_policies, run_algorithm_arena
from backend.thresholds import MODEL_GAP_MAX, SEVERITY_MODERATE, as_dict, auto_threshold


def _pipeline_like(rf: float, xgb: float, probability: float) -> dict:
    gap = round(abs(rf - xgb), 4)
    auto_t = auto_threshold()
    straddle = min(rf, xgb) < auto_t <= max(rf, xgb)
    return {
        "prediction": {
            "flood_probability": probability,
            "risk_category": "CRITICAL",
            "dual": {
                "random_forest": rf,
                "xgboost": xgb,
                "gap": gap,
                "disagree": bool(gap >= MODEL_GAP_MAX or straddle),
                "gap_exceeds": gap >= MODEL_GAP_MAX,
                "straddle_auto": straddle,
                "hold_reason": "test",
            },
            "v2": {"available": False},
        },
        "weather": {"rainfall_mm": 148.6},
        "river": {"value_m": 204.9},
        "dam": {"value_m": 199.4},
        "shelters": [],
        "roads": [],
    }


def test_arena_reuses_pipeline_ml_result():
    """Arena must consume the pipeline's prediction, not re-infer its own."""
    pipe = _pipeline_like(rf=0.5527, xgb=0.8558, probability=0.9452)
    out = run_algorithm_arena({"pipeline": pipe, "params": {}, "history": [], "citizens": []})
    ml = out["ml"]
    assert ml["source"] == "pipeline"
    assert ml["flood_probability"] == 0.9452
    assert ml["dual"]["random_forest"] == 0.5527
    assert ml["dual"]["xgboost"] == 0.8558


def test_arena_reads_live_tick_not_scenario_seed():
    """History keys are rainfall_mm/river_m/dam_m — the seed must not win."""
    pipe = _pipeline_like(rf=0.4, xgb=0.45, probability=0.5)
    out = run_algorithm_arena(
        {
            "pipeline": pipe,
            "params": {"rainfall_intensity": 55.0},
            "history": [{"rainfall_mm": 203.4, "river_m": 205.1, "dam_m": 200.2}],
            "citizens": [],
        }
    )
    assert out["rainfall_mm"] == 203.4
    assert out["river_level_m"] == 205.1
    assert out["dam_level_m"] == 200.2


def test_arena_autonomy_agrees_with_disagreement_hold():
    """A pipeline disagreement hold must never yield FULL_AUTO."""
    dual = {
        "random_forest": 0.55,
        "xgboost": 0.86,
        "gap": 0.31,
        "disagree": True,
        "hold_reason": "gap 31.0% >= 15%",
    }
    policy = evaluate_policies(
        dual=dual,
        physics={"flood_probability": 0.6},
        ml_p=0.94,
        citizens=[],
        shelters=[],
    )
    assert policy["hold_auto_dispatch"] is True
    assert policy["autonomy_level"] != "FULL_AUTO"
    assert policy["rules"][0]["fired"] is True


def test_agreeing_models_can_reach_full_auto():
    """Guard against over-correcting into permanent MANUAL_ONLY."""
    dual = {"random_forest": 0.81, "xgboost": 0.84, "gap": 0.03, "disagree": False}
    policy = evaluate_policies(
        dual=dual,
        physics={"flood_probability": 0.78},
        ml_p=0.82,
        citizens=[],
        shelters=[],
    )
    assert policy["autonomy_level"] == "FULL_AUTO"


def test_threshold_config_is_single_source():
    cfg = as_dict()
    assert cfg["model_gap_max"] == MODEL_GAP_MAX
    assert cfg["auto_threshold"] == auto_threshold()
    assert cfg["severity_moderate"] == SEVERITY_MODERATE
