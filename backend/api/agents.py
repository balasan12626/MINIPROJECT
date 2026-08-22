from fastapi import APIRouter, Header, HTTPException

from backend.agents.dialogue import last_conversation
from backend.agents.graph import graph
from backend.database import mongo
from backend.schemas.common import ReviewRequest
from backend.services.decision_engine import evaluate_policy
from backend.services.pipeline import last_snapshot, run_pipeline
from backend.utils.security import decode_token
from backend.websocket.hub import hub

router = APIRouter()


@router.get("/api/agents/status")
async def agents_status():
    return {"agents": graph.statuses(), "shared": graph.shared}


@router.get("/api/agents/conversation")
async def agents_conversation(mode: str = "live"):
    if mode not in {"live", "simulation"}:
        mode = "live"
    return last_conversation(mode)


@router.get("/api/agents/events")
async def agents_events(limit: int = 40):
    events = await mongo.find_many("agent_events", {}, limit=limit)
    return {"events": events}


@router.get("/api/policy")
async def policy():
    snap = last_snapshot("live")
    pred = (snap or {}).get("prediction") or {}
    p = pred.get("flood_probability")
    result = evaluate_policy(p, True, bool(pred.get("available")), True)
    return result


@router.get("/api/incidents")
async def incidents():
    items = await mongo.find_many("incidents", {}, limit=20)
    return {"incidents": items}


@router.get("/api/incidents/{incident_id}")
async def incident_detail(incident_id: str):
    items = await mongo.find_many("incidents", {"incident_id": incident_id}, limit=1)
    if not items:
        raise HTTPException(404, "incident not found")
    snap = last_snapshot(items[0].get("mode") or "live")
    return {"incident": items[0], "context": {
        "weather": snap.get("weather"),
        "river": snap.get("river"),
        "dam": snap.get("dam"),
        "shelters": snap.get("shelters"),
        "routes": snap.get("routes"),
        "roads": snap.get("roads"),
    }}


@router.post("/api/policy/review")
async def review(body: ReviewRequest, authorization: str | None = Header(default=None)):
    user = body.user
    if authorization and authorization.lower().startswith("bearer "):
        payload = decode_token(authorization.split(" ", 1)[1])
        if payload:
            user = payload.get("sub") or user
    if body.decision.lower() not in {"approve", "reject"}:
        raise HTTPException(400, "decision must be approve or reject")
    doc = {
        "incident_id": body.incident_id,
        "decision": body.decision.lower(),
        "reason": body.reason,
        "user": user,
    }
    await mongo.insert("human_reviews", doc)
    await mongo.insert("audit_logs", {"action": "human_review", **doc})
    if body.decision.lower() == "approve":
        await graph.emit("evacuation", "HUMAN_REVIEW", "Human approval", "continue optimization", doc)
        inc = await mongo.find_many("incidents", {"incident_id": body.incident_id}, limit=1)
        mode = (inc[0].get("mode") if inc else None) or "live"
        snap = await run_pipeline(mode)
        await hub.broadcast("emergency_update", {"review": doc})
        return {"ok": True, "review": doc, "pipeline": snap}
    await graph.emit("evacuation", "HUMAN_REVIEW", "Human rejection", "hold automated response", doc)
    return {"ok": True, "review": doc}
