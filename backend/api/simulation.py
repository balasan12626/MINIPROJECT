from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from backend.deps.auth import RequireOperator
from backend.rate_limit import limiter
from backend.schemas.common import (
    CitizenSosRequest,
    RescueOutcomeRequest,
    RoadOverrideRequest,
    ShelterOverrideRequest,
    SimulationOverrideRequest,
    SimulationStartRequest,
    WhatIfRequest,
)
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
    from backend.geo.cities import available_ids

    if body.city and body.city not in available_ids():
        raise HTTPException(400, f"unknown city {body.city}")
    params = body.model_dump()
    from backend.services.rain_forecast import ForecastUnavailable

    try:
        return await engine.start(params)
    except ForecastUnavailable as e:  # F18: never a silent fallback to the scenario number
        raise HTTPException(503, f"{e} - the run was not started (choose scenario rainfall or retry)") from None


@router.get("/api/cities")
async def cities_list():
    """F7 — cities the twin can run on (OSM networks + the demo network)."""
    from backend.geo.cities import active_id, list_cities

    return {"cities": list_cities(), "active": active_id()}


@router.get("/api/cities/{city_id}")
async def city_view(city_id: str):
    """Static map data for one city: shelters, depots, zones, water, road shapes."""
    from backend.geo.cities import view

    try:
        return view(city_id)
    except KeyError:
        raise HTTPException(404, f"unknown city {city_id}") from None


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


@router.get("/api/simulation/roads")
async def simulation_roads():
    """Current road network for this run: closures, who closed them, and how
    many active route legs drive on each road."""
    return {"roads": engine.road_status(), "log": engine.road_log[-30:]}


@router.post("/api/simulation/road")
@limiter.limit("60/minute")
async def simulation_road(request: Request, body: RoadOverrideRequest, _user: RequireOperator):
    """Block / open a road (or hand it back to the flood rule). Active units
    whose route uses a newly closed road are re-planned immediately."""
    if not body.clear and body.blocked is None:
        raise HTTPException(400, "send blocked: true/false or clear: true")
    try:
        return await engine.set_road(body.road_id.strip().upper(), blocked=body.blocked, clear=body.clear)
    except KeyError:
        raise HTTPException(404, f"unknown road {body.road_id}") from None


class AcceptModeBody(BaseModel):
    mode: str


class RejectBody(BaseModel):
    reason: str | None = None


@router.post("/api/simulation/accept-mode")
@limiter.limit("30/minute")
async def accept_mode(request: Request, body: AcceptModeBody, _user: RequireOperator):
    """"auto" = crews accept every request after roll-out (today's behaviour);
    "manual" = each request waits for Accept / Reject in the driver app."""
    try:
        return await engine.set_accept_mode(body.mode.strip().lower())
    except ValueError:
        raise HTTPException(400, "mode must be 'auto' or 'manual'") from None


@router.get("/api/simulation/unit/{unit_name}")
async def unit_job(unit_name: str):
    """Driver app view of one unit: its waiting request, current job, or free."""
    view = engine.unit_view(unit_name)
    if view is None:
        raise HTTPException(404, f"unknown unit {unit_name}")
    return view


@router.post("/api/simulation/unit/{unit_name}/accept")
@limiter.limit("60/minute")
async def unit_accept(request: Request, unit_name: str, _user: RequireOperator):
    try:
        return await engine.driver_answer(unit_name, True)
    except LookupError:
        raise HTTPException(409, "No request is waiting for this unit - it was answered, timed out or moved on") from None


@router.post("/api/simulation/unit/{unit_name}/reject")
@limiter.limit("60/minute")
async def unit_reject(request: Request, unit_name: str, body: RejectBody, _user: RequireOperator):
    try:
        return await engine.driver_answer(unit_name, False, body.reason)
    except LookupError:
        raise HTTPException(409, "No request is waiting for this unit - it was answered, timed out or moved on") from None


@router.post("/api/simulation/shelter")
@limiter.limit("60/minute")
async def simulation_shelter(request: Request, body: ShelterOverrideRequest, _user: RequireOperator):
    """Close / reopen a shelter, change its capacity, or reset it. Active groups
    that can no longer use it move to the nearest open shelter at once."""
    if not body.clear and body.closed is None and body.capacity is None:
        raise HTTPException(400, "send closed, capacity or clear: true")
    try:
        return await engine.set_shelter(body.name.strip(), closed=body.closed, capacity=body.capacity, clear=body.clear)
    except KeyError:
        raise HTTPException(404, f"unknown shelter {body.name}") from None


class MergeBody(BaseModel):
    keep: str = Field(min_length=1, max_length=80)
    drop: str = Field(min_length=1, max_length=80)


class NotDuplicateBody(BaseModel):
    a: str = Field(min_length=1, max_length=80)
    b: str = Field(min_length=1, max_length=80)


@router.post("/api/simulation/sos/merge")
@limiter.limit("60/minute")
async def simulation_sos_merge(request: Request, body: MergeBody, _user: RequireOperator):
    """F30: the operator confirms two SOS are the same people. `drop` is kept in
    the roster (status "merged") with its history; its unit is freed."""
    try:
        return await engine.merge_sos(body.keep.strip(), body.drop.strip())
    except KeyError:
        raise HTTPException(404, "unknown SOS") from None
    except ValueError as e:
        raise HTTPException(409, str(e)) from None


@router.post("/api/simulation/sos/not-duplicate")
@limiter.limit("60/minute")
async def simulation_sos_not_duplicate(request: Request, body: NotDuplicateBody, _user: RequireOperator):
    """F30: stop suggesting this pair for the rest of the run."""
    return await engine.dismiss_duplicate(body.a.strip(), body.b.strip())


