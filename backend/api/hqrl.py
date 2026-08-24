"""IEEE HQRL demo API — attached under /api/simulation/hqrl/* only."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Any, Optional

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
    return jsonable(engine.state())


@router.post("/api/simulation/hqrl/configure")
async def hqrl_configure(body: HqrlConfigBody):
    return await _emit(engine.configure(**body.model_dump(exclude_none=True)))


@router.post("/api/simulation/hqrl/start")
async def hqrl_start():
    return await _emit(engine.start())


@router.post("/api/simulation/hqrl/reset")
async def hqrl_reset():
    return await _emit(engine.reset())


@router.post("/api/simulation/hqrl/inject-closure")
async def hqrl_inject_closure(body: ClosureBody = ClosureBody()):
    return await _emit(engine.inject_road_closure(body.road_id))


@router.post("/api/simulation/hqrl/inject-conflict")
async def hqrl_inject_conflict():
    return await _emit(engine.inject_sensor_conflict())


@router.post("/api/simulation/hqrl/inject-shelter-full")
async def hqrl_inject_shelter(body: ShelterBody = ShelterBody()):
    return await _emit(engine.inject_shelter_full(body.shelter_id))


@router.post("/api/simulation/hqrl/replan")
async def hqrl_replan():
    return await _emit(engine.replan())


@router.post("/api/simulation/hqrl/accept")
async def hqrl_accept():
    return await _emit(engine.accept_route())


@router.post("/api/simulation/hqrl/reject")
async def hqrl_reject():
    return await _emit(engine.reject_route())


@router.post("/api/simulation/hqrl/failures")
async def hqrl_failures(body: FailuresBody):
    return await _emit(engine.set_failures(body.failures))


@router.post("/api/simulation/hqrl/benchmark")
async def hqrl_benchmark(body: BenchmarkBody = BenchmarkBody()):
    return await _emit(engine.run_benchmark(body.n_scenarios, body.seed))


@router.post("/api/simulation/hqrl/ablation")
async def hqrl_ablation(body: BenchmarkBody = BenchmarkBody()):
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
async def hqrl_demo_sequence():
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
    return jsonable({"steps": [{"step": s["step"], "name": s["name"], "phase": s["state"].get("demo_phase")} for s in steps], "final": final})
