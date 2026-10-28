from __future__ import annotations

import json
import math
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import joblib
import pandas as pd

from backend.config import get_settings
from backend.ml.features import build_feature_row, build_feature_row_v2, feature_columns, feature_columns_v2
from backend.utils.geo import risk_category

_lock = threading.Lock()
_models: dict[str, Any] = {}
_meta: dict[str, Any] = {}
_eval: dict[str, Any] = {}
_loaded = False
_load_error: Optional[str] = None


def models_dir() -> Path:
    return get_settings().models_path


def load_models(force: bool = False) -> None:
    global _loaded, _load_error, _meta, _eval
    with _lock:
        if _loaded and not force:
            return
        directory = models_dir()
        try:
            meta_path = directory / "model_metadata.json"
            eval_path = directory / "evaluation.json"
            _meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
            _eval = json.loads(eval_path.read_text(encoding="utf-8")) if eval_path.exists() else {}
            for name in ("ensemble", "xgboost", "random_forest", "extra_trees"):
                path = directory / f"{name}_flood.pkl"
                if path.exists():
                    _models[name] = joblib.load(path)
            if not _models:
                _load_error = "MODEL UNAVAILABLE"
                _loaded = True
                return
            _load_error = None
            _loaded = True
        except Exception as exc:  # noqa: BLE001
            _load_error = f"MODEL UNAVAILABLE: {exc}"
            _loaded = True


def model_status() -> dict[str, Any]:
    load_models()
    return {
        "available": bool(_models) and not _load_error,
        "message": _load_error,
        "best_model": _meta.get("best_model"),
        "model_id": _meta.get("model_id"),
        "model_version": _meta.get("model_version"),
        "loaded": list(_models.keys()),
        "evaluation": _eval,
        "metadata": {k: v for k, v in _meta.items() if k != "default_catchment"} | {
            "has_default_catchment": bool(_meta.get("default_catchment"))
        },
    }


def _active_model():
    load_models()
    best = _meta.get("best_model") or "ensemble"
    if best in _models:
        return best, _models[best]
    for key in ("ensemble", "extra_trees", "xgboost", "random_forest"):
        if key in _models:
            return key, _models[key]
    return None, None


def predict_from_row(row: dict[str, Any], model_name: Optional[str] = None) -> dict[str, Any]:
    load_models()
    if _load_error or not _models:
        return {
            "available": False,
            "message": _load_error or "MODEL UNAVAILABLE",
            "flood_probability": None,
            "risk_category": None,
        }
    name, model = _active_model()
    if model_name and model_name in _models:
        name, model = model_name, _models[model_name]
    numeric, categorical = feature_columns()
    cols = numeric + categorical
    frame = pd.DataFrame([{c: row.get(c) for c in cols}])
    t0 = time.perf_counter()
    proba = float(model.predict_proba(frame)[0, 1])
    latency = (time.perf_counter() - t0) * 1000
    return {
        "available": True,
        "flood_probability": round(max(0.0, min(1.0, proba)), 4),
        "risk_category": risk_category(proba),
        "model_id": _meta.get("model_id") or f"{name}_flood_v1",
        "model_version": _meta.get("model_version", "1.1.0"),
        "prediction_timestamp": datetime.now(timezone.utc),
        "inference_latency_ms": round(latency, 3),
        "features_used": {k: row.get(k) for k in ["T1d", "T3d", "T7d", "T10d", "month", "is_monsoon"]},
        "message": None,
    }


def predict_live(
    rainfall_24h_mm: float,
    forecast_daily_mm: list[float] | None = None,
    month: int | None = None,
    catchment: dict[str, Any] | None = None,
    model_name: Optional[str] = None,
) -> dict[str, Any]:
    row = build_feature_row(rainfall_24h_mm, forecast_daily_mm, month, catchment)
    return predict_from_row(row, model_name=model_name)


_v2_reg = None
_v2_clf = None
_v2_meta: dict[str, Any] = {}
_v2_loaded = False
_v2_error: Optional[str] = None


