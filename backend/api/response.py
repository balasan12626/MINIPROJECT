from fastapi import APIRouter, HTTPException

from backend.database import mongo
from backend.optimization.solvers import benchmark_all, run_method
from backend.schemas.common import OptimizationRequest
from backend.services.pipeline import last_snapshot
from backend.services.route_engine import candidate_routes
from backend.services.seed import SHELTERS, ZONES
from backend.services.shelter_engine import recommend_shelters
from backend.websocket.hub import hub

router = APIRouter()


@router.get("/api/shelters")
async def shelters():
    items = await mongo.find_many("shelters", {}, limit=50, sort_field="shelter_id", direction=1)
    return {"shelters": items or SHELTERS}


@router.get("/api/routes")
async def routes(origin_lat: float = 28.6510, origin_lon: float = 77.2620, dest_lat: float | None = None, dest_lon: float | None = None):
    snap = last_snapshot("live")
    if dest_lat is None or dest_lon is None:
        shelters = snap.get("shelters") or []
        if not shelters:
            stored = await mongo.find_many("shelters", {}, limit=1)
            shelters = stored or SHELTERS
        dest_lat = float(shelters[0]["lat"])
        dest_lon = float(shelters[0]["lon"])
    items = await candidate_routes(origin_lat, origin_lon, dest_lat, dest_lon)
    return {"routes": items}


@router.post("/api/optimization/evacuation")
async def optimize(body: OptimizationRequest):
    snap = last_snapshot("live")
    shelters = snap.get("shelters") or await mongo.find_many("shelters", {}, limit=8) or SHELTERS
    zones = ZONES[:4]
    if body.population_by_zone:
        for z in zones:
            if z["zone_id"] in body.population_by_zone:
                z = dict(z)
                z["population"] = int(body.population_by_zone[z["zone_id"]])
    method = body.method or "qaoa"
    result = run_method(method, zones, shelters[:6], traffic=0.5)
    await mongo.insert("optimization_runs", result)
    await hub.broadcast("optimization_update", result)
    return result


@router.post("/api/optimization/benchmark")
async def opt_benchmark():
    snap = last_snapshot("live")
    shelters = snap.get("shelters") or await mongo.find_many("shelters", {}, limit=8) or SHELTERS
    result = benchmark_all(ZONES[:4], shelters[:6], 0.5)
    await mongo.insert("benchmark_results", {"kind": "optimization", **result})
    return result