class PatrolBody(BaseModel):
    zone_id: str = Field(min_length=1, max_length=40)


@router.post("/api/simulation/patrol")
@limiter.limit("30/minute")
async def simulation_patrol(request: Request, body: PatrolBody, _user: RequireOperator):
    """F29: nearest free ambulance → centre of a modelled silent area (staging move)."""
    try:
        return await engine.send_patrol(body.zone_id.strip())
    except KeyError:
        raise HTTPException(404, "no silent area with that zone id") from None
    except ValueError as e:
        raise HTTPException(409, str(e)) from None


@router.post("/api/simulation/whatif")
@limiter.limit("6/minute")
async def simulation_whatif(request: Request, body: WhatIfRequest, _user: RequireOperator):
    """F16: play the next N simulated minutes from a COPY of the live run, once
    per option (plus a "no change" baseline). Returns a job id to poll."""
    from backend.services.whatif import JobBusy, jobs

    try:
        job = await jobs.submit(engine, [o.model_dump(exclude_none=True) for o in body.options],
                                body.horizon_min, body.runs, body.arrivals)
    except JobBusy as e:
        raise HTTPException(409, f"a what-if is already running ({e})") from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    return jsonable(job)


@router.get("/api/simulation/whatif/{job_id}")
async def simulation_whatif_status(job_id: str):
    from backend.services.whatif import STALE_TICKS, jobs

    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "unknown what-if job")
    out = dict(job)
    out["stale"] = engine.run_id != job["run_id"] or int(engine.tick or 0) - int(job["tick"]) >= STALE_TICKS
    return jsonable(out)


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


@router.get("/api/simulation/ai/suggest")
async def simulation_ai_suggest():
    """Real names from the current run, for the AI tab's suggestion chips."""
    order = {"queued": 0, "en_route": 1, "assigned": 2, "to_shelter": 3, "rescued": 4}
    rows = sorted(engine.contact_log, key=lambda r: order.get(r.get("ops_status") or "queued", 5))
    return {"people": [r.get("citizen_name") for r in rows[:6]], "run_status": engine.status}


@router.post("/api/simulation/ai")
@limiter.limit("40/minute")
async def simulation_ai(request: Request):
    """AI tab: grounded answers about people, places, dams, ambulances, shelters."""
    from backend.services import dam_risk
    from backend.services.ai_assistant import answer

    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    body = body if isinstance(body, dict) else {}
    history = body.get("history") if isinstance(body.get("history"), list) else []
    return await answer(str(body.get("question") or ""), engine.state(), dam_risk.list_dams(), history[-8:])


@router.post("/api/simulation/sos/surge")
@limiter.limit("10/minute")
async def simulation_sos_surge(request: Request, _user: RequireOperator):
    """Add many SOS calls at once (default 50) — the surge demo."""
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    return await engine.add_sos_surge(int((body or {}).get("count") or 50), (body or {}).get("seed"))


@router.get("/api/simulation/playbook")
async def get_playbook():
    from backend.agents.mas import get_playbook as _get

    return _get()


@router.put("/api/simulation/playbook")
@limiter.limit("30/minute")
async def put_playbook(request: Request, _user: RequireOperator):
    """Edit what each agent does per tier / on a sudden rise. Saved to Mongo
    `settings` so it survives a backend restart; {reset: true} deletes it."""
    from backend.agents.mas import set_playbook
    from backend.services.replay import save_playbook

    body = await request.json()
    body = body if isinstance(body, dict) else None
    out = set_playbook(body)
    saved = await save_playbook(None if (body or {}).get("reset") else out)
    return {**out, "persisted": saved or (body or {}).get("reset") is True}


# ---- replay (F5) -------------------------------------------------------------------


@router.get("/api/simulation/runs")
async def runs_list(limit: int = 20):
    from backend.services.replay import store

    return await store.list_runs(max(1, min(limit, 50)))


@router.get("/api/simulation/runs/{run_id}")
async def run_detail(run_id: str):
    from backend.services.replay import store

    run = await store.get_run(run_id)
    if run is None:
        raise HTTPException(404, f"unknown run {run_id}")
    return run


@router.get("/api/simulation/runs/{run_id}/frames")
async def run_frames(run_id: str, start: int = 1, end: int | None = None, limit: int = 100):
    """Frames in order, paged by `seq` (1-based). `total` is the run's frame count."""
    from backend.services.replay import store

    return await store.frames_page(run_id, start, end, limit)


@router.get("/api/simulation/runs/{run_id}/equity")
async def run_equity(run_id: str):
    """F14 — fairness table of a stored run, from its LAST frame's timestamps."""
    from backend.services.person_ops import _parse, equity_board
    from backend.services.replay import store

    page = await store.frames_page(run_id, 1, None, 1)
    total = page["total"]
    if not total:
        raise HTTPException(404, f"no stored frames for run {run_id}")
    last = (await store.frames_page(run_id, total, total, 1))["frames"] or page["frames"]
    frame = last[-1]
    return {"run_id": run_id, "at": frame.get("at"),
            **equity_board(frame.get("citizens") or [], now=_parse(frame.get("at")))}


@router.get("/api/simulation/runs/{run_id}/messages")
async def run_messages(run_id: str):
    from backend.services.replay import store

    return await store.messages_of(run_id)


@router.get("/api/simulation/runs/{run_id}/report.pdf")
async def run_report_pdf(run_id: str):
    from backend.services.replay import store
    from backend.services.report import build_report_pdf

    st = await store.report_state(run_id)
    if st is None:
        raise HTTPException(404, f"no stored frames for run {run_id}")
    return Response(
        content=build_report_pdf(jsonable(st)),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=replay_{run_id}.pdf"},
    )


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
