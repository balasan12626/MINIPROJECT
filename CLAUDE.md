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
| Person rescue stage machine | `backend/services/person_ops.py` (`STAGES`; stage length = route travel time, per-person `ops_stage_seconds`, demo clock `TIME_SCALE`; `en_route` = driver accepted) |
| Free ambulances / live shelter seats | `person_ops.fleet_board()` / `shelter_allocation_board()` (served in `state()`) |
| Agents, tiers, notifications, playbook | `backend/agents/mas.py` (tiers from `thresholds.ESCALATION_READY/FIELD`) |
| Route choice between candidate roads | `backend/optimization/qaoa_route.py` (called from `person_ops.road_route`) |
| Shelter closures / capacity edits, driver accept mode | `engine.shelter_overrides`, `engine.accept_mode` (served in `state()`) |
| Stored runs, frames, persisted playbook | `backend/services/replay.py` |
| AI Assistant answers | `backend/services/ai_assistant.py` (`POST /api/simulation/ai`) |
| Live rescue view model (derivation only, not a simulator) | `frontend/src/state/rescueOps.js` |
| Default SOS roster | `backend/services/citizens.py` ↔ `frontend/src/data/citizens.js` |
| Shelter / rescue-team coordinates | `backend/services/seed.py` + `rescue_desk.py` ↔ `frontend/src/data/rescueAssets.js` |
| Dam registry and reservoir physics | `backend/data/dams.py`, `backend/services/dam_risk.py` |
| City geography (roads, shelters, depots, zones, gauge) | `backend/data/cities/<id>.json` built by `scripts/build_city_data.py`; loaded / swapped in by `backend/geo/cities.py` (`activate`). `delhi_seed` = the old hand-made network |
| Ambulance positions + dispatch policy | `person_ops.ambulance_positions()` (derived from the stage machine), `DISPATCH_POLICIES`, staging = `plan_staging()` |
| Road "floods in ~N min" | `engine.road_forecast()` (the engine's own closure rule run forward; not a hydraulic model) |
| Peak-level interval / alert set | `models/conformal_v2.json` from `scripts/conformal_v2.py` (attached in `backend/ml/inference.py`) |
| Why-card, fairness board | `person_ops._decision()` → `row["decision"]`, `person_ops.equity_board()` |
| Ops stress test results | `models/ops_montecarlo_v1_<city>.json` from `scripts/monte_carlo_ops.py` (served by `GET /api/benchmark/ops`) |

Frontend files marked `↔` are mirrors of backend data and must be changed together.
`frontend/src/state/rescueOps.test.js` fails if a shelter name cannot resolve to coordinates.

## API contracts that bite

- `POST /api/simulation/run` — passing `scenario` makes the backend **overwrite every other field** with that preset's defaults (`backend/api/dams.py:50-51`). Send raw controls only, otherwise typed inputs are silently discarded.
- `POST /api/simulation/start` — does **not** merge a scenario's defaults server-side. Send the complete parameter set or the run quietly uses different numbers.
- HQRL has **no named scenarios**. A "benchmark scenario" is only a seed offset (`base_seed + i*17`); the real knobs are `(mode, n_scenarios, seed)` plus the 8-field `HqrlConfigBody`.
- `POST /api/simulation/sos` appends one person at `queued` (nearest existing cluster, no re-clustering). `POST /api/simulation/sos/surge` adds 1–100 **synthetic** callers. Both keep everyone's progress.
- `engine.start/pause/reset` must go through `_stop_task()` (cancel **and await**). A bare `task.cancel()` lets the old loop's `CancelledError` handler write `status="paused"` over the next run, which then stops after ~2 ticks.
- Roads (F1): `engine.roads_now()` is the only road list routes may use (seed + flood closures + operator overrides; operator wins). `POST /api/simulation/road {road_id, blocked|clear}` re-plans affected legs via `person_ops.reroute`. With no open road the plan is kept and `route_alert` is raised — never adopt a straight line as a re-route. Re-plan before any `await` (the tick loop interleaves).
- `POST /api/simulation/override` takes `rainfall_mm` / `river_m` / `dam_m` (barrage stage) / `flood_probability`, and `{clear: [...]}` to hand a field back to the scenario.
- `PUT /api/simulation/playbook` is saved to Mongo `settings {_id: "playbook"}` and loaded at startup (F5) — with MongoDB off it is memory-only and the response says `persisted: false`. uvicorn `--reload` still restarts the backend on every backend file save, which wipes the current run.
- Shelters (F2): `POST /api/simulation/shelter {name, closed | capacity | clear}`. Never move `rescued` rows; with no seats anywhere a `to_shelter` row holds (`shelter_wait`) instead of being delivered to a closed shelter.
- Drivers (F3): `accept_mode` "manual" holds `assigned` until `POST /api/simulation/unit/{unit}/accept|reject`; no answer in `ACCEPT_TIMEOUT_SECONDS` = reject. `start()` resets the mode to "auto".
- Public SOS (F4): `POST /api/public/sos` is the ONLY unauthenticated mutating endpoint — keep its rate limits, bbox, magic-byte check and EXIF re-encode. Its status endpoint takes the random ticket only.
- Replay (F5): `engine._record(cause)` after every tick / operator action; frames are compact copies, never the full `state()`. New MAS messages reach Mongo only through `mas.outbox`.
- Route benchmark (F6): `GET /api/benchmark/routes` only reads `models/route_benchmark_v1.json`; regenerate with `python scripts/bench_routes.py`. It shares `person_ops.route_candidates` with the live router — change both or neither. Per city: `--city <id>` → `route_benchmark_v1_<city>.json`.
- Cities (F7): one engine = one active city; `engine.start(params.city)` activates it and swaps the seed lists **in place**. Only Delhi has a real river gauge — every other city is rainfall-driven (no river / barrage term) and the UI must say so. Shelter capacity, crew size and traffic are assumed and labelled; where OSM lacks fire stations, police stations are depots (`kind: "police"`; Guwahati has none mapped). Overpass is often overloaded — re-run the build, the raw cache in `backend/data/cities/raw/` is reused. OSM zones have `population: null` (unknown, never guessed): any arithmetic on zone population must treat null as "no known load" (`solvers._pop`, `shelter_engine.score_shelter`) — before 2026-10-11 this crashed the live loop on tick 1 in every OSM city. City-dependent UI (SOS form region, page eyebrow, voice-agent fallback pin) reads `sim.city` / ScenarioContext `city`, never a Delhi constant.
- Dispatch (F8): `nearest_depot` is the original rule and is **idealised** (it launches from a depot, ignoring where the ambulance is). Compare policies against `first_free`; report `nearest_depot` as "not comparable".
- Public safety (F15): `GET /api/public/safety` is unauthenticated and read-only — keep the bbox check and 30/min limit, store nothing about the caller. `frontend/public/sw.js` caches only the `/sos` + `/safe` shell and `/assets/*`, never `/api`; it registers in production builds only.
- Groq calls via `dialogue.groq_body` force a JSON `response_format`: the prompt must ask for JSON or Groq returns HTTP 400. Keep `grounded()` — it rejects numbers not in the facts.
- `projection.spillway_hours` is a **count of hours spent spilling**, not a countdown. Time-to-overflow is `projection.threshold_crossing_hours`.
- Dam fill % is live-storage based: `(level − dead_storage) / (FRL − dead_storage)`, not `level / FRL`.
- `dam_level` means two different quantities: reservoir elevation (m MSL, ~488 at Bhakra) on the dam side, and Yamuna barrage stage (~199–206) on the evacuation side. Never merge them.

## Does not exist — do not invent

There are no hospitals, phone numbers, boats, or per-person `zone` anywhere in this repo. Unit positions are never stored: `team_paths` is a static from/to segment, and ambulance positions are derived each time by `person_ops.ambulance_positions()`. There is no real ambulance depot list (ambulances are spread round-robin over the city's depots), no real road traffic data, and no river gauge outside Delhi. Backend shelter occupancy is a growth curve unrelated to rescues, so report "delivered this run" separately rather than blending the two. OSM zone `population` is `null` (unknown) in the real cities.

These gaps are filled only by the planned features, and only from the named source: river gauges outside Delhi (F17, CWC), zone population (F19, WorldPop / GHSL), hospitals (F21, OSM, beds `null` unless tagged), boats (F22, an assumed and labelled fleet). Phone numbers stay out of the repo; F24's SMS number comes from `.env` only. Until a feature's "As built" says it landed, treat the item as non-existent.

## Leaflet / live-view performance

- Cache `L.divIcon` instances. Building one inline per render makes react-leaflet call `setIcon()` and rebuild the marker's DOM node on every poll.
- Animate with **one** shared `requestAnimationFrame` loop calling `marker.setLatLng()`. Never `setState` per frame.
- react-leaflet assigns `ref.current` **after** a child component's own effect runs — resolve the marker inside the loop, not in the effect body.
- Never run `map.flyTo()` while a per-frame loop is moving markers; use `setView(..., { animate: false })`. The combination froze the renderer.
- The `/simulation` tree re-renders every 1.2 s while a run is live. Memoise anything expensive.

## Planned work

**`NEW_FEATURES.md` is the roadmap — 37 features: 15 built (F1–F15), 22 planned (F16–F37).** It has a status table, the
"As built" notes of every built feature, a full plan for every planned one (data source, files, API, tests, done
checklist) and the build order. The original long plans of F1–F15 are archived in
`docs/archive/NEW_FEATURES_F1-F15_full_plans_2026-10-11.md` (history only).

- Built: F1 road block → reroute · F2 shelter close → reallocation · F3 driver Accept / Reject · F4 citizen `/sos` ·
  F5 replay + persistent playbook · F6 route benchmark · F7 six real OSM cities · F8 best-overall dispatch · F9
  pre-positioning · F10 road flood-time forecast · F11 conformal interval · F12 Monte-Carlo stress test · F13 Why-card ·
  F14 fairness board · F15 `/safe` + offline `/sos`.
- Planned, in build order: **F16 what-if planner → F36 Playwright browser tests** → F17 CWC river gauges → F18 rainfall
  forecast → F19 real population → F27 Sphere shelter capacity → F30 duplicate SOS → F23 early zone warnings → F21
  hospitals + triage → F29 silent zones → F25 crew shifts → F32 fair-vs-fast curve → F33 sensitivity → F34 hindsight
  regret → F31 family lookup → F24 Indian languages + SMS → F28 supply runs → F26 HAND road risk → F22 boats → F35 AI
  eval → F37 logins + audit log → F20 satellite check.
- Work one feature at a time: read its plan, build backend → API → UI → tests, tick its checklist, write its
  "As built", update the status table and this file's test counts.
- Ask the user before any new dependency the plans name (Playwright F36, raster library F26, password hashing F37,
  SALib F33). The user registers for external tokens themselves (OpenCelliD F29, Groq key F35); put them in `.env`.

## Next session — start here (handoff written 2026-10-11, 00:55)

1. **Stress-test batch.** Check that all six `models/ops_montecarlo_v1_<city>.json` and `models/route_benchmark_v1_<city>.json`
   exist. At handoff only **Delhi** was done (results copied into F12 in `NEW_FEATURES.md`); Mumbai was running, then
   Chennai, Kolkata, Guwahati, Patna (≈ 50 min each). Re-run any missing city with
   `python scripts/monte_carlo_ops.py --city <id>` and `python scripts/bench_routes.py --city <id>`
   (`$env:PYTHONIOENCODING="utf-8"` first), then copy its numbers into F12 the same way as Delhi.
2. **Build F16 (what-if planner).** Load the `agents-ai`, `rescue-ops` and `testing` skills, read the F16 plan and the code
   it names (`scripts/monte_carlo_ops.py`, `person_ops.ambulance_positions`, `engine.ops_ctx`). First step: move the
   simulator core into `backend/services/ops_sim.py` without changing the script's output (`test_monte_carlo.py` must pass).
3. **Then F36 (Playwright browser tests)** — ask the user before installing `@playwright/test`. It automates the
   still-open browser walk-through of F2–F15.
4. **Check it in the browser.** `.venv\Scripts\Activate.ps1`, `./start-backend.ps1`, `./start-frontend.ps1` (backend needs
   ~1 min for the models), open `http://localhost:5173/simulation`, pick a city, press **Run scenario** — a run started only
   through the API (or before a page reload) is not shown by the page. Use a **visible** tab: browser-automation tabs report
   `document.hidden = true` and the live feed pauses on hidden tabs by design ("Status: loading" there is not a bug).
   Offline `/sos` needs a production build (`npx vite build && npx vite preview`); the service worker is off in dev.
5. **Verify before stopping:** `python -m pytest -q` (**199 passing**: 198 at handoff + the F8 inf regression test), `cd frontend && npx vitest run`
   (**100 passing**) and `npx vite build` (only the large-chunk warning). Update these counts when they change.

State at handoff:
- Everything since commit `7d13dac` is **uncommitted and not pushed** (agents, QAOA routing, AI tab, surge, live controls,
  Re-run fix, F1–F15, today's fixes, the F16–F37 plans). Commit / push / deploy only when the user asks.
- 2026-10-11 runtime fixes (found by running Guwahati in the browser): live loop crashed on tick 1 in every OSM city
  (null zone population) — fixed + per-city tick test; SOS form / page eyebrow / voice-agent pin were Delhi-only — now
  follow the run's city; "INDOFLOODS (Indonesia)" text corrected. Details in F7 of `NEW_FEATURES.md`.
- Open decisions for the authors: whether F6 / F12 benchmarks and F11 coverage go into the report / IEEE paper (skills
  only; `verify.py`). F11 is shown as measured: ±210 m interval covers 86.4 % on unseen gauges (target 90 %), 83 % of
  alert sets contain both classes — never round these up.
- Not yet checked by hand: F2–F15 in a visible browser (Guwahati run + all tabs + `/safe` + `/sos` were checked
  2026-10-11 with no console errors), phone checks for F3 / F4 / F15, playbook surviving a backend restart with MongoDB on.
- Dependencies added earlier: `qrcode` (frontend), `Pillow` (listed in `backend/requirements.txt`).
- The machine runs low on memory with servers + the stress test + other apps; dev servers were killed once on
  2026-10-09 — close other apps before a demo.
- The VPS (`209.159.153.35`) runs an old build (`/api/dams`, playbook, AI endpoints 404 there). Redeploy only when asked.
- Demo tips: Agents tab live controls (🆘 50 SOS, Rainfall +50 cm, ⛔ Block busiest road). With most roads flood-closed,
  many legs show "No open road" — correct behaviour; F2 moves those people to a reachable shelter.

## Deployment

- VPS: `209.159.153.35` — UI `:5173`, API `:8000` (see `DEPLOYMENT.md`, `scripts/deploy-vps.sh`, `docker-compose.yml`). It deploys from GitHub `main`, so it only has what was pushed.
- Check it with `curl http://209.159.153.35:8000/api/health`; a new endpoint returning 404 there means the VPS is behind `main`.
- Deploying and pushing are outward-facing — only when the user asks.

## Skills

`simulation-page`, `rescue-ops`, `agents-ai` (MAS / QAOA / AI tab), `digital-twin`, `backend`, `frontend`, `database-api`, `ml-ai`, `testing`, `low-token`, `project-report`, `ieee-paper` — load the matching one before working in that area.

## Commands

```bash
./start-backend.ps1                 # uvicorn on :8000
./start-frontend.ps1                # vite on :5173

cd frontend && npx vitest run       # frontend tests
python -m pytest -q                 # backend tests

python scripts/build_city_data.py --city guwahati      # (re)build one city from OSM (--refresh = re-download)
python scripts/monte_carlo_ops.py --city chennai       # ops stress test, 60 runs → models/ops_montecarlo_v1_chennai.json
python scripts/bench_routes.py --city chennai          # route benchmark → models/route_benchmark_v1_chennai.json

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
- The live app's route QAOA (`qaoa_route.py`) is a classical statevector simulation of QAOA; the benchmark's "QAOA" in `hqrl_demo.py` is a softmax heuristic. Describe each as exactly that.
- Submissions are double-blind: upload `revised/FINEL/SUBMIT_blind_review.pdf` (no names); `camera_ready_with_authors.*` is for after acceptance. 4–6 pages, no Type 3 fonts.
- Every number is checked by `verify.py` against `models/flood_evaluation_v4.json` and the seeded `exp.json`; if `hqrl_demo.py`, the v4 model or thresholds change, rebuild and update the text.
- Keep the IEEE AI-use disclosure in the Acknowledgment. Never use "humanizer"/AI-detector-evasion tools.

## IEEE paper series P1–P5 (state 2026-10-11)

Five 6-page papers live in `.claude/skills/ieee-paper/series/` (one folder each: `paper.tex` + `exp_*.py` + `post_*.py`):

| Key | Folder | Paper |
| --- | --- | --- |
| p1 | `p1_quantum` | Constraint-preserving QAOA with transferable angles (shelter assignment) |
| p2 | `p2_agentic` | Rules decide, LLMs narrate: fail-closed multi-agent flood response, numeric guard |
| p3 | `p3_qagentic` | Runtime assurance for sampling optimizers: exact verifier + MILP-certified escalation |
| p4 | `p4_forecast` | Three-day flood exceedance on CAMELS-IND, gauges unseen in space and time (leakage-controlled) |
| p5 | `p5_merged` | Merged system paper: fail-closed chain forecast → policy → re-planner → narrator |

- Build: `$env:PAPER_MAX_PAGES=6; .venv\Scripts\python.exe .claude\skills\ieee-paper\series\build_series.py p1 p2 p3 p4 p5`
  (default limit is 8 — always set 6). Must end with `REFERENCES OK` and `ALL CHECKS PASSED`.
  Work dir `%TEMP%\aquasentinel-series\<key>`; output `iee papper fineal/series/<PaperN_...>/`.
- Numbers: never typed into `paper.tex`. `post_<key>.py` writes `nums.tex` from the experiment JSON and `assert`s every
  comparison the text makes. P5's `post_p5.py` re-runs post_p1..p4 and copies their macros with prefixes
  `Fc` (P4), `Qa` (P1), `Ra` (P3), `Ag` (P2); `fill_bib.py` rebuilds P5's bibliography from P1–P4 in first-citation order
  (re-run it after changing any `\cite` in P5).
- Deliverables: `iee papper fineal/10OCT/P{1..5}_*/` (`P#_SUBMIT_blind_review.pdf/.tex`, `P#_camera_ready_with_authors.pdf/.tex`,
  `nums.tex`, figures) and the five with-author PDFs in `iee papper fineal/10OCT/11 OCT/`. Copy new builds there by hand.
- **P5 reuses P1–P4 results: submit P5 OR the separate papers, never both, and never overlapping papers to one venue.**
- Writing: plain academic English, no AI tell words, no em dashes in prose; style stats with `scripts/style.py <pdf>`
  (P5: 0 tell words, burstiness 0.84). No AI-detector or plagiarism % can be measured here — never claim one.
- Pitfalls: Bash heredocs collapse `\\` (a `\t` became a TAB in `\textsc`) — write LaTeX-touching Python with the Write tool
  or `chr(92)`; `audit_refs.py` only sees `\ref` written in `paper.tex`, not inside generated macros; HiGHS status 1 = time
  limit, not infeasible (P3 time-outs all had valid plans); matplotlib needs `pdf.fonttype 42` to avoid Type 3 fonts.
- Long experiments (P2 live LLM calls need author approval; P3 MILP re-runs) go in background runs, not blocking waits.
