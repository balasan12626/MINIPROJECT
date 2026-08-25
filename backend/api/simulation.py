from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel

from backend.deps.auth import RequireOperator
from backend.rate_limit import limiter
from backend.schemas.common import CitizenSosRequest, RescueOutcomeRequest, SimulationOverrideRequest, SimulationStartRequest
from backend.simulation.engine import SCENARIOS, engine
from backend.utils.geo import jsonable

router = APIRouter()


@router.get("/api/simulation/scenarios")
async def scenarios():
    return {
        "scenarios": [
            {
                "id": key,
                "title": val["title"],
                "story": val["story"],
                "defaults": val.get("defaults") or {},
            }
            for key, val in SCENARIOS.items()
        ]
    }


@router.post("/api/simulation/start")
@limiter.limit("30/minute")
async def start(request: Request, body: SimulationStartRequest, _user: RequireOperator):
    if body.scenario not in SCENARIOS:
        raise HTTPException(400, f"unknown scenario {body.scenario}")
    params = body.model_dump()
    return await engine.start(params)


@router.post("/api/simulation/pause")
@limiter.limit("60/minute")
async def pause(request: Request, _user: RequireOperator):
    return await engine.pause()


@router.post("/api/simulation/resume")
@limiter.limit("60/minute")
async def resume(request: Request, _user: RequireOperator):
    return await engine.resume()


@router.post("/api/simulation/reset")
@limiter.limit("20/minute")
async def reset(request: Request, _user: RequireOperator):
    return await engine.reset()


@router.post("/api/simulation/override")
@limiter.limit("60/minute")
async def override(request: Request, body: SimulationOverrideRequest, _user: RequireOperator):
    fields = body.model_dump(exclude_none=True)
    if not fields:
        raise HTTPException(400, "provide at least one card value")
    if "flood_probability" in fields and fields["flood_probability"] > 1:
        fields["flood_probability"] = fields["flood_probability"] / 100.0
    st = await engine.apply_override(fields)
    from backend.services.pipeline import last_snapshot

    st["pipeline"] = last_snapshot("simulation")
    return st


@router.post("/api/rescue/outcome")
@limiter.limit("30/minute")
async def rescue_outcome(request: Request, body: RescueOutcomeRequest, _user: RequireOperator):
    from backend.agents.dialogue import confirm_rescue, last_conversation
    from backend.database import mongo
    from backend.services.seed import RESCUE_TEAMS

    packed = await confirm_rescue(body.mode, body.rescued, {"zone": "Yamuna floodplain"})
    if body.mode == "simulation":
        for row in engine.contact_log:
            row["rescued"] = "yes" if body.rescued else "no"
            row["status"] = "rescued" if body.rescued else "missing"
    if body.rescued:
        teams = await mongo.find_many("rescue_teams", {}, limit=20, sort_field="team_id", direction=1) or list(RESCUE_TEAMS)
        for team in teams:
            if team.get("mission") == "auto_flood":
                payload = {k: v for k, v in team.items() if k != "_id"}
                payload["status"] = "COMPLETED"
                await mongo.upsert("rescue_teams", {"team_id": team["team_id"]}, payload)
    return {"ok": True, "rescued": body.rescued, "conversation": packed or last_conversation(body.mode), "contact_log": engine.contact_log}


@router.post("/api/simulation/features")
@limiter.limit("60/minute")
async def set_features(request: Request, body: dict, _user: RequireOperator):
    return await engine.set_features(body.get("features") or body)


@router.post("/api/simulation/force-dispatch")
@limiter.limit("20/minute")
async def force_dispatch(request: Request, _user: RequireOperator):
    return await engine.force_dispatch()


@router.post("/api/simulation/ask-agent")
@limiter.limit("20/minute")
async def ask_agent(request: Request, body: dict, _user: RequireOperator):
    return await engine.ask_agent(str(body.get("question") or ""))


@router.post("/api/simulation/checklist")
@limiter.limit("60/minute")
async def checklist(request: Request, body: dict, _user: RequireOperator):
    return await engine.set_checklist(body.get("checklist") or body.get("items") or [])


@router.post("/api/simulation/sos")
@limiter.limit("30/minute")
async def simulation_sos(request: Request, body: CitizenSosRequest, _user: RequireOperator):
    payload = body.model_dump()
    return await engine.add_citizen_sos(payload)


@router.get("/api/simulation/person/{citizen_name:path}/report.pdf")
async def person_sim_pdf(citizen_name: str):
    from backend.services.person_report import build_person_pdf
    from urllib.parse import unquote

    name = unquote(citizen_name).strip()
    report = engine.person_detail(name)
    if not report.get("available"):
        raise HTTPException(404, report.get("message") or "person not found")
    try:
        from backend.services.rescue_desk import desk

        st = desk.state()
        report["message_counts"] = st.get("message_counts") or {}
        report["ambulances_free"] = st.get("ambulances_free")
        report["vacant_total"] = st.get("vacant_total")
    except Exception:  # noqa: BLE001
        pass
    try:
        data = build_person_pdf(report)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"PDF build failed: {exc}") from exc
    safe = "".join(ch if ch.isalnum() else "_" for ch in name)[:40] or "person"
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="person_{safe}.pdf"'},
    )


@router.get("/api/simulation/person-report.pdf")
async def person_sim_pdf_query(name: str = ""):
    """Reliable PDF download using ?name= query (avoids path encoding issues)."""
    from backend.services.person_report import build_person_pdf

    report = engine.person_detail(name)
    if not report.get("available"):
        raise HTTPException(404, report.get("message") or "person not found")
    try:
        from backend.services.rescue_desk import desk

        st = desk.state()
        report["message_counts"] = st.get("message_counts") or {}
        report["ambulances_free"] = st.get("ambulances_free")
        report["vacant_total"] = st.get("vacant_total")
    except Exception:  # noqa: BLE001
        pass
    data = build_person_pdf(report)
    safe = "".join(ch if ch.isalnum() else "_" for ch in name)[:40] or "person"
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="person_{safe}.pdf"'},
    )


@router.get("/api/simulation/algorithm-arena")
async def algorithm_arena():
    """Compare Dijkstra / A* / greedy + policy + physics/ML twin on current sim."""
    from backend.services.algorithm_arena import run_algorithm_arena
    from backend.agents.dialogue import last_conversation
    from backend.services.pipeline import last_snapshot

    st = engine.state()
    st["pipeline"] = last_snapshot("simulation")
    st["conversation"] = last_conversation("simulation")
    return run_algorithm_arena(st)


@router.get("/api/simulation/state")
async def state():
    from backend.agents.dialogue import last_conversation
    from backend.services.pipeline import last_snapshot

    st = engine.state()
    st["pipeline"] = last_snapshot("simulation")
    st["conversation"] = last_conversation("simulation")
    return jsonable(st)


@router.get("/api/simulation/report.pdf")
async def report_pdf():
    from backend.services.report import build_report_pdf
    from backend.agents.dialogue import last_conversation
    from backend.services.pipeline import last_snapshot

    st = engine.state()
    st["pipeline"] = last_snapshot("simulation")
    st["conversation"] = last_conversation("simulation")
    pdf = build_report_pdf(jsonable(st))
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=after_action_report.pdf"},
    )
