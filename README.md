# Agentic Real-Time Flood Response and Evacuation Optimization System

Sense → Predict → Reason → Decide → Optimize → Respond.

This repository is a working research prototype: React (Vite) + FastAPI + MongoDB, with an INDOFLOODS-trained flood-severity model, a real agent event graph, decision policy, shelter/route engines, QUBO / QAOA-inspired optimization, WebSocket updates, and a digital-twin simulation that reuses the same pipeline as live mode.

## What is implemented

- **Live Command Center** (`/`): live weather, hydrology, ML flood probability, agents, map, measured latencies.
- **Live Response & Evacuation** (`/response`): incidents, policy (monitor / human review / auto), shelter + route, optimization.
- **Scenario Builder** (`/simulation`): synthetic disaster configuration.
- **Simulation Execution** (`/simulation/run`): time-evolving digital twin using the same downstream pipeline.

Live pages never use a green LIVE badge for simulation data. Simulation pages are labeled **SIMULATION MODE — SYNTHETIC DATA**.

## Quick start

MongoDB must be running at `mongodb://localhost:27017` (or set `MONGODB_URI`). If MongoDB is down, APIs still run and return stored/unavailable states instead of fake KPIs.

```powershell
.\start-backend.ps1
.\start-frontend.ps1
```

Or manually:

```bash
# 1. Python deps
pip install -r backend/requirements.txt

# 2. Train models from dataset/ (already trained artifacts live in models/)
python scripts/train_flood_model.py

# 3. Backend (from repo root)
set PYTHONPATH=.
uvicorn backend.main:app --reload --port 8000

# 4. Frontend
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

Copy `.env.example` to `.env` and fill keys. This workspace `.env` is local-only and is gitignored.

Operator login (RBAC for review actions):

```
POST /api/auth/login?username=operator&password=...
```

## Dataset

INDOFLOODS files in `dataset/`:

- `floodevents_indofloods.csv`
- `precipitation_variables_indofloods.csv`
- `catchment_characteristics_indofloods.csv`

Used **only for training/evaluation**, never as live telemetry.

## Tests

```bash
pytest -q
cd frontend && npm test
```

## Docker

```bash
docker compose up --build
```

## Docs

- [ARCHITECTURE.md](ARCHITECTURE.md)
- [DATA_SOURCES.md](DATA_SOURCES.md)
- [ML_MODEL.md](ML_MODEL.md)
- [AGENT_ARCHITECTURE.md](AGENT_ARCHITECTURE.md)
- [OPTIMIZATION.md](OPTIMIZATION.md)
- [SIMULATION.md](SIMULATION.md)
- [BENCHMARKS.md](BENCHMARKS.md)
- [API.md](API.md)
- [DEPLOYMENT.md](DEPLOYMENT.md)
