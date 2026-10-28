---
name: agents-ai
description: Use when working on the multi-agent system (tiers, notifications, playbook, sudden-rise / SOS-surge alerts), the QAOA route choice, the live "sudden change" controls, or the AI Assistant tab on /simulation.
---

# Agents, QAOA routing and the AI Assistant

All three read the **one** simulation state (`engine.state()`); none of them
keeps a second copy of the operation.

## Multi-agent system — `backend/agents/mas.py`

- Rule-based, not learned. 10 agents (`AGENTS`): manager, administrator,
  probability, flood, dam, ambulance, rescue, shelter, route, notify.
- `engine.state()` calls `self.mas.update(...)` every poll and returns its view
  as `state["multi_agent"]` (tier, agents with observation/action, messages
  newest-first capped at 200, severity counts, notified units, playbook).
- Tiers come from `backend/thresholds.py`: `< ESCALATION_READY (0.50)` →
  ADMIN handover, `≥ 0.50` → READY (be ready, notify ambulance + shelter),
  `≥ ESCALATION_FIELD (0.75)` → FIELD (all on field). These are **separate**
  from `auto_threshold` (0.6, auto-dispatch) — do not merge them; the paper
  and report quote 0.6.
- Every message carries `severity` green / yellow / red and a dedupe `key`.
  `_say` drops repeats by key — give any new message a stable key or it will
  spam every 1.2 s poll. Episode flags (e.g. `amb_full`) stop
  "Ambulances all busy" repeating; it re-arms after "Ambulance available".
- Sudden rise: `_sudden` (probability jump ≥ `sudden_rise_points`, rain jump
  ≥ `sudden_rain_mm`, change-monitor up-alerts) and `announce_surge` (called
  explicitly by `add_sos_surge`; count-jump detection could not tell the
  first roster from a surge).
- Playbook (`DEFAULT_PLAYBOOK`, `GET/PUT /api/simulation/playbook`,
  `{reset: true}`) is saved to Mongo `settings` and reloaded at startup
  (`services/replay.py`, `mas.load_playbook`); memory-only when MongoDB is off.
  Triggers: ADMIN, READY, FIELD, SUDDEN, ROAD_BLOCKED, SHELTER_CLOSED.
- Every `_say` also lands in `mas.outbox`; the engine drains it into
  `mas_messages` once per tick / operator action (replay, F5).
- Shelter changes (F2): `announce_shelter_change`. Driver answers (F3):
  "Driver rejected" / "No answer → reassigned" from `row["rejections"]`.

## Live "sudden change" controls

`POST /api/simulation/override` with `rainfall_mm`, `river_m`, `dam_m`
(Yamuna barrage stage, ~199–206 m — **not** reservoir elevation) or
`flood_probability`; `{clear: [...]}` hands a field back to the scenario.
UI: `components/agents/LiveControls.jsx`. Rainfall cards show cm, the API
takes mm.

## Roads and live re-routing (F1)

- `engine.roads_now()` / `road_status()` / `set_road()`; `person_ops.reroute()`, `position_on()`, `route_hits()`.
- Every route dict carries `road_ids`; `no_open_road: true` marks a straight-line estimate (never a real route).
- MAS `announce_road()` posts kind `road` (yellow, pops up), per-unit "Rerouted", red "No open road", and the
  `ROAD_BLOCKED` playbook. Keys include `road_events` so repeated blocks of one road each announce.

## QAOA route choice — `backend/optimization/qaoa_route.py`

- Candidates: Yen k-shortest paths (≤ 4) in `person_ops.road_route()`.
- One-hot QUBO, cost = travel/max + 0.5·hazard rescaled to [0, 1],
  `PENALTY 2`, `LAYERS 3`, 512 shots, COBYLA after a grid search; exact
  classical statevector simulation in numpy, `lru_cache`d.
- Report it as "QAOA simulated classically". **No quantum speed-up claim.**
  `route.quantum.matches_exhaustive` / `agrees_with_dijkstra` are the honest
  checks — show them, don't hide a mismatch.
- `hqrl_demo.py`'s internal "QAOA" is a softmax heuristic (paper code) — do
  not describe it as real QAOA.

## AI Assistant — `backend/services/ai_assistant.py`

- `retrieve()` builds facts + cards from live state (people, dams, shelters,
  ZONES, "ambulance unit N", pronoun follow-ups from history).
- `_llm()` uses Groq via `dialogue.groq_body` — that forces JSON
  `response_format`, so the prompt **must** ask for JSON (`{"answer": ...}`)
  or Groq returns HTTP 400.
- `dialogue.grounded()` rejects any number not present in the facts; then the
  rule-based fact text is returned (`source: "rules"`). Never loosen this to
  make answers "look better".
- Unknown person in every part → no LLM call, plain "could not find" reply.
- Idle state (no run) → summary says so; never print `None%`.

## Frontend

| File | Role |
| --- | --- |
| `components/agents/AgentsPanel.jsx` | Tier gauge, network, message board, agent cards, rainfall ramp demo |
| `components/agents/NotificationCenter.jsx` | Portal bell + drawer; toasts only for red / headline kinds by default |
| `components/agents/PlaybookEditor.jsx` | Edit what each agent does per tier / sudden rise |
| `components/agents/LiveControls.jsx` | 50 SOS, rainfall ±, barrage ±, per-field set/clear |
| `components/agents/AiAssistant.jsx` | Chat, suggestion chips (real names), cards, person PDF |
| `components/rescue/QuantumRoutePanel.jsx` | QAOA probabilities, candidates, circuit |

## Checks

```bash
python -m pytest -q backend/tests/test_mas_qaoa.py backend/tests/test_ai_assistant.py backend/tests/test_engine_restart.py backend/tests/test_reroute.py
cd frontend && npx vitest run src/components/agents
```
