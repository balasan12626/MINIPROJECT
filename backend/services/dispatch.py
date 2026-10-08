"""Automatic rescue + ambulance call when flood probability ≥ 60%."""

from __future__ import annotations

from typing import Any

from backend.agents.dialogue import risk_band
from backend.agents.graph import graph
from backend.database import mongo
from backend.services.seed import RESCUE_TEAMS, ZONES
from backend.utils.geo import jsonable


def dispatch_permitted(action: str, dispatch_hold: bool, human_override: bool) -> bool:
    """Single rule for whether automatic dispatch may proceed after the decision policy.

    A model-disagreement hold blocks dispatch unless an operator overrides; otherwise
    dispatch needs the policy to have returned AUTOMATED_RESPONSE (all health checks
    passed) or an explicit operator override."""
    if dispatch_hold and not human_override:
        return False
    return action in {"AUTOMATED_RESPONSE", "HUMAN_OVERRIDE"}


async def apply_threshold_dispatch(probability: float | None, mode: str, allowed: bool = True) -> dict[str, Any]:
    """Call rescue + ambulance when P is in the auto band AND the decision policy allowed it.

    ``allowed`` is False when the policy did not return AUTOMATED_RESPONSE (a data,
    model or database health check failed), so a high probability alone can never
    bypass the fail-closed policy."""
    band = risk_band(probability)
    places = [{"name": z["name"], "lat": z["lat"], "lon": z["lon"]} for z in ZONES[:3]]
    teams = await mongo.find_many("rescue_teams", {}, limit=20, sort_field="team_id", direction=1) or [dict(t) for t in RESCUE_TEAMS]

    if band == "auto" and not allowed:
        await graph.emit("administrator", "DECISION_REQUIRED", "Safety gate blocked automation: rescue held for human review", "hold dispatch", {"band": band, "mode": mode})
        return {"called": False, "band": band, "places": [], "teams": [], "mode": mode, "held": True,
                "reason": "Safety gate blocked automation (health check failed)"}

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
