from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import joblib
import pandas as pd

from backend.config import get_settings
from backend.ml.features import build_feature_row, feature_columns
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
    disagree = bool(gap is not None and gap >= 0.10)
    straddle = False
    if rf_p is not None and xgb_p is not None:
        straddle = (min(rf_p, xgb_p) < 0.60) and (max(rf_p, xgb_p) >= 0.60)
    if straddle:
        disagree = True
    return {
        "available": bool(rf.get("available") and xgb.get("available")),
        "random_forest": rf_p,
        "xgboost": xgb_p,
        "gap": gap,
        "disagree": disagree,
        "straddle_60": straddle,
        "threshold_gap": 0.10,
        "message": (
            "Models disagree — Administrator holds auto-dispatch until they agree or an operator overrides."
            if disagree
            else "Models agree enough for automated policy."
        ),
    }
