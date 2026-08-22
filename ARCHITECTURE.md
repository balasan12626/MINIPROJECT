# Architecture

```
FRONTEND (React + Vite)
        REST + WebSocket
FASTAPI BACKEND
   LIVE DATA MODE | SIMULATION MODE
        DATA NORMALIZATION
        FEATURE ENGINE (INDOFLOODS T1d–T10d analogue)
        ML PREDICTION
        FLOOD RISK ENGINE
        AGENT GRAPH (shared state + Mongo events)
        DECISION POLICY
        SHELTER ENGINE
        ROUTE ENGINE (Yen/Dijkstra on Delhi graph)
        OPTIMIZATION (greedy / Dijkstra / SA / QAOA-inspired QUBO)
        WEBSOCKET → UI
```

Only the **data provider** changes between live and simulation. `backend/services/pipeline.py::run_pipeline(mode, observations)` is the shared path.

Snapshots are stored separately (`live` vs `simulation`) so the Command Center cannot display synthetic ticks as live intelligence.

## Layout

- `frontend/` — four screens, Leaflet map, Recharts, WebSocket client with reconnect + heartbeat.
- `backend/` — FastAPI app described in the project spec.
- `dataset/` — INDOFLOODS CSVs.
- `models/` — trained `random_forest_flood.pkl`, `xgboost_flood.pkl`, `evaluation.json`, `model_metadata.json`.
- `scripts/train_flood_model.py` — reproducible training.

## Decision policy

Configurable via `.env`:

- `FLOOD_MONITOR_THRESHOLD` (default 0.50)
- `FLOOD_AUTO_THRESHOLD` (default 0.60)
- `AUTOMATION_ENABLED`
- `HUMAN_OVERRIDE_ENABLED`

Automation also requires data-quality, model, and MongoDB system gates. These thresholds are **project policy settings**, not scientific constants.
