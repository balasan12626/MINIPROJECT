from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from backend.deps.auth import RequireOperator
from backend.rate_limit import limiter
from backend.services.rescue_desk import desk
from backend.services.person_report import build_person_pdf
from backend.utils.geo import jsonable

router = APIRouter()


@router.get("/api/rescue-desk/state")
async def rescue_state():
    return desk.state()


@router.post("/api/rescue-desk/sos")
@limiter.limit("30/minute")
async def rescue_sos(request: Request, body: dict, _user: RequireOperator):
    return desk.ingest_sos(body or {})


@router.post("/api/rescue-desk/sync-simulation")
@limiter.limit("30/minute")
async def sync_simulation(request: Request, _user: RequireOperator):
    from backend.simulation.engine import engine

    return desk.ingest_from_simulation(engine.state())


@router.post("/api/rescue-desk/admin/share")
@limiter.limit("30/minute")
async def admin_share(request: Request, body: dict, _user: RequireOperator):
    case_id = str((body or {}).get("case_id") or "")
    if not case_id:
        raise HTTPException(400, "case_id required")
    return desk.admin_share(case_id)


@router.post("/api/rescue-desk/ambulance/action")
@limiter.limit("60/minute")
async def ambulance_action(request: Request, body: dict, _user: RequireOperator):
    body = body or {}
    case_id = str(body.get("case_id") or "")
    ambulance_id = str(body.get("ambulance_id") or "")
    action = str(body.get("action") or "")
    if not case_id or not ambulance_id or not action:
        raise HTTPException(400, "case_id, ambulance_id, action required")
    return desk.ambulance_action(case_id, ambulance_id, action)


@router.post("/api/rescue-desk/shelter/confirm")
@limiter.limit("60/minute")
async def shelter_confirm(request: Request, body: dict, _user: RequireOperator):
    body = body or {}
    case_id = str(body.get("case_id") or "")
    if not case_id:
        raise HTTPException(400, "case_id required")
    return desk.shelter_confirm(case_id, bool(body.get("accept", True)))


@router.post("/api/rescue-desk/rescued")
@limiter.limit("60/minute")
async def rescued(request: Request, body: dict, _user: RequireOperator):
    body = body or {}
    case_id = str(body.get("case_id") or "")
    if not case_id:
        raise HTTPException(400, "case_id required")
    return desk.confirm_rescued(case_id, bool(body.get("rescued", True)))


@router.post("/api/rescue-desk/reset")
@limiter.limit("20/minute")
async def rescue_reset(request: Request, _user: RequireOperator):
    return desk.reset()


@router.get("/api/rescue-desk/person/{case_id}")
async def person_detail(case_id: str):
    return jsonable(desk.person_report(case_id))


@router.get("/api/rescue-desk/person/{case_id}/report.pdf")
async def person_pdf(case_id: str):
    report = desk.person_report(case_id)
    if not report.get("available"):
        raise HTTPException(404, "case not found")
    data = build_person_pdf(report)
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="person_{case_id}.pdf"'},
    )
