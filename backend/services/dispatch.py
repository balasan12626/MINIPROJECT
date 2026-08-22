"""Automatic rescue + ambulance call when flood probability ≥ 60%."""

from __future__ import annotations

from typing import Any

from backend.agents.dialogue import risk_band
from backend.agents.graph import graph
from backend.database import mongo
from backend.services.seed import RESCUE_TEAMS, ZONES
from backend.utils.geo import jsonable


async def apply_threshold_dispatch(probability: float | None, mode: str) -> dict[str, Any]:
    band = risk_band(probability)
    places = [{"name": z["name"], "lat": z["lat"], "lon": z["lon"]} for z in ZONES[:3]]
    teams = await mongo.find_many("rescue_teams", {}, limit=20, sort_field="team_id", direction=1) or [dict(t) for t in RESCUE_TEAMS]

    if band != "auto":
        for team in teams:
            if team.get("mission") == "auto_flood":
                payload = {k: v for k, v in team.items() if k != "_id"}
                payload["status"] = "AVAILABLE"
                payload["mission"] = None
                payload["target_name"] = None
                await mongo.upsert("rescue_teams", {"team_id": team["team_id"]}, payload)
        await graph.emit("administrator", "DECISION_REQUIRED", f"Band {band}: rescue not auto-called", "hold dispatch", {"band": band, "mode": mode})
        return {"called": False, "band": band, "places": [], "teams": [], "mode": mode}

    assigned = []
    for i, team in enumerate(teams[:4]):
        place = places[i % len(places)]
        role = "ambulance" if i % 2 else "rescue"
        payload = {k: v for k, v in team.items() if k != "_id"}
        payload.update(
            {
                "status": "TRAVELLING",
                "mission": "auto_flood",
                "role": role,
                "target_name": place["name"],
                "target_lat": place["lat"],
                "target_lon": place["lon"],
                "mode": mode,
            }
        )
        await mongo.upsert("rescue_teams", {"team_id": team["team_id"]}, payload)
        assigned.append(jsonable({"team_id": team["team_id"], "name": team.get("name"), "role": role, "place": place["name"]}))

    names = ", ".join(p["name"] for p in places)
    await graph.emit("rescue", "RESCUE_RESPONSE", f"Auto-dispatch: flood P≥60%. Teams moving to {names}", "go to flood places", {"places": places, "mode": mode})
    await graph.emit("ambulance", "RESCUE_RESPONSE", f"Ambulance auto-called with rescue to {names}", "medical cover on scene", {"places": places, "mode": mode})
    return {"called": True, "band": band, "places": places, "teams": assigned, "mode": mode}
