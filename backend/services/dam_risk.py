"""Dam Monitor domain logic for the /simulation → Dam Monitor tab.

Combines:
  - calculated reservoir status (pure arithmetic on current/full level — Box 1)
  - the existing trained ML regressor/classifier (backend/ml/inference.py — Box 2)
  - a bounded, documented water-balance simulation heuristic (Run Simulation)
  - a hybrid "advanced risk engine" that blends the two, following the same
    documented-formula convention as backend/ml/risk_engine.py::operational_risk

Nothing here retrains or recomputes model accuracy — evaluation numbers are
read verbatim from backend.ml.inference.evaluation_v2(), which loads the
already-computed holdout metrics on disk.
"""

from __future__ import annotations

import random
from datetime import timedelta
from typing import Any, Optional

from backend.data.dams import CATCHMENT_NOTE, DAM_REGISTRY, get_dam_raw
from backend.ml.inference import evaluation_v2, predict_peak_level_v2
from backend.utils.geo import risk_category, utcnow

FILL_BANDS = (
    (95.0, "CRITICAL"),
    (85.0, "VERY_HIGH"),
    (70.0, "HIGH"),
    (50.0, "MODERATE"),
)

RESPONSE_LEVEL = {
    "LOW": "MONITOR",
    "MODERATE": "MONITOR",
    "HIGH": "ALERT",
    "VERY_HIGH": "PREPARE_EVACUATION",
    "CRITICAL": "EVACUATE",
}

SIM_FORMULA_DOC = (
    "Volumetric water balance: hourly_delta_m = ((inflow_cumec - outflow_cumec) * 3600 "
    "/ effective_area_m2 + rainfall_intensity_mm_hr/1000) * temp_factor, clipped to "
    "+/-2 m/h as a physical guard. effective_area is the reservoir's average surface "
    "area over its live range (live_capacity / (FRL - dead_storage_level)). At FRL the "
    "spillway passes surplus (outflow raised to inflow); level is capped at FRL and any "
    "remaining surplus raises overtopping_risk. Uses a constant area rather than a full "
    "elevation-storage curve — adequate for what-if exploration, not a calibrated "
    "hydrology model."
)

SCENARIO_PRESETS = {
    "normal": {
        "title": "Normal",
        "story": "Baseline monsoon conditions — steady rainfall, routine inflow/outflow.",
        "defaults": {"rainfall_mm": 15.0, "rainfall_intensity_mm_hr": 3.0, "inflow_cumec": 700.0, "outflow_cumec": 650.0},
    },
    "heavy_rainfall": {
        "title": "Heavy Rainfall",
        "story": "Increased rainfall and inflow push the reservoir toward its warning band.",
        "defaults": {"rainfall_mm": 90.0, "rainfall_intensity_mm_hr": 18.0, "inflow_cumec": 1600.0, "outflow_cumec": 900.0},
    },
    "extreme_rainfall": {
        "title": "Extreme Rainfall",
        "story": "Very high rainfall with rapidly rising inflow — high-risk trajectory.",
        "defaults": {"rainfall_mm": 220.0, "rainfall_intensity_mm_hr": 45.0, "inflow_cumec": 3200.0, "outflow_cumec": 1200.0},
    },
    "emergency_release": {
        "title": "Emergency Release",
        "story": "Operators increase outflow/release to draw the reservoir down.",
        "defaults": {"rainfall_mm": 60.0, "rainfall_intensity_mm_hr": 12.0, "inflow_cumec": 1400.0, "outflow_cumec": 2400.0},
    },
    "worst_case": {
        "title": "Worst-Case Scenario",
        "story": "High rainfall, high inflow, and release capacity constrained — compounding risk.",
        "defaults": {"rainfall_mm": 260.0, "rainfall_intensity_mm_hr": 50.0, "inflow_cumec": 3600.0, "outflow_cumec": 700.0},
    },
}


