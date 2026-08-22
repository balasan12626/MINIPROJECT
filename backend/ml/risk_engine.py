from __future__ import annotations

import math
from typing import Any


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
    }
