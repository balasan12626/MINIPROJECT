"""Local explanations for the flood Random Forest (TreeSHAP when available)."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from backend.ml.features import build_feature_row, feature_columns
from backend.ml.inference import _active_model, _models, load_models, predict_from_row


def _background_row(row: dict[str, Any]) -> dict[str, Any]:
    bg = dict(row)
    numeric, _ = feature_columns()
    for col in numeric:
        if col.startswith("T") and col.endswith("d") and "_z" not in col:
            bg[col] = 0.0
        elif col.endswith("_z") or col.startswith("log_"):
            bg[col] = 0.0
        elif col in {"precip_intensity_recent", "precip_frac_recent", "precip_buildup_3_10", "t10_vs_annual", "t3_vs_wettest", "t1_vs_wettest"}:
            bg[col] = 0.0
    return bg


def _interventional_bars(model, row: dict[str, Any], base_p: float, cols: list[str]) -> list[dict[str, Any]]:
    bg = _background_row(row)
    numeric, categorical = feature_columns()
    all_cols = numeric + categorical
    bars = []
    for col in cols:
        if col not in row:
            continue
        tweaked = dict(row)
        tweaked[col] = bg.get(col, 0)
        frame = pd.DataFrame([{c: tweaked.get(c, row.get(c)) for c in all_cols}])
        try:
            p = float(model.predict_proba(frame)[0, 1])
        except Exception:  # noqa: BLE001
            continue
        phi = round(base_p - p, 4)
        bars.append({"feature": col, "shap_value": phi, "direction": "raises" if phi > 0 else "lowers"})
    bars.sort(key=lambda b: abs(b["shap_value"]), reverse=True)
    return bars[:10]


def explain_prediction(rainfall_24h_mm: float, forecast_daily_mm: list[float] | None = None) -> dict[str, Any]:
    load_models()
    row = build_feature_row(rainfall_24h_mm, forecast_daily_mm)
    pred = predict_from_row(row)
    name, model = _active_model()
    if "random_forest" in _models:
        name, model = "random_forest", _models["random_forest"]
    if model is None or not pred.get("available"):
        return {"available": False, "message": "MODEL UNAVAILABLE", "bars": []}
    numeric, categorical = feature_columns()
    cols = numeric + categorical
    frame = pd.DataFrame([{c: row.get(c) for c in cols}])
    try:
        base_p = float(model.predict_proba(frame)[0, 1])
    except Exception:  # noqa: BLE001
        base_p = float(pred.get("flood_probability") or 0)
    method = "interventional SHAP-style"
    bars: list[dict[str, Any]] = []
    try:
        import shap  # type: ignore

        estimator = model
        data = frame
        if hasattr(model, "named_steps"):
            steps = list(model.named_steps.items())
            clf = steps[-1][1]
            prep = model[:-1]
            data = prep.transform(frame)
            estimator = clf
        if hasattr(estimator, "estimators_"):
            explainer = shap.TreeExplainer(estimator)
            values = explainer.shap_values(data)
            if isinstance(values, list):
                values = values[1]
            arr = np.array(values)
            if arr.ndim == 2:
                arr = arr[0]
            names = list(getattr(estimator, "feature_names_in_", None) or cols)[: len(arr)]
            for feat, val in zip(names, arr):
                bars.append({"feature": str(feat), "shap_value": round(float(val), 4), "direction": "raises" if float(val) > 0 else "lowers"})
            bars.sort(key=lambda b: abs(b["shap_value"]), reverse=True)
            bars = bars[:10]
            method = "TreeSHAP"
    except Exception:  # noqa: BLE001
        bars = _interventional_bars(model, row, base_p, numeric)
        method = "interventional SHAP-style"
    if not bars:
        bars = _interventional_bars(model, row, base_p, numeric)
        method = "interventional SHAP-style"
    return {
        "available": True,
        "method": method,
        "model_id": name or pred.get("model_id"),
        "flood_probability": round(base_p, 4),
        "risk_category": pred.get("risk_category"),
        "base_probability": round(base_p, 4),
        "bars": bars,
        "features_used": pred.get("features_used"),
        "counterfactual": rain_counterfactual(rainfall_24h_mm, forecast_daily_mm),
    }


def rain_counterfactual(
    rainfall_24h_mm: float,
    forecast_daily_mm: list[float] | None = None,
    target: float = 0.60,
) -> dict[str, Any]:
    load_models()
    model_name = "random_forest" if "random_forest" in _models else None

    def p_at(rain: float) -> float | None:
        out = predict_from_row(build_feature_row(rain, forecast_daily_mm), model_name=model_name)
        return out.get("flood_probability") if out.get("available") else None

    current_p = p_at(float(rainfall_24h_mm))
    if current_p is None:
        return {"available": False, "message": "MODEL UNAVAILABLE"}
    if current_p < target:
        return {
            "available": True,
            "needed": False,
            "current_rain_mm": round(float(rainfall_24h_mm), 1),
            "current_p": current_p,
            "target_p": target,
            "message": f"RF is already below {int(target * 100)}% at {rainfall_24h_mm:.0f} mm.",
        }
    lo, hi = 0.0, float(rainfall_24h_mm)
    best = 0.0
    for _ in range(14):
        mid = (lo + hi) / 2.0
        pm = p_at(mid)
        if pm is None:
            break
        if pm < target:
            best = mid
            lo = mid
        else:
            hi = mid
    return {
        "available": True,
        "needed": True,
        "current_rain_mm": round(float(rainfall_24h_mm), 1),
        "target_rain_mm": round(best, 1),
        "current_p": current_p,
        "target_p": target,
        "message": (
            f"Rain would need to fall from {rainfall_24h_mm:.0f} mm to ~{best:.0f} mm "
            f"for Random Forest P to drop below {int(target * 100)}%."
        ),
    }