def load_models_v2(force: bool = False) -> None:
    global _v2_reg, _v2_clf, _v2_meta, _v2_loaded, _v2_error
    with _lock:
        if _v2_loaded and not force:
            return
        directory = models_dir()
        try:
            # Prefer v3 stage-1 regressor (tail-weighted, confirmed better on the
            # untouched holdout) if present; v2 stays on disk as the preserved
            # baseline. Stage-2 classifier is unchanged between v2 and v3.
            meta_path = directory / "flood_model_metadata_v3.json"
            if not meta_path.exists():
                meta_path = directory / "flood_model_metadata_v2.json"
            _v2_meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
            reg_path = directory / "flood_regressor_v3.pkl"
            if not reg_path.exists():
                reg_path = directory / "flood_regressor_v2.pkl"
            clf_path = directory / "flood_alert_model_v2.pkl"
            _v2_reg = joblib.load(reg_path) if reg_path.exists() else None
            _v2_clf = joblib.load(clf_path) if clf_path.exists() else None
            if _v2_reg is None or _v2_clf is None:
                _v2_error = "MODEL UNAVAILABLE"
            else:
                _v2_error = None
            _v2_loaded = True
        except Exception as exc:  # noqa: BLE001
            _v2_error = f"MODEL UNAVAILABLE: {exc}"
            _v2_loaded = True


def get_v2_regressor():
    load_models_v2()
    return _v2_reg, dict(_v2_meta)


def evaluation_v2() -> dict[str, Any]:
    """Real, already-computed holdout evaluation for the active v2/v3 stage-1
    regressor + stage-2 classifier — read from disk, never recomputed here."""
    directory = models_dir()
    path = directory / "flood_evaluation_v3.json"
    version = "3.0.0"
    if not path.exists():
        path = directory / "flood_evaluation_v2.json"
        version = "2.0.0"
    if not path.exists():
        return {"available": False, "message": "MODEL UNAVAILABLE"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "message": f"MODEL UNAVAILABLE: {exc}"}
    load_models_v2()
    return {
        "available": True,
        "version": _v2_meta.get("version") or version,
        "stage1_model": (_v2_meta.get("stage1") or {}).get("model"),
        "stage2_model": (_v2_meta.get("stage2") or {}).get("model"),
        "regression_holdout": data.get("regression_holdout"),
        "classifier_holdout": data.get("classifier_safety_check_holdout"),
        "regression_holdout_v2_baseline": data.get("regression_holdout_v2_baseline_for_comparison"),
        "source": path.name,
    }


def model_status_v2() -> dict[str, Any]:
    load_models_v2()
    return {
        "available": bool(_v2_reg and _v2_clf) and not _v2_error,
        "message": _v2_error,
        "stage1_model": (_v2_meta.get("stage1") or {}).get("model"),
        "stage2_model": (_v2_meta.get("stage2") or {}).get("model"),
        "version": _v2_meta.get("version"),
        "metadata": {k: v for k, v in _v2_meta.items() if k != "default_catchment"},
    }


def _alert_level(prob_severe: float) -> str:
    return risk_category(prob_severe) or "LOW"


_conformal: dict[str, Any] | None = None
_conformal_loaded = False


def conformal_view(pred_level: float, prob_severe: float) -> dict[str, Any] | None:
    """F11 — attach the CV-conformal 90 % interval (peak level, metres) and
    prediction set (alert) computed by scripts/conformal_v2.py. Only for the
    model it was calibrated on (v3 regressor); otherwise None. Coverage values
    are the ones MEASURED on held-out gauges, copied from the file."""
    global _conformal, _conformal_loaded
    if not _conformal_loaded:
        _conformal_loaded = True
        path = Path(__file__).resolve().parents[2] / "models" / "conformal_v2.json"
        try:
            _conformal = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            _conformal = None
    c = _conformal
    if not c or str(_v2_meta.get("version", "")).split(".")[0] != "3":
        return None
    lvl = c.get("peak_level_abs") or {}
    alert = c.get("alert") or {}
    q_m = float(lvl.get("q_m") or 0)
    q_a = float(alert.get("q") or 1)
    pred_set = [lab for lab, p in (("no_severe_flood", 1 - prob_severe), ("severe_flood", prob_severe)) if 1 - p <= q_a]
    return {
        "level": "90% interval",
        "peak_level_low_m": round(pred_level - q_m, 1),
        "peak_level_high_m": round(pred_level + q_m, 1),
        "half_width_m": round(q_m, 1),
        "measured_coverage": lvl.get("test_coverage"),
        "measured_on": f"{(c.get('peak_level') or {}).get('test_gauges')} held-out gauges",
        "alert_set": pred_set,
        "alert_set_coverage": alert.get("test_coverage"),
        "method": c.get("method"),
        "note": lvl.get("note"),
    }


