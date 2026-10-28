"""F11 — conformal uncertainty: the quantile rule, the stored artifact, and what inference attaches."""
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

from backend.ml import inference

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "models" / "conformal_v2.json"


def _script():
    spec = importlib.util.spec_from_file_location("conformal_v2", ROOT / "scripts" / "conformal_v2.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_conformal_quantile_is_the_finite_sample_rank():
    mod = _script()
    scores = np.arange(1, 101, dtype=float)  # 1..100
    # ⌈(100+1)·0.9⌉ = 91st smallest
    assert mod.conformal_quantile(scores, 0.10) == 91.0
    # tiny n: never beyond the largest score
    assert mod.conformal_quantile(np.array([0.2, 0.5]), 0.10) == 0.5


def test_prediction_set_contains_every_label_with_score_below_q():
    mod = _script()
    assert mod.prediction_set(0.95, 0.2) == ["severe_flood"]
    assert mod.prediction_set(0.05, 0.2) == ["no_severe_flood"]
    assert mod.prediction_set(0.5, 0.6) == ["no_severe_flood", "severe_flood"]


@pytest.mark.skipif(not ART.exists(), reason="run scripts/conformal_v2.py first")
def test_artifact_is_honest_about_how_it_was_measured():
    d = json.loads(ART.read_text(encoding="utf-8"))
    assert d["no_test_tuning"] is True and "TRAINING gauges only" in d["method"]
    lvl = d["peak_level_abs"]
    assert lvl["q_m"] > 0 and 0 <= lvl["test_coverage"] <= 1
    assert d["peak_level"]["test_gauges"] > 0 and d["peak_level"]["n_calibration_gauges"] > d["peak_level"]["test_gauges"]
    assert any("blend" in c for c in d["caveats"])


@pytest.mark.skipif(not ART.exists(), reason="run scripts/conformal_v2.py first")
def test_inference_attaches_interval_only_for_the_calibrated_model(monkeypatch):
    d = json.loads(ART.read_text(encoding="utf-8"))
    monkeypatch.setattr(inference, "_conformal_loaded", False)
    monkeypatch.setattr(inference, "_v2_meta", {"version": "3.0.0"})
    u = inference.conformal_view(300.0, 0.9)
    q = d["peak_level_abs"]["q_m"]
    assert u["peak_level_low_m"] == round(300.0 - q, 1) and u["peak_level_high_m"] == round(300.0 + q, 1)
    assert u["measured_coverage"] == d["peak_level_abs"]["test_coverage"]
    assert u["alert_set"]
    monkeypatch.setattr(inference, "_v2_meta", {"version": "2.0.0"})
    assert inference.conformal_view(300.0, 0.9) is None, "never reuse v3's calibration for another model"
