from fastapi import APIRouter, HTTPException, Request

from backend.agents.dialogue import last_conversation
from backend.agents.graph import graph
from backend.database import mongo
from backend.deps.auth import RequireOperator
from backend.rate_limit import limiter
from backend.schemas.common import ReviewRequest
from backend.services.decision_engine import evaluate_policy
from backend.services.pipeline import last_snapshot, run_pipeline
from backend.utils.geo import jsonable
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


@router.get("/api/agents/execution-trace")
async def execution_trace(mode: str = "live", limit: int = 30):
    """Ordered agent steps from persisted events + latest pipeline snapshot (not fabricated)."""
    import asyncio

    events = []
    try:
        events = await asyncio.wait_for(mongo.find_many("agent_events", {}, limit=limit), timeout=3.0) or []
    except Exception:  # noqa: BLE001
        events = []
    snap = last_snapshot(mode if mode in {"live", "simulation"} else "live") or {}
    progress = snap.get("progress") or snap.get("agent_progress") or []
    steps = []
    for ev in reversed(events):
        steps.append(
            {
                "agent": ev.get("agent") or ev.get("agent_id") or "agent",
                "event": ev.get("event") or ev.get("type"),
                "observation": ev.get("observation") or ev.get("message"),
                "action": ev.get("action"),
                "timestamp": ev.get("timestamp") or ev.get("created_at"),
                "source": "agent_events",
            }
        )
    for p in progress if isinstance(progress, list) else []:
        steps.append(
            {
                "agent": p.get("stage") or p.get("agent") or "pipeline",
                "event": "PROGRESS",
                "observation": p.get("message") or p.get("text"),
                "action": p.get("action"),
                "timestamp": p.get("timestamp"),
                "source": "pipeline_progress",
            }
        )
    # Always include current in-memory agent statuses so the panel is useful even with empty Mongo
    if not steps:
        for a in graph.statuses() or []:
            steps.append(
                {
                    "agent": a.get("name") or a.get("agent") or "agent",
                    "event": a.get("last_event") or a.get("status"),
                    "observation": a.get("current_action") or a.get("status"),
                    "action": a.get("current_action"),
                    "timestamp": a.get("timestamp"),
                    "source": "agent_status",
                }
            )
    return {
        "available": bool(steps),
        "mode": mode,
        "architecture": [
            "data",
            "flood_risk",
            "planning",
            "rescue",
            "alert",
            "monitoring",
        ],
        "honesty": "Events are real Mongo/pipeline/status records when present; empty means no run yet.",
        "steps": jsonable(steps),
    }


@router.post("/api/policy/review")
@limiter.limit("30/minute")
async def review(request: Request, body: ReviewRequest, user_ctx: RequireOperator):
    user = user_ctx.get("username") or body.user
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