def predict_peak_level_v2(
    rainfall_24h_mm: float,
    forecast_daily_mm: list[float] | None = None,
    month: int | None = None,
    catchment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    load_models_v2()
    if _v2_error or not (_v2_reg and _v2_clf):
        return {
            "available": False,
            "message": _v2_error or "MODEL UNAVAILABLE",
            "predicted_peak_flood_level_m": None,
            "flood_type_probability": None,
            "alert_level": None,
        }
    row = build_feature_row_v2(rainfall_24h_mm, forecast_daily_mm, month, catchment)
    numeric, categorical, _ = feature_columns_v2()
    cols = numeric + categorical
    frame = pd.DataFrame([{c: row.get(c) for c in cols}])
    t0 = time.perf_counter()
    log_target = bool((_v2_meta.get("stage1") or {}).get("log_target"))
    pred = float(_v2_reg.predict(frame)[0])
    pred_level = math.expm1(pred) if log_target else pred
    frame2 = frame.copy()
    frame2["pred_peak_level"] = pred_level
    prob_severe = float(_v2_clf.predict_proba(frame2)[0, 1])
    latency = (time.perf_counter() - t0) * 1000
    return {
        "available": True,
        "predicted_peak_flood_level_m": round(pred_level, 3),
        "flood_type_probability": round(prob_severe, 4),
        "alert_level": _alert_level(prob_severe),
        # F11: measured 90 % interval / prediction set (models/conformal_v2.json)
        "uncertainty": conformal_view(pred_level, prob_severe),
        "stage1_model": (_v2_meta.get("stage1") or {}).get("model"),
        "stage2_model": (_v2_meta.get("stage2") or {}).get("model"),
        "model_version": _v2_meta.get("version"),
        "prediction_timestamp": datetime.now(timezone.utc),
        "inference_latency_ms": round(latency, 3),
        "message": None,
    }


def dual_model_view(rainfall_24h_mm: float, forecast_daily_mm: list[float] | None = None) -> dict[str, Any]:
    """Raw Random Forest vs XGBoost on the same rainfall (not the blended ops score)."""
    load_models()
    rf = predict_live(rainfall_24h_mm, forecast_daily_mm, model_name="random_forest" if "random_forest" in _models else None)
    xgb_name = "xgboost" if "xgboost" in _models else None
    xgb = predict_live(rainfall_24h_mm, forecast_daily_mm, model_name=xgb_name) if xgb_name else {"available": False, "flood_probability": None}
    rf_p = rf.get("flood_probability")
    xgb_p = xgb.get("flood_probability")
    gap = None
    if rf_p is not None and xgb_p is not None:
        gap = round(abs(float(rf_p) - float(xgb_p)), 4)
    from backend.thresholds import MODEL_GAP_MAX, auto_threshold

    auto_t = auto_threshold()
    # Two independent hold reasons, reported separately so the UI can state
    # which one fired instead of quoting a rule that isn't the active gate.
    gap_exceeds = bool(gap is not None and gap >= MODEL_GAP_MAX)
    straddle = False
    if rf_p is not None and xgb_p is not None:
        straddle = (min(rf_p, xgb_p) < auto_t) and (max(rf_p, xgb_p) >= auto_t)
    disagree = bool(gap_exceeds or straddle)
    if gap_exceeds and straddle:
        reason = f"gap {gap:.1%} >= {MODEL_GAP_MAX:.0%} and models straddle the {auto_t:.0%} auto threshold"
    elif gap_exceeds:
        reason = f"gap {gap:.1%} >= {MODEL_GAP_MAX:.0%}"
    elif straddle:
        reason = f"gap {gap:.1%} is within tolerance but models straddle the {auto_t:.0%} auto threshold"
    else:
        reason = "Models agree enough for automated policy."
    return {
        "available": bool(rf.get("available") and xgb.get("available")),
        "random_forest": rf_p,
        "xgboost": xgb_p,
        "gap": gap,
        "disagree": disagree,
        "gap_exceeds": gap_exceeds,
        "straddle_auto": straddle,
        "straddle_60": straddle,
        "threshold_gap": MODEL_GAP_MAX,
        "auto_threshold": auto_t,
        "hold_reason": reason,
        "message": (
            f"Models disagree ({reason}) — Administrator holds auto-dispatch until they agree or an operator overrides."
            if disagree
            else "Models agree enough for automated policy."
        ),
    }
