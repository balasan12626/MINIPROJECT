# AI Development Workflow

## Agent roles

- Claude Code = primary coding and reasoning agent.
- GitHub Copilot = secondary assistant for small boilerplate and local edits.

Claude Code handles architecture, multi-file changes, backend logic, frontend architecture, API integration, database logic, ML/AI work, simulation work, debugging, testing strategy, and project-level decisions.

GitHub Copilot should be used mainly for autocomplete, repetitive code, imports, simple functions, and small syntax help.

## Low-token / low-context rules

- Read only the files required for the current task.
- Prefer targeted search over broad repo exploration.
- Avoid unrelated directories, logs, caches, generated files, datasets, model weights, and virtual environments unless explicitly required.
- Do not scan the whole repository unless asked.
- Make the smallest correct change.
- Reuse existing code before creating new code.
- Avoid unnecessary dependencies and refactors.
- Do not run the full suite unless needed.
- Prefer focused verification.

## Task workflow

1. Understand the request.
2. Locate the smallest relevant files.
3. Inspect only those files.
4. Fix the root cause.
5. Run the smallest relevant check.
6. Report concise results.

## Safety

- Do not delete important project files without permission.
- Do not revert unrelated user changes.
- Do not force-push.
- Do not modify unrelated files.
- Do not inspect or edit datasets/model weights unless required.

## ML safety

- No target leakage; no fabricated metrics, predictions, probabilities, or confidence values.
- No test-set tuning.
- No random row split when group/time leakage exists — use group/time-aware validation.
- Preserve V1 models/artifacts; new versions are additive (v2 naming), never overwrite V1.
- V2 must be genuinely wired into production code paths, not just present on disk.
- XAI must explain the model that actually produced the displayed prediction (v1 XAI for v1, v2 XAI for v2).

## Frontend

- UI must be driven by backend/application state — no hard-coded operational metrics or fake dashboard numbers.
- No static simulation results presented as if live.
- Reuse existing components; keep components modular; do not rewrite unrelated pages.

## Digital Twin

- Simulation state has one authoritative source; every displayed value must trace to current simulation state.
- Map, flood level, risk, route, shelters, population, and alerts update consistently together.
- Avoid disconnected duplicate state.

## Route

- Routes are calculated from actual current simulation state (real graph/algorithm), never decorative or random.
- Do not claim shortest/safest route unless the algorithm actually computed it.
- Recalculate routes when relevant conditions (blockage, shelter capacity) change.

## Stack summary

- Frontend: React + Vite
- Backend: FastAPI + Python services
- Database: MongoDB via Motor/PyMongo
- ML/AI: scikit-learn, xgboost, inference/evaluation pipeline
- Digital Twin: simulation engine + scenario pipeline
- Testing: pytest for backend; Vitest for frontend

## Canonical sources

One owner per concern. If a displayed value is wrong, fix it at the owner — never patch the component that renders it.

| Concern | Owner |
| --- | --- |
| Risk / model thresholds | `backend/thresholds.py` (served by `GET /api/config/thresholds`) |
| Scenario catalogue | `frontend/src/config/scenarios.js` |
| `/simulation` page state + the single run flow | `frontend/src/state/ScenarioContext.jsx` |
| Person rescue stage machine | `backend/services/person_ops.py` (`STAGES`; stage length = route travel time, per-person `ops_stage_seconds`, demo clock `TIME_SCALE`) |
| Live rescue view model (derivation only, not a simulator) | `frontend/src/state/rescueOps.js` |
| Default SOS roster | `backend/services/citizens.py` ↔ `frontend/src/data/citizens.js` |
| Shelter / rescue-team coordinates | `backend/services/seed.py` + `rescue_desk.py` ↔ `frontend/src/data/rescueAssets.js` |
| Dam registry and reservoir physics | `backend/data/dams.py`, `backend/services/dam_risk.py` |

Frontend files marked `↔` are mirrors of backend data and must be changed together.
`frontend/src/state/rescueOps.test.js` fails if a shelter name cannot resolve to coordinates.

## API contracts that bite