def classify_fill(pct: float) -> str:
    for threshold, label in FILL_BANDS:
        if pct >= threshold:
            return label
    return "LOW"


def fill_percentage(current_level_m: float, full_level_m: float, dead_level_m: float | None = None) -> float:
    """Live-storage fill: (level - dead) / (FRL - dead), clamped to 0-100.

    These levels are absolute elevations (m MSL), so the old
    `level / full_level` ratio was meaningless — it treated sea level as an
    empty reservoir and reported ~76% for a Hirakud level that is actually
    below its dead-storage level.
    """
    if full_level_m is None or float(full_level_m) <= 0:
        return 0.0
    dead = 0.0 if dead_level_m is None else float(dead_level_m)
    span = float(full_level_m) - dead
    if span <= 0:
        return 0.0
    frac = (float(current_level_m) - dead) / span
    return round(max(0.0, min(1.0, frac)) * 100.0, 2)


def threshold_levels(full_level_m: float, dead_level_m: float | None = None) -> dict[str, float]:
    """Elevation of each band boundary, interpolated across LIVE storage."""
    dead = 0.0 if dead_level_m is None else float(dead_level_m)
    span = float(full_level_m) - dead
    return {
        "normal": round(dead + span * 0.50, 2),
        "warning": round(dead + span * 0.70, 2),
        "high_risk": round(dead + span * 0.85, 2),
        "critical": round(dead + span * 0.95, 2),
        "dead_storage": round(dead, 2),
        "full_reservoir": round(float(full_level_m), 2),
    }


def _public_dam(dam: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in dam.items() if k != "catchment_profile"}


def list_dams() -> list[dict[str, Any]]:
    out = []
    for dam in DAM_REGISTRY:
        pct = fill_percentage(dam["current_level_m"], dam["full_reservoir_level_m"], dam.get("dead_storage_level_m"))
        row = _public_dam(dam)
        row["fill_percentage"] = pct
        row["status"] = classify_fill(pct)
        row["figures_are_approximate"] = True
        row["last_updated"] = utcnow().isoformat()
        out.append(row)
    return out


def get_dam(dam_id: str) -> Optional[dict[str, Any]]:
    dam = get_dam_raw(dam_id)
    if not dam:
        return None
    row = _public_dam(dam)
    row["fill_percentage"] = fill_percentage(dam["current_level_m"], dam["full_reservoir_level_m"], dam.get("dead_storage_level_m"))
    row["status"] = classify_fill(row["fill_percentage"])
    row["figures_are_approximate"] = True
    row["last_updated"] = utcnow().isoformat()
    row["thresholds_m"] = threshold_levels(dam["full_reservoir_level_m"], dam.get("dead_storage_level_m"))
    return row


def reservoir_status(dam: dict[str, Any], current_level_m: Optional[float] = None) -> dict[str, Any]:
    """Box 1 — calculated reservoir status. Pure arithmetic, no ML involved."""
    full = float(dam["full_reservoir_level_m"])
    dead = dam.get("dead_storage_level_m")
    dead_f = float(dead) if dead is not None else 0.0
    current = max(0.0, float(current_level_m) if current_level_m is not None else float(dam["current_level_m"]))
    pct = fill_percentage(current, full, dead)
    classification = classify_fill(pct)
    return {
        "current_level_m": round(current, 2),
        "full_reservoir_level_m": full,
        "dead_storage_level_m": round(dead_f, 2) if dead is not None else None,
        "level_unit": dam.get("level_unit", "m"),
        "level_datum": dam.get("level_datum", "MSL"),
        "fill_percentage": pct,
        "remaining_level_m": round(full - current, 2),
        "status": classification,
        "overflow": current > full,
        "below_dead_storage": bool(dead is not None and current < dead_f),
        "recommended_response_level": RESPONSE_LEVEL[classification],
        "calculation": (
            "fill_percentage = (current_level_m - dead_storage_level_m) / "
            "(full_reservoir_level_m - dead_storage_level_m) * 100"
        ),
        "data_source": "calculated",
    }


