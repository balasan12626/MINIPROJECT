from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.database import mongo
from backend.utils.geo import jsonable
from backend.websocket.hub import hub


class AgentMemory:
    def __init__(self, name: str) -> None:
        self.name = name
        self.status = "IDLE"
        self.last_event = "initialized"
        self.current_action = "awaiting input"
        self.timestamp = datetime.now(timezone.utc)
        self.state: dict[str, Any] = {}

    def snapshot(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "last_event": self.last_event,
            "current_action": self.current_action,
            "timestamp": self.timestamp,
            "state": self.state,
        }


class AgentGraph:
    """Lightweight stateful orchestration: agents share a graph state and emit events."""

    def __init__(self) -> None:
        self.agents = {
            "weather": AgentMemory("Weather Agent"),
            "dam": AgentMemory("Dam Agent"),
            "flood_risk": AgentMemory("Flood Risk Agent"),
            "traffic": AgentMemory("Traffic Agent"),
            "shelter": AgentMemory("Shelter Agent"),
            "evacuation": AgentMemory("Evacuation Agent"),
            "rescue": AgentMemory("Rescue Agent"),
            "ambulance": AgentMemory("Ambulance Agent"),
            "administrator": AgentMemory("Administrator Agent"),
            "disaster": AgentMemory("Disaster Team Agent"),
            "monitor": AgentMemory("Card Monitor Agent"),
        }
        self.shared: dict[str, Any] = {"mode": "live", "stage": "IDLE"}

    async def emit(self, agent_key: str, event_type: str, message: str, action: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        agent = self.agents[agent_key]
        agent.status = "ACTIVE"
        agent.last_event = message
        agent.current_action = action
        agent.timestamp = datetime.now(timezone.utc)
        if extra:
            extra = jsonable(extra)
            agent.state.update(extra)
        payload = jsonable({
            "agent": agent.name,
            "agent_key": agent_key,
            "event_type": event_type,
            "message": message,
            "action": action,
            "status": agent.status,
            "timestamp": agent.timestamp,
            "extra": extra or {},
            "mode": self.shared.get("mode"),
        })
        await mongo.insert("agent_events", payload)
        await hub.broadcast("agent_update", payload)
        return payload

    def statuses(self) -> list[dict[str, Any]]:
        return [a.snapshot() for a in self.agents.values()]


graph = AgentGraph()