- `POST /api/simulation/run` — passing `scenario` makes the backend **overwrite every other field** with that preset's defaults (`backend/api/dams.py:50-51`). Send raw controls only, otherwise typed inputs are silently discarded.
- `POST /api/simulation/start` — does **not** merge a scenario's defaults server-side. Send the complete parameter set or the run quietly uses different numbers.
- HQRL has **no named scenarios**. A "benchmark scenario" is only a seed offset (`base_seed + i*17`); the real knobs are `(mode, n_scenarios, seed)` plus the 8-field `HqrlConfigBody`.
- `POST /api/simulation/sos` is broken three ways: its schema has no `age`, the new person fails the clustering status filter, and it rebuilds `contact_log` from scratch — wiping everyone already past `assigned`. Do not wire it without fixing it.
- `SimulationEngine.resume()` re-runs `_ingest_citizens()` and destroys all per-person progress. Do not expose a backend resume.
- `projection.spillway_hours` is a **count of hours spent spilling**, not a countdown. Time-to-overflow is `projection.threshold_crossing_hours`.
- Dam fill % is live-storage based: `(level − dead_storage) / (FRL − dead_storage)`, not `level / FRL`.
- `dam_level` means two different quantities: reservoir elevation (m MSL, ~488 at Bhakra) on the dam side, and Yamuna barrage stage (~199–206) on the evacuation side. Never merge them.

## Does not exist — do not invent

There are no hospitals, phone numbers, boats, or per-person `zone` anywhere in this repo. Unit positions are never stored: `team_paths` is a static from/to segment. Backend shelter occupancy is a growth curve unrelated to rescues, so report "delivered this run" separately rather than blending the two.

## Leaflet / live-view performance

- Cache `L.divIcon` instances. Building one inline per render makes react-leaflet call `setIcon()` and rebuild the marker's DOM node on every poll.
- Animate with **one** shared `requestAnimationFrame` loop calling `marker.setLatLng()`. Never `setState` per frame.
- react-leaflet assigns `ref.current` **after** a child component's own effect runs — resolve the marker inside the loop, not in the effect body.
- Never run `map.flyTo()` while a per-frame loop is moving markers; use `setView(..., { animate: false })`. The combination froze the renderer.
- The `/simulation` tree re-renders every 1.2 s while a run is live. Memoise anything expensive.

## Commands

```bash
./start-backend.ps1                 # uvicorn on :8000
./start-frontend.ps1                # vite on :5173

cd frontend && npx vitest run       # frontend tests
python -m pytest -q                 # backend tests

.\.claude\skills\project-report\scripts\make_report.ps1               # rebuild project report (.docx + .pdf)
.\.claude\skills\project-report\scripts\make_report.ps1 -Screenshots  # + recapture UI screenshots

.\.claude\skills\ieee-paper\scripts\make_paper.ps1                    # rebuild IEEE paper (PDF + Word, blind + camera)
.\.claude\skills\ieee-paper\scripts\make_paper.ps1 -SkipExp           # text-only edit, reuse experiment results
```

## Project report

- Use the `project-report` skill for any change to the final-year report. Do not hand-edit `MINI PROIOJECTT  REPOT FINEL/AquaSentinel_Project_Report.docx` — it is regenerated and edits are overwritten.
- Content and personal details (students, register numbers, supervisor, HOD, designations) live in `.claude/skills/project-report/scripts/content.py`.
- Layout comes only from `SAMPLE PROJECT REPORT FORMAT & INSTRUCTIONS.docx`; never modify the sample.
- Report numbers must come from `models/*.json`, seeded runs or real test runs, and stay in step with the code — if a model, threshold or test count changes, update `content.py` and rebuild.

## IEEE paper

- Use the `ieee-paper` skill for any change to the conference paper. Edit only `.claude/skills/ieee-paper/scripts/paper.tex` (tables are mirrored in `build_paper_docx.js` — change both); never hand-edit the generated files in `iee papper fineal/revised/`.
- The first version (INDICON 2026, paper 4244) was rejected for limited novelty, IEEE non-compliance and clarity. Do not reintroduce its mistakes: no example/placeholder numbers, no claims of trained PPO, real QAOA or SHAP for routes, no quantum speed-up.
- Submissions are double-blind: upload `revised/FINEL/SUBMIT_blind_review.pdf` (no names); `camera_ready_with_authors.*` is for after acceptance. 4–6 pages, no Type 3 fonts.
- Every number is checked by `verify.py` against `models/flood_evaluation_v4.json` and the seeded `exp.json`; if `hqrl_demo.py`, the v4 model or thresholds change, rebuild and update the text.
- Keep the IEEE AI-use disclosure in the Acknowledgment. Never use "humanizer"/AI-detector-evasion tools.
