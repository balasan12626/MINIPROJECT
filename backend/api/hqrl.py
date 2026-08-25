"""IEEE HQRL demo API — attached under /api/simulation/hqrl/* only."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Any, Optional

from backend.deps.auth import RequireAnalyst, RequireOperator
from backend.rate_limit import limiter
from backend.simulation.hqrl_demo import engine
from backend.utils.geo import jsonable
from backend.websocket.hub import hub

router = APIRouter(tags=["hqrl-demo"])


class HqrlConfigBody(BaseModel):
    seed: Optional[int] = 42
    n_groups: Optional[int] = Field(default=6, ge=1, le=20)
    n_shelters: Optional[int] = Field(default=3, ge=2, le=3)
    shelter_capacity_scale: Optional[float] = Field(default=1.0, ge=0.3, le=2.0)
    flood_severity: Optional[float] = Field(default=0.35, ge=0.0, le=1.0)
    traffic_level: Optional[float] = Field(default=0.40, ge=0.0, le=1.0)
    n_road_closures: Optional[int] = Field(default=0, ge=0, le=8)
    vehicles_available: Optional[int] = Field(default=8, ge=1, le=40)


class ClosureBody(BaseModel):
    road_id: Optional[str] = None


class ShelterBody(BaseModel):
    shelter_id: Optional[str] = None


class FailuresBody(BaseModel):
    failures: dict[str, bool] = Field(default_factory=dict)


class BenchmarkBody(BaseModel):
    n_scenarios: int = Field(default=10, ge=1, le=100)
    seed: Optional[int] = None


async def _emit(state: dict) -> dict:
    payload = jsonable(state)
    try:
        await hub.broadcast("hqrl_state", payload)
    except Exception:  # noqa: BLE001
        pass
    return payload


@router.get("/api/simulation/hqrl/state")
async def hqrl_state():
    st = jsonable(engine.state())
    st["network_kind"] = "SYNTHETIC_RESEARCH_NETWORK"
    st["honesty"] = {
        "network": "SYNTHETIC",
        "ppo": "HEURISTIC_POLICY_SCORING",
        "qaoa": "SIMULATED_QUANTUM_INSPIRED",
    }
    return st


@router.post("/api/simulation/hqrl/configure")
@limiter.limit("30/minute")
async def hqrl_configure(request: Request, body: HqrlConfigBody, _user: RequireOperator):
    return await _emit(engine.configure(**body.model_dump(exclude_none=True)))


@router.post("/api/simulation/hqrl/start")
@limiter.limit("30/minute")
async def hqrl_start(request: Request, _user: RequireOperator):
    return await _emit(engine.start())


@router.post("/api/simulation/hqrl/reset")
@limiter.limit("20/minute")
async def hqrl_reset(request: Request, _user: RequireOperator):
    return await _emit(engine.reset())


@router.post("/api/simulation/hqrl/inject-closure")
@limiter.limit("30/minute")
async def hqrl_inject_closure(request: Request, body: ClosureBody, _user: RequireOperator):
    return await _emit(engine.inject_road_closure(body.road_id))


@router.post("/api/simulation/hqrl/inject-conflict")
@limiter.limit("30/minute")
async def hqrl_inject_conflict(request: Request, _user: RequireOperator):
    return await _emit(engine.inject_sensor_conflict())


@router.post("/api/simulation/hqrl/inject-shelter-full")
@limiter.limit("30/minute")
async def hqrl_inject_shelter(request: Request, body: ShelterBody, _user: RequireOperator):
    return await _emit(engine.inject_shelter_full(body.shelter_id))


@router.post("/api/simulation/hqrl/replan")
@limiter.limit("30/minute")
async def hqrl_replan(request: Request, _user: RequireOperator):
    return await _emit(engine.replan())


@router.post("/api/simulation/hqrl/accept")
@limiter.limit("30/minute")
async def hqrl_accept(request: Request, _user: RequireOperator):
    return await _emit(engine.accept_route())


@router.post("/api/simulation/hqrl/reject")
@limiter.limit("30/minute")
async def hqrl_reject(request: Request, _user: RequireOperator):
    return await _emit(engine.reject_route())


@router.post("/api/simulation/hqrl/failures")
@limiter.limit("30/minute")
async def hqrl_failures(request: Request, body: FailuresBody, _user: RequireOperator):
    return await _emit(engine.set_failures(body.failures))


@router.post("/api/simulation/hqrl/benchmark")
@limiter.limit("10/minute")
async def hqrl_benchmark(request: Request, body: BenchmarkBody, _user: RequireAnalyst):
    return await _emit(engine.run_benchmark(body.n_scenarios, body.seed))


@router.post("/api/simulation/hqrl/ablation")
@limiter.limit("10/minute")
async def hqrl_ablation(request: Request, body: BenchmarkBody, _user: RequireAnalyst):
    return await _emit(engine.run_ablation(body.n_scenarios, body.seed, store_only=False))


@router.get("/api/simulation/hqrl/paper-pack")
async def hqrl_paper_pack():
    return jsonable(engine.paper_pack())


@router.get("/api/simulation/hqrl/export")
async def hqrl_export():
    data = engine.export_results()
    return JSONResponse(
        content=jsonable(data),
        headers={"Content-Disposition": 'attachment; filename="hqrl_synthetic_results.json"'},
    )


@router.get("/api/simulation/hqrl/export.csv")
async def hqrl_export_csv():
    from fastapi.responses import PlainTextResponse

    if not engine.benchmark:
        engine.run_benchmark(10, engine.config.seed)
    return PlainTextResponse(
        engine.benchmark_csv(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="hqrl_benchmark_table.csv"'},
    )


@router.get("/api/simulation/hqrl/export.tex")
async def hqrl_export_tex():
    from fastapi.responses import PlainTextResponse

    if not engine.benchmark:
        engine.run_benchmark(10, engine.config.seed)
    return PlainTextResponse(
        engine.latex_table(),
        media_type="application/x-tex",
        headers={"Content-Disposition": 'attachment; filename="hqrl_table.tex"'},
    )


@router.post("/api/simulation/hqrl/demo-sequence")
@limiter.limit("10/minute")
async def hqrl_demo_sequence(request: Request, _user: RequireOperator):
    """One-shot scripted IEEE viva sequence (synchronous steps for UI orchestration)."""
    steps: list[dict[str, Any]] = []
    engine.start()
    steps.append({"step": 1, "name": "initial", "state": engine.state()})
    engine.inject_road_closure()
    steps.append({"step": 2, "name": "closure", "state": engine.state()})
    engine.replan()
    steps.append({"step": 3, "name": "replan", "state": engine.state()})
    engine.accept_route()
    steps.append({"step": 4, "name": "accept", "state": engine.state()})
    engine.inject_shelter_full()
    steps.append({"step": 5, "name": "shelter_full", "state": engine.state()})
    engine.replan()
    steps.append({"step": 6, "name": "replan2", "state": engine.state()})
    final = engine.state()
    await hub.broadcast("hqrl_state", jsonable(final))
    return jsonable(
        {
            "steps": [{"step": s["step"], "name": s["name"], "phase": s["state"].get("demo_phase")} for s in steps],
            "final": final,
        }
    )
