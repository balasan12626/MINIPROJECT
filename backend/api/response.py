from fastapi import APIRouter, HTTPException, Request

from backend.database import mongo
from backend.deps.auth import RequireAnalyst, RequireOperator
from backend.optimization.solvers import benchmark_all, run_method
from backend.rate_limit import limiter
from backend.schemas.common import OptimizationRequest
from backend.services.pipeline import last_snapshot
from backend.services.route_engine import candidate_routes
from backend.services.seed import SHELTERS, ZONES
from backend.websocket.hub import hub

router = APIRouter()


@router.get("/api/shelters")
async def shelters():
    items = await mongo.find_many("shelters", {}, limit=50, sort_field="shelter_id", direction=1)
    return {"shelters": items or SHELTERS}


@router.get("/api/routes")
async def routes(
    origin_lat: float = 28.6510,
    origin_lon: float = 77.2620,
    dest_lat: float | None = None,
    dest_lon: float | None = None,
):
    snap = last_snapshot("live")
    if dest_lat is None or dest_lon is None:
        shelters_list = snap.get("shelters") or []
        if not shelters_list:
            stored = await mongo.find_many("shelters", {}, limit=1)
            shelters_list = stored or SHELTERS
        dest_lat = float(shelters_list[0]["lat"])
        dest_lon = float(shelters_list[0]["lon"])
    items = await candidate_routes(origin_lat, origin_lon, dest_lat, dest_lon)
    return {"routes": items}


@router.post("/api/optimization/evacuation")
@limiter.limit("20/minute")
async def optimize(request: Request, body: OptimizationRequest, _user: RequireOperator):
    snap = last_snapshot("live")
    shelters_list = snap.get("shelters") or await mongo.find_many("shelters", {}, limit=8) or SHELTERS
    zones = [dict(z) for z in ZONES[:4]]
    if body.population_by_zone:
        for z in zones:
            if z["zone_id"] in body.population_by_zone:
                z["population"] = int(body.population_by_zone[z["zone_id"]])
    method = body.method or "qaoa"
    result = run_method(method, zones, shelters_list[:6], traffic=0.5)
    result["method_label"] = (
        "QAOA Simulation / Quantum-Inspired Optimization"
        if str(method).lower().startswith("qaoa")
        else str(method)
    )
    await mongo.insert("optimization_runs", result)
    await hub.broadcast("optimization_update", result)
    return result


@router.post("/api/optimization/benchmark")
@limiter.limit("10/minute")
async def opt_benchmark(request: Request, _user: RequireAnalyst):
    snap = last_snapshot("live")
    shelters_list = snap.get("shelters") or await mongo.find_many("shelters", {}, limit=8) or SHELTERS
    result = benchmark_all(ZONES[:4], shelters_list[:6], 0.5)
    await mongo.insert("benchmark_results", {"kind": "optimization", **result})
    return result
