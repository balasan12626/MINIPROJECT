from __future__ import annotations

import math
from typing import Any

from backend.ml.inference import predict_live

FORMULA_DOC = (
    "operational_p = clip(0.16 + 0.50*sigmoid_rain(rain) + 0.20*stage_h + 0.14*ml_prior, 0, 1); "
    "sigmoid_rain = 1/(1+exp(-(rain-38)/12)); "
    "stage_h = mean(clip((pct-70)/30,0,1)) over river/dam percent_of_danger"
)


def operational_risk(
    ml_probability: float | None,
    rainfall_24h_mm: float,
    river_pct: float | None = None,
    dam_pct: float | None = None,
) -> dict[str, Any]:
    """Monotonic flood-risk mapping for live/simulation policy.

    INDOFLOODS Severe-vs-Flood is largely a station label, so the trained
    classifier barely moves with rainfall. This engine keeps the ML score as
    a prior and adds rainfall + stage-vs-danger, which must increase as the
    hazard increases. Coefficients are project settings, not a claim of
    extra ML accuracy.
    """
    ml = 0.5 if ml_probability is None else float(ml_probability)
    rain = max(float(rainfall_24h_mm), 0.0)
    rain_h = 1.0 / (1.0 + math.exp(-(rain - 38.0) / 12.0))
    hydros = []
    for v in (river_pct, dam_pct):
        if v is not None:
            hydros.append(min(max((float(v) - 70.0) / 30.0, 0.0), 1.0))
    hydro_h = sum(hydros) / len(hydros) if hydros else rain_h * 0.35
    p = 0.16 + 0.50 * rain_h + 0.20 * hydro_h + 0.14 * ml
    p = max(0.0, min(1.0, p))
    return {
        "flood_probability": round(p, 4),
        "ml_probability": round(ml, 4),
        "rainfall_component": round(rain_h, 4),
        "stage_component": round(hydro_h, 4),
        "probability_source": "INDOFLOODS ML prior + rainfall + stage-vs-danger",
        "prediction_kind": "HYBRID_OPERATIONAL",
        "formula": FORMULA_DOC,
    }


def rainfall_sweep_report(
    rains: list[float] | None = None,
    river_pct: float = 80.0,
    dam_pct: float = 80.0,
) -> dict[str, Any]:
    """Only rainfall changes; every other hybrid input held constant."""
    rains = rains or [5.0, 40.0, 80.0, 120.0, 150.0]
    rows = []
    for rain in rains:
        raw = predict_live(float(rain), [])
        ml_p = raw.get("flood_probability")
        hybrid = operational_risk(ml_p, float(rain), river_pct, dam_pct)
        rows.append(
            {
                "rainfall_mm": rain,
                "raw_ml_probability": ml_p,
                "raw_ml_risk": raw.get("risk_category"),
                "raw_model": raw.get("model_id"),
                "hybrid_operational_probability": hybrid["flood_probability"],
                "rainfall_component": hybrid["rainfall_component"],
                "stage_component": hybrid["stage_component"],
                "ml_prior_used": hybrid["ml_probability"],
            }
        )
    # Detect non-monotonic raw ML (legitimate model behavior vs bug)
    raw_series = [r["raw_ml_probability"] for r in rows if r["raw_ml_probability"] is not None]
    raw_non_mono = any(raw_series[i] > raw_series[i + 1] for i in range(len(raw_series) - 1)) if len(raw_series) > 1 else False
    hybrid_series = [r["hybrid_operational_probability"] for r in rows]
    hybrid_mono = all(hybrid_series[i] <= hybrid_series[i + 1] + 1e-9 for i in range(len(hybrid_series) - 1))
    return {
        "available": True,
        "controls_held_constant": {"river_pct": river_pct, "dam_pct": dam_pct, "forecast_daily_mm": []},
        "formula": FORMULA_DOC,
        "note": (
            "Raw ML non-monotonicity with rainfall alone is often legitimate for INDOFLOODS "
            "station-label classifiers (feature interactions / catchment defaults). "
            "Hybrid operational risk is designed to be monotonic in rainfall."
        ),
        "raw_ml_non_monotonic": raw_non_mono,
        "hybrid_monotonic_in_rainfall": hybrid_mono,
        "rows": rows,
    }