def _hourly_delta(
    rainfall_mm: float,
    rainfall_intensity_mm_hr: float,
    inflow_cumec: float,
    outflow_cumec: float,
    full_level_m: float,
    temp_factor: float,
    effective_area_km2: float | None = None,
) -> float:
    """Level change per hour from a real volumetric water balance.

    dV = (inflow - outflow) * dt  ->  dh = dV / A

    The previous version divided by `full_level_m * 40.0`, a dimensionless
    invention that made 200 cumec net inflow raise a reservoir ~15 m in 72 h.
    With a true surface area (~112 km2 for Bhakra) the same net inflow gives
    ~0.0064 m/h, i.e. ~0.46 m over 72 h — physically plausible.
    """
    # Fall back to a conservative small reservoir only if area is unknown.
    area_m2 = float(effective_area_km2 or 25.0) * 1.0e6
    net_cumec = float(inflow_cumec) - float(outflow_cumec)
    flow_component = (net_cumec * 3600.0) / area_m2
    # Direct precipitation on the water surface: mm over the same area.
    direct_rain_m = (float(rainfall_intensity_mm_hr) / 1000.0)
    delta = (flow_component + direct_rain_m) * temp_factor
    # Physical guard only — not a substitute for the balance itself.
    return max(-2.0, min(2.0, delta))


def water_balance_projection(
    dam: dict[str, Any],
    *,
    current_level_m: Optional[float],
    rainfall_mm: float,
    rainfall_intensity_mm_hr: float,
    inflow_cumec: float,
    outflow_cumec: float,
    capacity_override_m: Optional[float],
    forecast_hours: int,
    temperature_c: Optional[float] = None,
) -> dict[str, Any]:
    full = float(capacity_override_m) if capacity_override_m else float(dam["full_reservoir_level_m"])
    level = max(0.0, float(current_level_m) if current_level_m is not None else float(dam["current_level_m"]))
    rainfall_mm = max(0.0, min(600.0, float(rainfall_mm)))
    rainfall_intensity = max(0.0, min(150.0, float(rainfall_intensity_mm_hr)))
    inflow = max(0.0, float(inflow_cumec))
    outflow = max(0.0, float(outflow_cumec))
    temp_factor = 1.0
    if temperature_c is not None:
        temp_factor = max(0.9, min(1.05, 1.0 - (float(temperature_c) - 25.0) * 0.002))

    dead = dam.get("dead_storage_level_m")
    area_km2 = dam.get("effective_area_km2")
    thresholds = threshold_levels(full, dead)
    # Level bands for the spillway/overtopping state machine (Phase 17).
    crossed: dict[str, int] = {}
    series: list[dict[str, Any]] = []
    now = utcnow()
    hours = int(forecast_hours)
    spillway_hours = 0
    overtopping_risk = False
    for hour in range(hours + 1):
        pct = fill_percentage(level, full, dead)
        at_frl = level >= full
        series.append(
            {
                "hour": hour,
                "timestamp": (now + timedelta(hours=hour)).isoformat(),
                "predicted_level_m": round(level, 3),
                "fill_percentage": pct,
                "rainfall_mm": rainfall_mm,
                "inflow_cumec": inflow,
                "outflow_cumec": outflow,
                "spillway_active": bool(at_frl),
            }
        )
        for label, level_m in thresholds.items():
            if label in ("dead_storage", "full_reservoir"):
                continue
            if label not in crossed and level >= level_m:
                crossed[label] = hour
        if hour == hours:
            break
        # Once the reservoir reaches FRL the spillway passes surplus: the
        # release rises to match inflow instead of the level climbing freely.
        effective_outflow = outflow
        if at_frl:
            spillway_hours += 1
            effective_outflow = max(outflow, inflow)
        delta = _hourly_delta(rainfall_mm, rainfall_intensity, inflow, effective_outflow, full, temp_factor, area_km2)
        level = max(0.0, level + delta)
        if level > full:
            # Surplus the spillway could not pass in this hour.
            overtopping_risk = True
            level = full

    start_level = series[0]["predicted_level_m"]
    end_level = series[-1]["predicted_level_m"]
    trend = "RISING" if end_level > start_level + 0.05 else ("FALLING" if end_level < start_level - 0.05 else "STABLE")

    if overtopping_risk:
        reservoir_state = "OVERTOPPING_RISK"
    elif spillway_hours:
        reservoir_state = "SPILLWAY_OPERATION"
    elif end_level >= thresholds["high_risk"]:
        reservoir_state = "WARNING"
    elif end_level >= thresholds["normal"]:
        reservoir_state = "HIGH"
    else:
        reservoir_state = "NORMAL"

    # Canonical "predicted peak" for the reservoir: the maximum of the
    # projected series (under emergency release the final level is LOWER than
    # the peak, so the final level must never be labelled as a peak).
    peak_row = max(series, key=lambda r: r["predicted_level_m"])
    return {
        "series": series,
        "thresholds_m": thresholds,
        "threshold_crossing_hours": crossed,
        "peak_level_m": peak_row["predicted_level_m"],
        "peak_hour": peak_row["hour"],
        "final_level_m": end_level,
        "final_fill_percentage": series[-1]["fill_percentage"],
        "trend": trend,
        "reservoir_state": reservoir_state,
        "spillway_hours": spillway_hours,
        "overtopping_risk": overtopping_risk,
        "effective_area_km2": area_km2,
        "area_source": dam.get("area_source"),
        "level_unit": dam.get("level_unit", "m"),
        "level_datum": dam.get("level_datum", "MSL"),
        "formula": SIM_FORMULA_DOC,
        "data_source": "simulated",
    }


