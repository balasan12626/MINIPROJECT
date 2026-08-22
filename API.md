# API

Base URL: `http://localhost:8000`

| Method | Path | Notes |
| --- | --- | --- |
| GET | /api/health | Backend, Mongo, models, WS clients |
| GET | /api/weather/current | OpenWeather / Open-Meteo |
| GET | /api/weather/forecast | Daily forecast |
| GET | /api/rainfall/current | |
| GET | /api/water-level | |
| GET | /api/dam | |
| GET | /api/river | |
| GET | /api/traffic | Roads + blockage |
| GET | /api/shelters | |
| GET | /api/routes | Optional origin/dest query |
| POST | /api/ml/predict | Body rainfall_24h_mm + forecast_daily_mm |
| GET | /api/ml/models | |
| GET | /api/ml/benchmark | |
| GET | /api/risk/current | |
| GET | /api/pipeline/live | Full live snapshot (triggers run if empty) |
| POST | /api/pipeline/refresh | Force live cycle |
| GET | /api/metrics | |
| GET | /api/agents/status | |
| GET | /api/agents/events | |
| GET | /api/policy | |
| POST | /api/policy/review | Approve/reject; audit log |
| GET | /api/incidents | |
| GET | /api/incidents/{id} | |
| POST | /api/optimization/evacuation | |
| POST | /api/optimization/benchmark | |
| GET | /api/simulation/scenarios | |
| POST | /api/simulation/start | |
| POST | /api/simulation/pause | |
| POST | /api/simulation/resume | |
| POST | /api/simulation/reset | |
| GET | /api/simulation/state | Includes simulation pipeline snapshot |
| POST | /api/emergency/sos | Citizen SOS |
| GET | /api/emergency | |
| GET | /api/emergency/{id} | |
| GET | /api/rescue/teams | |
| POST | /api/rescue/assign | |
| PATCH | /api/rescue/{team_id}/status | AVAILABLE…COMPLETED |
| POST | /api/auth/login | JWT |
| WS | /ws | heartbeat / ping / typed events |

WebSocket event types: `weather_update`, `rainfall_update`, `dam_update`, `river_update`, `risk_update`, `agent_update`, `shelter_update`, `route_update`, `optimization_update`, `emergency_update`, `rescue_update`, `system_metrics`, `simulation_event`, `simulation_state`, `heartbeat`, `pong`.
