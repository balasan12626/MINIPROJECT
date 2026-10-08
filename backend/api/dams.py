from fastapi import APIRouter, HTTPException, Request

from backend.rate_limit import limiter
from backend.schemas.dams import DamRiskRequest, DamSimulationRequest
from backend.services import dam_risk
from backend.data.dams import get_dam_raw
from backend.services.seed import ZONES
from backend.utils.geo import haversine_km

router = APIRouter()


def evacuation_region() -> dict:
    """The flood / evacuation region the engine actually simulates.

    Canonical source: backend/services/seed.py ZONES (the Delhi Yamuna
    floodplain). Its centre is the plain mean of the zone coordinates. There
    is exactly one evacuation region in this backend, so every scenario shares
    it; the reservoir shown next to it must be chosen relative to it."""
    lat = sum(z["lat"] for z in ZONES) / len(ZONES)
    lon = sum(z["lon"] for z in ZONES) / len(ZONES)
    return {
        "id": "delhi_yamuna",
        "name": "Delhi — Yamuna floodplain",
        "river": "Yamuna",
        "lat": round(lat, 5),
        "lon": round(lon, 5),
        "zones": [z["zone_id"] for z in ZONES],
        "source": "backend/services/seed.py ZONES (centroid)",
    }


def region_dam(dams: list[dict], region: dict) -> dict | None:
    """Nearest registry reservoir to the evacuation region (real haversine)."""
    best = None
    for d in dams:
        dist = haversine_km(region["lat"], region["lon"], float(d["lat"]), float(d["lon"]))
        d["distance_to_region_km"] = round(dist, 1)
        if best is None or dist < best["distance_km"]:
            best = {"dam_id": d["id"], "name": d["name"], "river": d.get("river"), "distance_km": round(dist, 1)}
    if best is not None:
        # Honest caveat: no registry reservoir sits on the Yamuna itself.
        best["same_river"] = str(best.get("river") or "").lower() == str(region.get("river") or "").lower()
        best["note"] = (
            "Nearest reservoir in the dam registry to the evacuation region. "
            + ("" if best["same_river"] else f"It is on the {best['river']}, not the {region['river']}: its reservoir level "
               "(m MSL) is a separate quantity from the Yamuna barrage stage used by the evacuation engine.")
        ).strip()
    return best


@router.get("/api/dams")
async def dams_list():
    dams = dam_risk.list_dams()
    region = evacuation_region()
    return {
        "available": True,
        "dams": dams,
        "scenarios": dam_risk.SCENARIO_PRESETS,
        "evacuation_region": region,
        "region_dam": region_dam(dams, region),
    }


@router.get("/api/dams/{dam_id}")
async def dams_detail(dam_id: str):
    detail = dam_risk.get_dam(dam_id)
    if not detail:
        raise HTTPException(404, f"unknown dam_id '{dam_id}'")
    raw = get_dam_raw(dam_id)
    detail["status_box"] = dam_risk.reservoir_status(raw)
    return detail


@router.get("/api/dams/{dam_id}/history")
async def dams_history(dam_id: str, days: int = 14):
    if not get_dam_raw(dam_id):
        raise HTTPException(404, f"unknown dam_id '{dam_id}'")
    days = max(1, min(90, days))
    return dam_risk.dam_history(dam_id, days=days)


@router.post("/api/simulation/run")
@limiter.limit("60/minute")
async def dam_simulation_run(request: Request, body: DamSimulationRequest):
    dam = get_dam_raw(body.dam_id)
    if not dam:
        raise HTTPException(404, f"unknown dam_id '{body.dam_id}'")
    if body.capacity_override_m is not None and body.capacity_override_m <= 0:
        raise HTTPException(400, "capacity_override_m must be > 0")

    scenario = None
    inputs = body.model_dump()
    if body.scenario:
        preset = dam_risk.SCENARIO_PRESETS.get(body.scenario)
        if not preset:
            raise HTTPException(400, f"unknown scenario '{body.scenario}'")
        scenario = {"id": body.scenario, **preset}
        for key, val in preset["defaults"].items():
            inputs[key] = val

    status = dam_risk.reservoir_status(dam, current_level_m=inputs.get("current_level_m"))
    projection = dam_risk.water_balance_projection(
        dam,
        current_level_m=inputs.get("current_level_m"),
        rainfall_mm=inputs["rainfall_mm"],
        rainfall_intensity_mm_hr=inputs["rainfall_intensity_mm_hr"],
        inflow_cumec=inputs["inflow_cumec"],
        outflow_cumec=inputs["outflow_cumec"],
        capacity_override_m=inputs.get("capacity_override_m"),
        forecast_hours=inputs["forecast_hours"],
        temperature_c=inputs.get("temperature_c"),
    )
    ml_pred = dam_risk.ml_dam_prediction(dam, rainfall_24h_mm=inputs["rainfall_mm"])
    risk = dam_risk.advanced_risk_engine(
        status=status,
        projection=projection,
        ml_pred=ml_pred,
        rainfall_mm=inputs["rainfall_mm"],
        inflow_cumec=inputs["inflow_cumec"],
        outflow_cumec=inputs["outflow_cumec"],
    )
    return {
        "available": True,
        "dam_id": body.dam_id,
        "scenario": scenario,
        "inputs": inputs,
        "status_box": status,
        "ml_prediction_box": ml_pred,
        "projection": projection,
        "risk_engine": risk,
    }


@router.post("/api/prediction/dam-risk")
@limiter.limit("60/minute")
async def dam_risk_prediction(request: Request, body: DamRiskRequest):
    dam = get_dam_raw(body.dam_id)
    if not dam:
        raise HTTPException(404, f"unknown dam_id '{body.dam_id}'")
    return dam_risk.ml_dam_prediction(
        dam,
        rainfall_24h_mm=body.rainfall_24h_mm,
        forecast_daily_mm=body.forecast_daily_mm,
        month=body.month,
    )