def ml_dam_prediction(
    dam: dict[str, Any],
    *,
    rainfall_24h_mm: float,
    forecast_daily_mm: Optional[list[float]] = None,
    month: Optional[int] = None,
) -> dict[str, Any]:
    """Box 2 — independent ML prediction using the existing trained v2/v3 pipeline."""
    out = predict_peak_level_v2(
        float(rainfall_24h_mm), forecast_daily_mm or [], month=month, catchment=dam["catchment_profile"]
    )
    if not out.get("available"):
        return {
            "available": False,
            "message": out.get("message") or "MODEL UNAVAILABLE",
            "data_source": "ml_model",
        }
    prob = out.get("flood_type_probability")
    category = out.get("alert_level") or risk_category(prob)
    ev = evaluation_v2()
    return {
        "available": True,
        "predicted_peak_level_m": out.get("predicted_peak_flood_level_m"),
        "probability_severe": prob,
        "risk_category": category,
        "recommended_response_level": RESPONSE_LEVEL.get(category or "LOW", "MONITOR"),
        "stage1_model": out.get("stage1_model"),
        "stage2_model": out.get("stage2_model"),
        "model_version": out.get("model_version"),
        "inference_latency_ms": out.get("inference_latency_ms"),
        "catchment_note": CATCHMENT_NOTE,
        "model_evaluation": {
            "available": ev.get("available", False),
            "version": ev.get("version"),
            "regression_holdout": ev.get("regression_holdout"),
            "classifier_holdout": ev.get("classifier_holdout"),
            "source": ev.get("source"),
        },
        "prediction_kind": "PEAK_LEVEL_V2",
        "data_source": "ml_model",
    }


def _main_drivers(
    *, rainfall_mm: float, inflow_cumec: float, outflow_cumec: float, fill_pct: float, ml_probability: Optional[float]
) -> list[str]:
    drivers = []
    if rainfall_mm >= 150:
        drivers.append("Very heavy rainfall")
    elif rainfall_mm >= 60:
        drivers.append("Heavy rainfall")
    if inflow_cumec > outflow_cumec * 1.5:
        drivers.append("Rising inflow exceeding release")
    if fill_pct >= 85:
        drivers.append("Reservoir near full-reservoir level")
    if ml_probability is not None and ml_probability >= 0.5:
        drivers.append("ML model flags elevated severe-flood probability")
    if not drivers:
        drivers.append("Conditions within normal operating range")
    return drivers


