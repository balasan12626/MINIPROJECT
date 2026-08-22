from fastapi import APIRouter, Query

from backend.ml.inference import model_status, predict_live
from backend.schemas.common import PredictionRequest
from backend.services import weather_service
from backend.services.pipeline import last_latencies, last_snapshot, run_pipeline

router = APIRouter()


@router.post("/api/ml/predict")
async def ml_predict(body: PredictionRequest):
    rain = body.rainfall_24h_mm
    daily = list(body.forecast_daily_mm or [])
    if rain is None:
        rain, daily_live, _ = await weather_service.rainfall_24h_and_forecast()
        if rain is None:
            return {"available": False, "message": "DATA SOURCE UNAVAILABLE and no rainfall provided"}
        if not daily:
            daily = daily_live
    return predict_live(float(rain), daily, month=body.month)


@router.get("/api/ml/models")
async def ml_models():
    return model_status()


@router.get("/api/ml/explain")
async def ml_explain(rainfall_24h_mm: float | None = Query(default=None)):
    from backend.ml.explain import explain_prediction
    from backend.simulation.engine import engine

    rain = rainfall_24h_mm
    if rain is None:
        hist = engine.history or []
        if hist and hist[-1].get("rainfall_mm") is not None:
            rain = float(hist[-1]["rainfall_mm"])
        else:
            snap = last_snapshot("simulation") or last_snapshot("live")
            rain = (snap.get("weather") or {}).get("rainfall_mm")
    if rain is None:
        return {"available": False, "message": "DATA UNAVAILABLE — no rainfall to explain", "bars": []}
    return explain_prediction(float(rain))


@router.get("/api/ml/benchmark")
async def ml_benchmark():
    status = model_status()
    if not status.get("evaluation"):
        return {"available": False, "message": "MODEL UNAVAILABLE — train with scripts/train_flood_model.py"}
    return {"available": True, "evaluation": status["evaluation"], "metadata": status.get("metadata")}


@router.get("/api/risk/current")
async def risk_current():
    snap = last_snapshot("live")
    if snap.get("prediction"):
        return snap["prediction"]
    snap = await run_pipeline("live")
    return snap.get("prediction") or {"available": False, "message": "MODEL UNAVAILABLE"}


@router.get("/api/pipeline/live")
async def pipeline_live():
    snap = last_snapshot("live")
    if snap.get("prediction"):
        return snap
    return await run_pipeline("live")


@router.post("/api/pipeline/refresh")
async def pipeline_refresh():
    return await run_pipeline("live")


@router.get("/api/metrics")
async def metrics():
    lat = last_latencies()
    if not lat:
        return {"available": False, "message": "DATA UNAVAILABLE"}
    return {"available": True, **lat}
