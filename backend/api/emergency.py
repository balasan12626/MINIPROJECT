from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.agents.graph import graph
from backend.database import mongo
from backend.deps.auth import RequireAuth, RequireOperator
from backend.rate_limit import limiter
from backend.schemas.common import RescueStatusUpdate, SosRequest
from backend.services.seed import RESCUE_TEAMS
from backend.services.sos_cluster import cluster_emergencies
from backend.utils.geo import haversine_km, jsonable, utcnow
from backend.utils.security import authenticate_user, create_token
from backend.websocket.hub import hub

VALID_STATUS = {"AVAILABLE", "ASSIGNED", "TRAVELLING", "ARRIVED", "RESCUING", "COMPLETED"}

router = APIRouter()


class LoginBody(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


@router.post("/api/emergency/sos")
@limiter.limit("30/minute")
async def sos(request: Request, body: SosRequest, _user: RequireOperator):
    doc = {
        "lat": body.lat,
        "lon": body.lon,
        "people": body.people,
        "emergency_type": body.emergency_type,
        "medical_need": body.medical_need,
        "notes": body.notes,
        "status": "open",
        "timestamp": utcnow(),
    }
    inserted = await mongo.insert("emergency_requests", doc)
    doc["id"] = inserted
    safe = jsonable(doc)
    await graph.emit("rescue", "SOS", "Citizen SOS received", "queue rescue assignment", safe)
    await hub.broadcast("emergency_update", safe)
    teams = await mongo.find_many("rescue_teams", {}, limit=20, sort_field="team_id", direction=1) or RESCUE_TEAMS
    available = [t for t in teams if str(t.get("status") or "AVAILABLE").upper() == "AVAILABLE"] or teams
    assignment = None
    if available:
        team = min(available, key=lambda t: haversine_km(body.lat, body.lon, t["lat"], t["lon"]))
        assignment = {
            "team_id": team["team_id"],
            "emergency_id": inserted,
            "status": "ASSIGNED",
            "lat": body.lat,
            "lon": body.lon,
        }
        await mongo.insert("rescue_assignments", assignment)
        await mongo.upsert(
            "rescue_teams",
            {"team_id": team["team_id"]},
            {**{k: v for k, v in team.items() if k != "_id"}, "status": "ASSIGNED"},
        )
        await graph.emit(
            "rescue",
            "RESCUE_RESPONSE",
            "Rescue assignment created",
            "dispatch nearest team",
            jsonable(assignment),
        )
        await hub.broadcast("rescue_update", jsonable(assignment))
    emergencies = await mongo.find_many("emergency_requests", {}, limit=200)
    clusters = cluster_emergencies(emergencies, teams)
    await hub.broadcast("sos_clusters", clusters)
    return {"emergency": safe, "assignment": jsonable(assignment), "clusters": clusters}


@router.get("/api/emergency")
async def list_emergencies():
    return {"emergencies": jsonable(await mongo.find_many("emergency_requests", {}, limit=100))}


@router.get("/api/emergency/clusters")
async def sos_clusters():
    emergencies = await mongo.find_many("emergency_requests", {}, limit=200)
    teams = await mongo.find_many("rescue_teams", {}, limit=20, sort_field="team_id", direction=1) or RESCUE_TEAMS
    return cluster_emergencies(emergencies, teams)


@router.get("/api/emergency/{eid}")
async def get_emergency(eid: str):
    items = await mongo.find_many("emergency_requests", {}, limit=100)
    for item in items:
        if item.get("_id") == eid or item.get("id") == eid:
            return jsonable(item)
    raise HTTPException(404, "emergency not found")


@router.get("/api/rescue/teams")
async def teams():
    items = await mongo.find_many("rescue_teams", {}, limit=20, sort_field="team_id", direction=1)
    return {"teams": jsonable(items or RESCUE_TEAMS)}


@router.post("/api/rescue/assign")
@limiter.limit("30/minute")
async def assign(request: Request, team_id: str, emergency_id: str, _user: RequireOperator):
    teams_db = await mongo.find_many("rescue_teams", {"team_id": team_id}, limit=1)
    if not teams_db and not any(t["team_id"] == team_id for t in RESCUE_TEAMS):
        raise HTTPException(404, "team not found")
    assignment = {"team_id": team_id, "emergency_id": emergency_id, "status": "ASSIGNED", "timestamp": utcnow()}
    await mongo.insert("rescue_assignments", assignment)
    await mongo.upsert("rescue_teams", {"team_id": team_id}, {"status": "ASSIGNED"})
    await hub.broadcast("rescue_update", assignment)
    return assignment


@router.patch("/api/rescue/{team_id}/status")
@limiter.limit("60/minute")
async def patch_status(request: Request, team_id: str, body: RescueStatusUpdate, _user: RequireOperator):
    status = body.status.upper()
    if status not in VALID_STATUS:
        raise HTTPException(400, f"status must be one of {sorted(VALID_STATUS)}")
    await mongo.upsert("rescue_teams", {"team_id": team_id}, {"status": status, "team_id": team_id})
    await hub.broadcast("rescue_update", {"team_id": team_id, "status": status})
    return {"team_id": team_id, "status": status}


@router.post("/api/auth/login")
@limiter.limit("20/minute")
async def login(request: Request, body: LoginBody):
    user = authenticate_user(body.username, body.password)
    if not user:
        raise HTTPException(401, "invalid credentials")
    return {
        "access_token": create_token(user["username"], user["role"]),
        "token_type": "bearer",
        "role": user["role"],
        "username": user["username"],
    }


@router.get("/api/auth/me")
async def me(user: RequireAuth):
    return {"username": user["username"], "role": user["role"]}