def advanced_risk_engine(
    *,
    status: dict[str, Any],
    projection: dict[str, Any],
    ml_pred: dict[str, Any],
    rainfall_mm: float,
    inflow_cumec: float,
    outflow_cumec: float,
) -> dict[str, Any]:
    """Combines calculated status + simulation trend + ML output into one
    structured result, following the same clipped-weighted-blend convention
    as backend/ml/risk_engine.py::operational_risk (documented, bounded, not
    a black box)."""
    fill_pct = status["fill_percentage"]
    fill_component = min(1.0, fill_pct / 100.0)
    ml_prob = ml_pred.get("probability_severe") if ml_pred.get("available") else None
    ml_component = float(ml_prob) if ml_prob is not None else fill_component * 0.5
    rise_component = 1.0 if projection.get("trend") == "RISING" else (0.4 if projection.get("trend") == "STABLE" else 0.0)

    composite = max(0.0, min(1.0, 0.45 * fill_component + 0.35 * ml_component + 0.20 * rise_component))
    if composite >= 0.85:
        risk = "CRITICAL"
    elif composite >= 0.65:
        risk = "VERY_HIGH"
    elif composite >= 0.45:
        risk = "HIGH"
    elif composite >= 0.25:
        risk = "MODERATE"
    else:
        risk = "LOW"

    return {
        "risk": risk,
        "composite_score": round(composite, 4),
        "fill_percentage": fill_pct,
        "trend": projection.get("trend"),
        # Both read straight from the projection — one computation, no copy.
        "predicted_level_m": projection.get("final_level_m"),
        "predicted_peak_level_m": projection.get("peak_level_m"),
        "ml_confidence": round(ml_component, 4) if ml_prob is not None else None,
        "ml_confidence_source": "model probability_severe" if ml_prob is not None else "unavailable — fill/trend only",
        "main_drivers": _main_drivers(
            rainfall_mm=rainfall_mm,
            inflow_cumec=inflow_cumec,
            outflow_cumec=outflow_cumec,
            fill_pct=fill_pct,
            ml_probability=ml_prob,
        ),
        "formula": (
            "composite = clip(0.45*fill_pct/100 + 0.35*ml_probability_severe + 0.20*trend_component, 0, 1); "
            "trend_component = 1.0 RISING / 0.4 STABLE / 0.0 FALLING"
        ),
        "recommended_response_level": RESPONSE_LEVEL.get(risk, "MONITOR"),
    }


def dam_history(dam_id: str, days: int = 14) -> dict[str, Any]:
    """Deterministic synthetic history, clearly labeled — no real per-dam
    telemetry dataset exists in this repo."""
    dam = get_dam_raw(dam_id)
    if not dam:
        return {"available": False, "message": f"unknown dam_id {dam_id}"}
    rng = random.Random(dam_id)
    full = float(dam["full_reservoir_level_m"])
    dead = dam.get("dead_storage_level_m")
    floor = float(dead) if dead is not None else 0.0
    normal = float(dam["historical_normal_level_m"])
    now = utcnow()
    points = []
    level = normal
    for i in range(days, -1, -1):
        drift = rng.uniform(-0.8, 1.0)
        # Synthetic history stays inside the physically meaningful live range.
        level = max(floor, min(full, level + drift))
        points.append(
            {
                "date": (now - timedelta(days=i)).date().isoformat(),
                "level_m": round(level, 2),
                "fill_percentage": fill_percentage(level, full, dead),
            }
        )
    return {
        "available": True,
        "dam_id": dam_id,
        "points": points,
        "data_source": "simulated_history",
        "message": "Synthetic baseline pattern seeded from the dam's normal operating level — not real historical telemetry.",
    }
