from fastapi import APIRouter, HTTPException, Query, Request

from backend.deps.auth import RequireOperator
from backend.ml.inference import evaluation_v2, model_status, model_status_v2, predict_live, predict_peak_level_v2
from backend.ml.risk_engine import rainfall_sweep_report
from backend.rate_limit import limiter
from backend.schemas.common import ForecastV4Request, PredictionRequest
from backend.services import weather_service
from backend.services.pipeline import last_latencies, last_snapshot, run_pipeline

router = APIRouter()


@router.get("/api/config/thresholds")
async def config_thresholds():
    """The single decision-threshold config every panel must render against."""
    from backend.thresholds import as_dict

    return {"available": True, **as_dict()}


@router.post("/api/ml/predict")
@limiter.limit("60/minute")
async def ml_predict(request: Request, body: PredictionRequest):
    """Raw ML only — does not apply hybrid operational risk blending."""
    rain = body.rainfall_24h_mm
    daily = list(body.forecast_daily_mm or [])
    if rain is None:
        rain, daily_live, _ = await weather_service.rainfall_24h_and_forecast()
        if rain is None:
            return {"available": False, "message": "DATA SOURCE UNAVAILABLE and no rainfall provided"}
        if not daily:
            daily = daily_live
    out = predict_live(float(rain), daily, month=body.month)
    out["prediction_kind"] = "RAW_ML"
    out["note"] = "This is the trained model probability only. Operational risk uses a separate hybrid engine."
    return out


@router.get("/api/ml/models")
async def ml_models():
    return model_status()


@router.post("/api/ml/predict-v2")
@limiter.limit("60/minute")
async def ml_predict_v2(request: Request, body: PredictionRequest):
    """Two-stage v2: XGBoost/LightGBM-selected peak flood level regressor
    followed by a severity/alert classifier. Additive endpoint — does not
    change /api/ml/predict (v1) behavior."""
    rain = body.rainfall_24h_mm
    daily = list(body.forecast_daily_mm or [])
    if rain is None:
        rain, daily_live, _ = await weather_service.rainfall_24h_and_forecast()
        if rain is None:
            return {"available": False, "message": "DATA SOURCE UNAVAILABLE and no rainfall provided"}
        if not daily:
            daily = daily_live
    out = predict_peak_level_v2(float(rain), daily, month=body.month)
    out["prediction_kind"] = "PEAK_LEVEL_V2"
    return out


@router.get("/api/ml/models-v2")
async def ml_models_v2():
    return model_status_v2()


@router.get("/api/ml/explain-v2")
async def ml_explain_v2(rainfall_24h_mm: float | None = Query(default=None)):
    from backend.ml.explain import explain_prediction_v2
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
    return explain_prediction_v2(float(rain))


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


@router.get("/api/ml/benchmark-v2")
async def ml_benchmark_v2():
    """Real, pre-computed holdout evaluation for the active V3 model — reads
    the stored evaluation artifact, never retrains or recomputes on request."""
    return evaluation_v2()


@router.get("/api/ml/benchmark-v4")
async def ml_benchmark_v4():
    """V4 CAMELS-IND forecaster: re-scores the saved model on the untouched
    unseen-gauge test set on every call, plus the stored 20-model comparison."""
    from starlette.concurrency import run_in_threadpool
    from backend.ml.benchmark_v4 import live_benchmark

    return await run_in_threadpool(live_benchmark)


@router.get("/api/ml/v4/gauges")
async def ml_v4_gauges():
    """Unseen-gauge list for the v4 replay picker (held out of training)."""
    from starlette.concurrency import run_in_threadpool
    from backend.ml.forecast_v4 import list_gauges

    return await run_in_threadpool(list_gauges)


@router.post("/api/ml/predict-v4")
@limiter.limit("60/minute")
async def ml_predict_v4(request: Request, body: ForecastV4Request):
    """V4 flood-within-3-days forecast replayed on a real CAMELS-IND gauge-day:
    probability, actual outcome, and TreeSHAP from the same booster."""
    from starlette.concurrency import run_in_threadpool
    from backend.ml.forecast_v4 import predict_replay

    return await run_in_threadpool(predict_replay, body.gauge_id, body.date)


@router.get("/api/ml/rainfall-sweep")
@limiter.limit("20/minute")
async def ml_rainfall_sweep(
    request: Request,
    river_pct: float = Query(default=80.0),
    dam_pct: float = Query(default=80.0),
):
    """Controlled test: only rainfall changes; report raw ML vs hybrid operational risk."""
    return rainfall_sweep_report(river_pct=river_pct, dam_pct=dam_pct)


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
@limiter.limit("20/minute")
async def pipeline_refresh(request: Request, _user: RequireOperator):
    return await run_pipeline("live")


@router.get("/api/metrics")
async def metrics():
    lat = last_latencies()
    if not lat:
        return {"available": False, "message": "DATA UNAVAILABLE"}
    return {"available": True, **lat}
