# Agent architecture

Agents are a lightweight stateful graph (`backend/agents/graph.py`), not decorative timers.

Each agent has memory: status, last event, current action, timestamp, extra state. Every `emit()` writes `agent_events` in MongoDB and broadcasts `agent_update` on the WebSocket hub.

## Nodes

| Agent | Input | Output event |
| --- | --- | --- |
| Weather | live/sim weather | `WEATHER_UPDATE` |
| Dam | river/dam observations | `DAM_UPDATE` |
| Flood Risk | ML probability | `FLOOD_RISK_UPDATE`, `DECISION_REQUIRED` |
| Traffic | road flood exposure vs probability | blocked-road set |
| Shelter | capacity, risk, distance | `SHELTER_SEARCH` |
| Evacuation | policy + routes + QUBO assignment | `ROUTE_OPTIMIZATION`, `EVACUATION_PLAN` |
| Rescue | SOS / auto response | `RESCUE_RESPONSE` / `SOS` |

Flow implemented in `run_pipeline`:

```
WEATHER_UPDATE → DAM_UPDATE → FLOOD_RISK_UPDATE → DECISION_REQUIRED
 → HUMAN_REVIEW or AUTOMATED_RESPONSE or MONITOR
 → SHELTER_SEARCH → ROUTE_OPTIMIZATION → EVACUATION_PLAN → RESCUE_RESPONSE
```

Human approve/reject calls `POST /api/policy/review` and is audit-logged (`user`, `timestamp`, `decision`, `reason`).
