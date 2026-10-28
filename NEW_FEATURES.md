# NEW_FEATURES.md — feature roadmap (implementation guide)

How to use this file:
- **F1–F15 are built.** Each keeps only its **"As built"** notes (what the code really does) and any checklist item still
  open. The original step-by-step plans for F1–F15 are archived in
  `docs/archive/NEW_FEATURES_F1-F15_full_plans_2026-10-11.md` — read them only for history.
- **F16–F37 are planned (F16–F25 and F26–F37 both picked 2026-10-11).** Each has goal, data source, files, API, tests
  and a done checklist. Work them in the build order below, tick the checklist as items land, and add an "As built"
  note when one is done.

**Count: 37 features — 15 built (F1–F15), 22 planned (F16–F37).**

## Status

| # | Feature | Status | Open items |
|---|---|---|---|
| F1 | Block a road → live reroute | ✅ done 2026-10-08 | — |
| F2 | Close / shrink a shelter → reallocation | ✅ built 2026-10-09 | browser check |
| F3 | Driver app Accept / Reject (`/driver/:unit`) | ✅ built 2026-10-09 | phone-width check |
| F4 | Citizen SOS phone page (`/sos`) | ✅ built 2026-10-09 | phone check |
| F5 | Replay past runs + persistent playbook | ✅ built 2026-10-09 | browser check, playbook after restart |
| F6 | Measured route-choice benchmark | ✅ built 2026-10-09 | report / paper decision |
| F7 | Six cities on real OSM road networks | ✅ built 2026-10-09, fixed 2026-10-11 | browser check per city |
| F8 | Best overall dispatch + derived ambulance positions | ✅ built 2026-10-09 | — |
| F9 | Pre-position idle ambulances | ✅ built 2026-10-09 | — |
| F10 | Road flood-time forecast | ✅ built 2026-10-09 | — |
| F11 | Measured uncertainty (conformal) | ✅ built 2026-10-09 | report / paper decision |
| F12 | Monte-Carlo ops stress test | ✅ built 2026-10-09 | Delhi measured; 5 cities' result files pending |
| F13 | "Why this decision?" card | ✅ built 2026-10-09 | — |
| F14 | Fairness dashboard | ✅ built 2026-10-09 | — |
| F15 | `/safe` page + offline SOS | ✅ built 2026-10-11 | real phone in airplane mode |
| F16 | What-if planner on the live run | ✅ built 2026-10-11 | browser click-through |
| F17 | Real river gauges for the other 5 cities | ✅ built 2026-10-11 | browser check Guwahati / Patna |
| F18 | Live rainfall forecast per city | ✅ built 2026-10-11 | browser check |
| F19 | Real population per zone | ✅ built 2026-10-11 | browser check |
| F20 | Check road closures against satellite flood maps | ✅ built 2026-10-11 | — |
| F21 | Hospitals + medical triage | ✅ built 2026-10-11 | browser + phone check |
| F22 | Boats for cut-off people | ✅ built 2026-10-11 | browser check |
| F23 | Early evacuation warnings per zone | ✅ built 2026-10-11 | sweep files per city (background); browser check |
| F24 | SOS in Indian languages + SMS fallback | ✅ built 2026-10-11 | native review of hi/ta/bn/as; phone check |
| F25 | Ambulance crews over a long operation | ✅ built 2026-10-11 | long-run files (background); browser check |
| F26 | Height-based road flood risk (HAND from elevation data) | 📋 planned | |
| F27 | Shelter capacity from building size (Sphere standard) | ✅ built 2026-10-11 | browser check |
| F28 | Food, water and medicine supply runs to shelters | ✅ built 2026-10-11 | browser check |
| F29 | Silent zones — phone towers lost to the flood | ✅ built 2026-10-11 | needs OPENCELLID_TOKEN + build_towers run; browser check |
| F30 | Duplicate SOS detection and merge | ✅ built 2026-10-11 | browser check |
| F31 | Family reunification lookup (ticket only) | ✅ built 2026-10-11 | phone check |
| F32 | Fair vs fast dispatch — measured trade-off curve | ✅ built 2026-10-11 | fairness files (background); paper decision |
| F33 | Which assumptions matter — sensitivity analysis | ✅ built 2026-10-11 | sensitivity files (background); paper decision |
| F34 | Hindsight check of past runs (regret) | ✅ built 2026-10-11 | paper decision |
| F35 | AI Assistant accuracy evaluation | 📋 planned | |
| F36 | Automatic browser tests (Playwright) | 📋 planned | |
| F37 | Login, roles and action history | 📋 planned | |

## Rules that apply to every feature (from CLAUDE.md)

- One authoritative state: everything lives on `SimulationEngine` (`backend/simulation/engine.py`) and is served by
  `engine.state()`; the live feed (`frontend/src/pages/SimulationExecution/simStore.js`) is the only poller. New UI reads
  `state`, never keeps its own copy.
- `backend/services/person_ops.py` is the only stage machine. Do not add a second simulator — the F12 stress test and
  the F16 planner drive the same `person_ops` code on a virtual clock.
- Routes come from the real graph (`person_ops.route_candidates` → QAOA / Dijkstra choice). Never draw a decorative route.
- **No fabricated numbers.** Real data names its source; anything assumed is a labelled parameter (`*_source: "assumed"`),
  shown in the UI, and swept in the stress test so a result never rests on one invented value. Synthetic people / trips
  are labelled synthetic.
- **Hospitals and boats do not exist until F21 / F22 add them** — and then only hospitals mapped in OSM, and boats as a
  labelled assumed fleet. There are still **no phone numbers** in the repo; F24's SMS number comes from configuration only.
- OSM zone `population` is `null` unless F19 fills it from a named source — never a guess; arithmetic treats null as
  "no known load".
- Mutating endpoints use `RequireOperator` (`backend/deps/auth.py`) + a `limiter.limit(...)`. Public endpoints
  (`/api/public/*`) keep bbox checks and rate limits and store nothing they do not need.
- Long computations (stress test, planner, data builds) never run inside a normal request: scripts, or a background job
  with a job id that the UI polls.
- New ML / data artefacts are additive (`*_v1.json`, `*_v2`), never overwrite an older one.
- `uvicorn --reload` restarts the backend on every save and wipes the run — re-run the scenario after backend edits.
- New MAS messages need a stable `key` (`MultiAgentSystem._say` dedupes by key) or they repeat every poll.
- Browser automation tabs report `document.hidden = true`; the live feed pauses on hidden tabs by design.
- After each feature: `python -m pytest -q` and `cd frontend && npx vitest run && npx vite build`, then click it through
  in a visible browser tab.

---

# Built — F1–F15 (as built)

## F1 — Block a road → live reroute  ✅ DONE 2026-10-08
- `engine.roads_now()` is the one road list for the run = seed `ROADS` + `auto_blocked` (flood rules, grow-only per run)
  + `road_overrides` (operator wins). `start()` re-syncs Mongo `roads` to the seed — closures used to leak between runs.
- `person_ops.road_route` returns `road_ids`; when the nearest junction is cut off it tries the 3 nearest junctions at
  each end. A disconnected trip returns `method: "direct", no_open_road: true`.
- `person_ops.reroute(rows, roads, reason, improve=False)` + `position_on` + `leg_progress`. **No open road → the plan is
  kept and `route_alert` is set (red "No open road"); a straight line is never adopted as a re-route.** Reopen
  (`improve=True`) re-plans alert legs and any leg ≥ 0.5 min faster.
- Operator re-plan runs **before any await** in `set_road`. The loop re-plans only on NEW flood closures.
- API: `GET /api/simulation/roads`, `POST /api/simulation/road {road_id, blocked | clear}`; state has `road_status`,
  `road_log`. MAS `announce_road`, playbook trigger `ROAD_BLOCKED`.
- UI: `RoadControlPanel.jsx`, clickable roads in `LiveRescueMap.jsx`, "⛔ Block busiest road" in `LiveControls.jsx`,
  re-route chips in `RouteCasesPanel.jsx`. Tests: `test_reroute.py`, `RoadControlPanel.test.jsx`.

## F2 — Close / shrink a shelter → reallocation  ✅ BUILT 2026-10-09
- `engine.shelter_overrides {name: {closed, capacity}}` + `shelter_log`; `engine.set_shelter()` re-plans before any
  await; `engine.ops_ctx()` is the one ctx for every stage-machine call.
- `person_ops.shelter_registry(overrides)`, `_reachable_shelter()` (nearest open shelter with seats AND an open road),
  `reallocate()`: closed → over capacity (newest first) → unreachable → `shelter_wait`. No seats anywhere → the row holds
  with `ops_wait_reason`. `rescued` rows never move. Road closures also call `_reallocate`.
- API `POST /api/simulation/shelter {name, closed?, capacity?, clear?}`; MAS `announce_shelter_change`, `SHELTER_CLOSED`.
- UI: `ShelterCapacityPanel` Edit → Close / Reopen / Set capacity / Reset. Tests: `test_reallocate.py`,
  `ShelterCapacityPanel.test.jsx`.
- ☐ Clicked through in the browser.

## F3 — Driver app: Accept / Reject  ✅ BUILT 2026-10-09
- `engine.accept_mode` ("auto" | "manual", reset to auto by `start()`); `person_ops.ACCEPT_TIMEOUT_SECONDS = 20`;
  no answer = `reject(..., "no answer")`; `reject()` re-assigns at once, skipping rejected units.
- API: `POST /api/simulation/accept-mode {mode}`, `GET /api/simulation/unit/{unit}`, `POST .../accept`,
  `POST .../reject {reason}` (409 when no request is waiting).
- UI: `/driver/:unit` (lazy, 2 s poll, countdown from backend `seconds_left`); Auto-accept / Drivers decide toggle and
  "Open driver view ↗" in `FleetPanel`. Tests: `test_driver_accept.py`, `DriverApp.test.jsx`.
- ☐ Checked on a phone (360 px width).

## F4 — Citizen SOS phone page  ✅ BUILT 2026-10-09
- `backend/api/public_sos.py`: `POST /api/public/sos` (multipart; 5/min per IP + 10 per IP per run; 409 no run; 422
  outside bbox; 415 bad magic bytes; 413 > 3 MB), `GET /api/public/sos/{ticket}` (ticket only),
  `GET /api/simulation/photo/{ticket}` (operator). Photos re-encoded by Pillow (EXIF dropped, ≤ 1600 px) to
  `uploads/sos/{run_id}/{ticket}.jpg` (git-ignored).
- UI: `/sos` form + GPS + photo + status screen (ticket in `localStorage`); 📱 badge + photo in People / AI card; QR card
  on the Live tab. HTTPS note in `DEPLOYMENT.md` (GPS needs https). Tests: `test_public_sos.py`, `CitizenSos.test.jsx`.
- Note: vite listens on 127.0.0.1, so a phone on the LAN needs `--host`.
- ☐ Real phone → SOS → joins the run.

## F5 — Replay past runs + persistent playbook  ✅ BUILT 2026-10-09
- `backend/services/replay.py` (`ReplayStore`): `record(engine, cause)` writes compact frames (`simulation_frames`),
  drains `mas.outbox` into `mas_messages`, upserts `simulation_runs`. Mongo down → last run only (400 frames), `persisted: false`.
- Playbook: `PUT /api/simulation/playbook` → `settings {_id: "playbook"}`, loaded at startup. Retention: newest 50 runs.
- API: `GET /api/simulation/runs`, `/runs/{id}`, `/runs/{id}/frames`, `/runs/{id}/messages`, `/runs/{id}/report.pdf`.
- UI: 📼 History → `ReplayPlayer.jsx` (▶/⏸, slider, 1×/4×/16×), `state/replay.js frameToView()` feeds the existing
  components; purple "REPLAY — not live" banner. Road lines are not replayed. Tests: `test_replay.py`, `replay.test.js`,
  `ReplayPlayer.test.jsx`.
- ☐ Restart the backend with MongoDB on and confirm the playbook stayed. ☐ Replay clicked through.

## F6 — Measured route-choice benchmark  ✅ BUILT 2026-10-09
- `person_ops.route_candidates()` is shared by the live router and `scripts/bench_routes.py` →
  `models/route_benchmark_v1.json` (+ `.timing.json`); per city `--city <id>` → `route_benchmark_v1_<city>.json`.
  `GET /api/benchmark/routes`, `RouteBenchmarkCard.jsx` on the Algorithms tab. Tests: `test_bench_routes.py`.
- **Measured (200 synthetic trips, seed 42, `delhi_seed` graph):** at most 2 candidates per trip, only at 0 % blockage
  (165 of 195 routed trips); QAOA = exhaustive on 100 %, = Dijkstra on 99.39 %. From 10 % blockage every trip has one
  candidate; at 30 %, 87 of 200 trips have no open road.
- ☐ Report / IEEE paper: authors' decision (honest result, but it does not support a novelty claim).

## F7 — Six cities on real road networks  ✅ BUILT 2026-10-09 (Guwahati rebuilt + runtime fixes 2026-10-11)
- `backend/data/cities/{delhi,mumbai,chennai,kolkata,guwahati,patna}.json` from `scripts/build_city_data.py`
  (Overpass cache in `backend/data/cities/raw/`; `--refresh` downloads again). The hand-made network stays as `delhi_seed`.
- **Data rule — nothing invented:** roads, fire stations (depots), candidate shelters, suburbs (zones) and water come
  from OpenStreetMap (ODbL, attributed). Road `flood_exposure` is a distance-to-water proxy (bridges capped). Shelter
  capacity, crew size and traffic are assumed and labelled. Population: OSM tag only, else `null`.
- Depots: fewer than 3 fire stations mapped → OSM police stations fill in (`kind: "police"`). Patna: 1 fire station +
  police; Guwahati: no fire station in OSM, all 6 depots police (one is a police oversight office — kept as mapped).
- Only Delhi has a real INDOFLOODS gauge (Yamuna, danger 205.33 m); the other five are rainfall-driven (→ F17).
- Runtime: `backend/geo/cities.py` (`list_cities / load_city / activate`); `engine.start(params.city)` swaps the seed
  lists in place. API `GET /api/cities`, `GET /api/cities/{id}`. UI: `CityPicker` on Setup, `useCityView` for the map.
- Fixes 2026-10-11: (1) the live loop crashed on tick 1 in every OSM city (`None - int` on zone population in
  `shelter_engine.score_shelter` / `solvers`) — null now means "no known load" (`solvers._pop`), regression test
  `test_one_engine_tick_runs_in_every_city`; (2) SOS form region, page eyebrow and voice-agent fallback pin now follow
  the run's city; (3) "INDOFLOODS (Indonesia)" text corrected to Indian river gauges; (4) build script's "→" print
  crashed on a cp1252 console → "->".
- Tests: `test_cities.py` (schema, labelled assumptions, activate and back, routes per city, rainfall city, roster,
  one engine tick per city).
- ☐ Clicked through in a visible browser for every city (Guwahati done 2026-10-11).

## F8 — Best overall dispatch + ambulance positions  ✅ BUILT 2026-10-09
- Positions are **derived, never stored**: `person_ops.ambulance_positions(rows, ctx, now)` reads them off the stage
  machine (home depot round-robin → last drop-off shelter → interpolated along a staging move).
- `DISPATCH_POLICIES = ("nearest_depot", "first_free", "greedy", "optimal")`. `nearest_depot` = original rule,
  **idealised** (launches from a depot) — report it as "not comparable"; `first_free` is the fair baseline; `optimal` =
  `scipy.optimize.linear_sum_assignment`, cost = road minutes × `VULN_WEIGHT` (child / elderly 1.6, chest-deep 1.3).
- Tests: `test_dispatch_policy.py`.
- Fix 2026-10-11: a person with no open road has road time `inf`; it leaked into `row["decision"]` and made
  `GET /api/simulation/state` return HTTP 500 for the whole run (the UI default policy is `optimal`). Non-finite minutes
  are now `None` ("no open road"). Regression: `test_optimal_dispatch_unreachable_person_is_json_safe`.

## F9 — Pre-position idle ambulances  ✅ BUILT 2026-10-09
- `person_ops.staging_points` (greedy weighted k-median over junctions, ≤ 6) + `plan_staging`; weight = exposure proxy ×
  flood probability × (1 + SOS within 1.5 km). Runs each tick when `params.preposition` is on; moves are real road
  routes; a dispatch mid-move starts from the interpolated point. Test in `test_dispatch_policy.py`.

## F10 — Road flood-time forecast  ✅ BUILT 2026-10-09
- `engine.road_forecast()` runs the engine's own closure rule (`flood_exposure >= 0.85 - blockage(t)`) forward;
  `route_candidates(..., closing=)` drops a candidate that reaches a road after its forecast close; legs carry
  `flood_forecast`. Shown in `RoadControlPanel` ("floods in ~N min"), `DecisionCard`, `/safe`. Labelled a forecast of
  the simulation's rule, not a hydraulic model. Tests: `test_road_forecast.py`.

## F11 — Measured uncertainty (conformal)  ✅ BUILT 2026-10-09
- `scripts/conformal_v2.py` → `models/conformal_v2.json`. Calibrates the model production uses: the **v3 stage-1
  regressor** + `flood_alert_model_v2.pkl`. GroupKFold(5) on training gauges; coverage measured once on 31 held-out
  gauges (788 rows); no test tuning. Measured (target 90 %):
  - absolute peak level ±210.1 m → coverage **86.4 %** (below target);
  - log interval → 98.0 %, median width ≈ 837 m;
  - alert set → 96.5 %, but **83 % of sets contain both classes**.
- Shown as-is in the Prediction tab; the hybrid operational probability has no interval. Tests: `test_conformal.py`.
- ☐ Report / paper decision.

## F12 — Monte-Carlo ops stress test  ✅ BUILT 2026-10-09
- `scripts/monte_carlo_ops.py --city <id> --runs 60 --seed 1`: `person_ops` on a virtual clock (no UI, no ML), synthetic
  SOS in city zones, random closures / surges; fixed flood probability 0.7 for hotspot weights; horizon 1500 demo-s
  (unserved = censored) → `models/ops_montecarlo_v1_<city>.json` + `.timing.json`. `GET /api/benchmark/ops?city=`,
  `OpsBenchmarkCard` on the Algorithms tab. Tests: `test_monte_carlo.py`.
- **Measured — Delhi (OSM city, 60 runs × 45 people = 2,700 per policy, seed 1, 2026-10-11):** all served.
  | Policy | time-to-safe mean | p90 | vs `first_free` (95 % CI) | faster in |
  |---|---|---|---|---|
  | `first_free` (fair baseline) | 71.58 min | 130.4 | — | — |
  | `greedy` | 70.14 | 126.5 | −1.44 [−2.25, −0.63] | 60 % of runs |
  | `optimal` | 68.56 | 120.9 | −3.02 [−4.02, −2.03] | 80 % |
  | `optimal` + pre-positioning | 68.10 | 120.0 | −3.48 [−4.56, −2.41] | 85 % |
  | `nearest_depot` (idealised) | 58.25 | 95.3 | **not comparable** — ambulances jump back to a depot | |
  Route benchmark Delhi (200 synthetic trips): QAOA = exhaustive on 100 % of routed trips at every blockage level;
  no-open-road trips 0 / 19 / 38 / 123 at 0 / 10 / 20 / 30 % blockage. The 30 % mean travel time is LOWER only because
  most long trips became unroutable (survivor effect) — do not read it as faster.
- Mumbai, Chennai, Kolkata, Guwahati, Patna: batch still running at handoff (≈ 50 min per city; Mumbai started 00:47).
- ☐ All six `ops_montecarlo_v1_<city>.json` and `route_benchmark_v1_<city>.json` present; numbers copied here.

## F13 — "Why this decision?" card  ✅ BUILT 2026-10-09
- `person_ops._decision(...)` → `row["decision"]`: queue reason, ambulances considered (ETA, free / busy / rejected),
  policy, shelters considered (distance, seats, reachable, closed), chosen + why — only real alternatives.
  `DecisionCard.jsx` in `RescueOpsPanel`, `LivePeopleTable`, AI person card. Test in `test_decision_equity.py`.

## F14 — Fairness dashboard  ✅ BUILT 2026-10-09
- `person_ops.equity_board(rows, now)`: time-to-pickup / time-to-safe by vulnerability and cluster (median, p90, n,
  still waiting); flags a group with median ≥ 1.5 × overall; small groups not flagged. `EquityPanel.jsx` on the Live tab
  and in History. Tests: `test_decision_equity.py`.

## F15 — `/safe` page + offline SOS  ✅ BUILT 2026-10-11
- `GET /api/public/safety?lat&lon` (30/min, bbox-checked, stores nothing): live flag, tier + probability + advice,
  nearest open shelter with seats reachable by an open road (route, km, vehicle min, walk min at 4.5 km/h), closed /
  soon-flooding roads within 2 km, river gauge if any.
- `/sos` outbox: offline (or no-answer) SOS kept in `localStorage["aq_sos_outbox"]`, sent on `online` / every 15 s; a
  refusal drops it and says why. Offline shell: `frontend/public/sw.js` + `utils/offlinePages.js` (production builds
  only; caches the `/sos` + `/safe` shell and `/assets/*`, never `/api`, `/ws` or map tiles).
- Tests: `test_public_sos.py` (+5 safety), `CitizenSos.test.jsx` (+3 offline), `offlinePages.test.js` (2).
- ☐ Real phone in airplane mode (production build over HTTPS or localhost).

---

# Planned — F16–F37 (picked 2026-10-11)

**Build order (all 22):**
**F16 → F36 → F17 → F18 → F19 → F27 → F30 → F23 → F21 → F29 → F25 → F32 → F33 → F34 → F31 → F24 → F28 → F26 → F22 →
F35 → F37 → F20.**
- F16 first (biggest demo value, reuses F12); F36 next so every later feature is checked in a real browser automatically.
- F17 / F18 / F19 / F27 replace assumptions with real data or a cited standard.
- F32 / F33 / F34 / F35 are measured results for the IEEE paper series.
- F37 must land before any public deployment beyond the demo. F20 depends on finding open flood-extent data.

| # | Feature | Size | Depends on | New data source |
|---|---|---|---|---|
| F16 | What-if planner on the live run | M | F12 | — |
| F17 | Real river gauges for Mumbai / Chennai / Kolkata / Guwahati / Patna | M | F7 | CWC flood-forecast stations |
| F18 | Live rainfall forecast per city | S–M | F7 | Open-Meteo forecast API |
| F19 | Real population per zone | M | F7 | WorldPop (or GHSL) |
| F20 | Check road closures against satellite flood maps | L | F7, F10 | Copernicus EMS / UNOSAT / Global Flood Database |
| F21 | Hospitals + medical triage | M | F7, F13 | OSM `amenity=hospital` |
| F22 | Boats for cut-off people | L | F1, F8 | OSM water + flood proxy (boat fleet assumed) |
| F23 | Early evacuation warnings per zone | M | F10, F12 | — (compliance assumed, swept) |
| F24 | SOS in Indian languages + SMS fallback | M | F4, F15 | — (translations need a native check) |
| F25 | Ambulance crews over a long operation | M | F8, F12 | — (shift rules assumed, swept) |
| F26 | Height-based road flood risk (HAND) | L | F7, F10 | Copernicus GLO-30 / SRTM elevation |
| F27 | Shelter capacity from building size | S–M | F7 | OSM building outlines + Sphere standard |
| F28 | Supply runs to shelters | M–L | F2, F27 | Sphere minimum standards |
| F29 | Silent zones (towers lost) | M | F7, F10 | OpenCelliD tower locations |
| F30 | Duplicate SOS detection | S–M | F4 | — (existing SOS rows) |
| F31 | Family reunification lookup | S | F4, F15 | — (existing tickets) |
| F32 | Fair vs fast dispatch trade-off | M | F8, F12, F14 | — |
| F33 | Sensitivity analysis of assumptions | M | F12 | — |
| F34 | Hindsight check of past runs | M | F5, F16 | — (stored frames) |
| F35 | AI Assistant accuracy evaluation | M | AI tab | — (question bank built from state) |
| F36 | Automatic browser tests | M | all UI | — (new dev dependency: Playwright) |
| F37 | Login, roles, action history | M–L | all endpoints | — |

## F16 — What-if planner on the live run  ✅ BUILT 2026-10-11

**As built.**
- `backend/services/ops_sim.py` is the ONE simulator core: `make_instance` / `play` / `stats` / `summarise` / `paired`
  (moved verbatim from `scripts/monte_carlo_ops.py`, which now imports them) + `snapshot(engine)` / `play_whatif` /
  `whatif_summary`. `test_monte_carlo.py` passes unchanged.
- Thread safety: `person_ops.ambulance_pool()` / `route_chooser()` read context variables (`person_ops.isolated(pool,
  chooser)`), so a what-if in `asyncio.to_thread` gets its own pool (+ "Extra Unit n") and Dijkstra routes without
  touching the live module globals.
- Snapshot = deep copies of `contact_log`, `ops_ctx()` roads / overrides / staging / F10 closing, plus future flood
  closures from `engine.road_forecast()` (operator roads excluded) and the run's observed SOS rate. Optional future SOS
  are Poisson at that rate, each a resample of a real caller of this run jittered ~400 m, flagged `synthetic`.
- Metric: sim minutes from the snapshot until safe; anyone still waiting at the horizon counts as the horizon
  (`time_to_safe_censored_min`, a lower bound), so options serving different numbers of people compare fairly. Paired
  per-run diff vs "No change" with 95 % CI and % of runs faster. Simulated crews accept every job (said in the UI).
- `backend/services/whatif.py`: one job at a time (409), `engine.start` cancels a job in flight and clears results.
  API `POST /api/simulation/whatif` (6/min) → job; `GET /api/simulation/whatif/{id}` adds `stale` (≥ 5 ticks or another
  run). AI Assistant facts include the last finished what-if ("what if…" questions).
- UI `components/agents/WhatIfPanel.jsx` (Agents tab, under Live controls): up to 4 options, horizon, runs, arrivals
  toggle, CI bar chart + table, stale badge. Apply = existing `/shelter` and `/road` endpoints only; extra ambulances /
  dispatch policy / pre-positioning are marked "not live" (fleet fixed; Setup applies next run).
- Live check 2026-10-11 (Delhi, 12 SOS, tick 2, 5 runs): 23 s; AI Assistant answered from the measured numbers.
- Tests: `test_whatif.py` (8), `WhatIfPanel.test.jsx` (3).

**Goal.** During a live run the operator asks "what if I add 3 ambulances / close shelter X / block road R / switch
dispatch policy?" The backend copies the current live state, plays the next 30–60 simulated minutes several times for
each option on the same `person_ops` code as the F12 stress test, and shows time-to-safety per option side by side.
Nothing in the live run changes until the operator applies an option with the existing controls.

**What exists.** `scripts/monte_carlo_ops.py`: `make_instance(rng, n_sos, surge)`, `play(inst, policy)`, `stats`,
`summarise`, `paired`. It starts from a synthetic instance, not from live state. Live state: `engine.contact_log`,
`engine.roads_now()`, `engine.shelter_overrides`, `engine.ops_ctx()`, `person_ops.ambulance_positions()`.

**Backend.**
1. Move the reusable core of `monte_carlo_ops.py` (`play`, `stats`, `summarise`, `paired`) into
   `backend/services/ops_sim.py`; the script imports it (one simulator, two callers). Keep the script's output identical
   — `test_monte_carlo.py` must still pass with the same seed.
2. `ops_sim.snapshot(engine)` → instance built from the LIVE run: deep copies of the rows (every stage kept), roads now,
   shelter overrides, ambulance positions, dispatch policy, current tick / blockage. No synthetic people added, except
   optional future SOS arrivals at the run's own observed rate, labelled `synthetic_arrivals`.
3. Options (validated schema `WhatIfOption`): `add_ambulances {n ≤ 10}`, `close_shelter {name}`,
   `set_capacity {name, capacity}`, `block_road {road_id}`, `open_road {road_id}`, `dispatch_policy {policy}`,
   `preposition {on}`. Always include a "no change" baseline.
4. Job API (never inside one request):
   `POST /api/simulation/whatif {options[≤ 4], horizon_min (15–120), runs (5–30)}` → `{job_id}` (operator, 6/min);
   `GET /api/simulation/whatif/{job_id}` → `{status, progress, results: per option {served, time_to_safe mean/p50/p90,
   still_waiting, diff_vs_baseline + 95 % CI, faster_in_pct_runs}, snapshot_at, run_id, tick}`.
   Runs in a thread via `asyncio.to_thread`; at most one job at a time; results kept in memory for the current run only.
   A result says which tick it was taken from; the UI marks it "stale" once the run has moved ≥ 5 ticks.
5. AI Assistant facts get the last finished what-if so "what if we add ambulances?" answers from measured numbers.

**Frontend.** `components/agents/WhatIfPanel.jsx` (Agents tab, next to `LiveControls`): pick up to 4 options →
Run → progress → bar chart (time-to-safe p50 / p90 per option, CI whiskers) + table. "Apply" buttons call the EXISTING
endpoints (shelter / road / policy), never a new mutation path. Label: "Simulated from the live state at tick N —
N runs, not a forecast of the real world."

**Tests.** `test_whatif.py`: snapshot copies live rows and does not mutate the engine; the "no change" option reproduces
the live plan on its first step; `add_ambulances` never makes time-to-safe worse in a fixed-seed tiny case; job
lifecycle (queued → running → done; second job while one runs → 409); schema rejects > 10 ambulances / unknown shelter.
Vitest: panel renders results and the stale badge.

**Done checklist**
- ☑ `ops_sim.py` shared by script + planner; F12 output unchanged for the same seed
- ☑ Live state untouched by a what-if (test)
- ☑ Panel shows measured per-option results with CI and "simulated" label
- ☑ Apply uses existing endpoints only
- ☐ Clicked through in a visible browser on two cities

## F17 — Real river gauges for the other 5 cities  ✅ BUILT 2026-10-11

**As built.**
- `backend/data/gauges_cwc.json`: **Guwahati (D.C. Court), Brahmaputra** — warning 48.68 m, danger 49.68 m, HFL 51.46 m
  (2004-07-21), from CWC Daily Flood Bulletin 17/07/2019; **Patna Gandhighat, Ganga** — warning 47.6 m, danger 48.6 m,
  HFL 50.52 m (2016-08-21), from CWC Daily Flood Bulletin 01/10/2019 (`cwc.gov.in/sites/default/files/cfcr-cwcdfb-*.pdf`).
  Station coordinates from Google Flood Hub's page for the same CWC station id (CWC_001-MBDGHY, CWC_003-MGD5PTN); the
  CWC FFS station API timed out, so the bulletins are the level source. Retrieved 2026-10-11.
- **Mumbai, Chennai, Kolkata: no CWC level-forecast station** within 30 km in the bulletins checked → stay rainfall-driven
  (recorded under `_none_found`). Valid result, not forced.
- `scripts/build_city_data.py`: `cwc_gauge()` is the fallback when INDOFLOODS has no gauge within 30 km;
  `--gauges-only` re-picks the gauge in an existing city file without an OSM rebuild (used for all six cities).
- CWC gauges carry `catchment: null` + `ml_note` ("ML model not applicable — no catchment attributes"); the engine's
  river doc uses the official danger level (same "metres above / below danger" mapping as Delhi) and carries
  `source_url` / `hfl_m`; `transfer_warning()` says the ML model is not specific to a CWC-only gauge.
- UI: city card "River gauge: <station> (CWC)", the city note shows source + retrieval date + ML note; river controls
  appear automatically for these cities (`flood_driver = "river"`).
- Test: `test_cities.py::test_cwc_gauges_are_sourced_and_used_only_where_listed`.
- Not done: live CWC level (no machine-readable feed reached); the stage still comes from the scenario.


**Goal.** Mumbai, Chennai, Kolkata, Guwahati and Patna get a real river gauge (station name, river, warning and danger
level from the official source), so they stop being rainfall-only where a gauge exists.

**Data.** Central Water Commission (CWC) flood-forecasting stations (e.g. Brahmaputra at Guwahati, Ganga at Patna).
**First step tomorrow:** confirm which stations exist near each city and where their warning / danger levels are
published (CWC flood-forecast site / bulletins). Only levels copied from that source, with the URL and date, go in the
file. A city with no CWC station within 30 km **stays rainfall-driven** — do not force one (Mumbai and Chennai may have
none; that is a valid result).

**Backend.**
- `backend/data/gauges_cwc.json` (new, additive): `{city_id: {station, river, lat, lon, warning_level_m,
  danger_level_m, hfl_m?, source_url, retrieved_at}}`.
- `scripts/build_city_data.py`: when INDOFLOODS has no gauge within 30 km, use the CWC entry; `gauge.source` says which.
- Catchment attributes for the ML model exist only for INDOFLOODS gauges → for a CWC-only gauge the river card and stage
  term work, but the ML model gets `null` catchment features and the UI says "ML model not applicable — no catchment
  attributes" (no borrowed attributes from a far-away gauge).
- Optional live level: only if CWC offers a machine-readable current level; otherwise the stage comes from the scenario
  (same "metres above / below danger" mapping as Delhi).

**Frontend.** City cards show "River gauge: <station> (CWC)"; river card + river / barrage controls appear for these
cities; transfer warning text per source.

**Tests.** Every gauge entry has `source_url` + `retrieved_at`; warning < danger; gauge within 30 km of the city centre;
a city without an entry stays rainfall-driven; ML catchment features null for CWC-only gauges.

**Done checklist**
- ☐ Station list + levels copied from the official source, with URL and date
- ☐ Cities without a station stay rainfall-driven (said in the UI)
- ☐ No catchment attribute borrowed from another gauge
- ☐ Tests + browser check per changed city

## F18 — Live rainfall forecast per city  ✅ BUILT 2026-10-11

**As built.**
﻿- `backend/services/rain_forecast.py`: Open-Meteo hourly precipitation (`forecast_days=3`, UTC), 8 s timeout, 30-min
  in-memory cache per (lat, lon) (Mongo cache not added — memory only). `ForecastUnavailable` on any failure.
- Units: the engine's `rainfall_mm` is a 24-h total, so at a tick whose simulated time is T the forecast value is the
  SUM of the forecast hours in [T, T + 24 h); `rainfall_1h_mm` = that hour; `forecast_daily_mm` = the next 3 such
  windows. Tick → sim time = `started_at + tick × tick_seconds × TIME_SCALE / 60` min.
- `SimulationStartRequest.rain_source: "scenario" | "forecast"`. `engine.start` fetches BEFORE stopping the old run;
  failure → HTTP 503 "… the run was not started" (old run untouched). Never a silent fallback. Operator rainfall
  overrides still win.
- State: `rain_source`, `rain_forecast {source, attribution, fetched_at, lat, lon, url, per_tick[], hourly[]}`;
  weather doc says `rain_source` + "24-h forecast total, Open-Meteo".
- UI: Setup (city card area) checkbox "Use live rainfall forecast"; Prediction tab `RainForecastCard` (per-tick 24-h
  total + hourly line, "forecast, not observed" badge, fetch time, attribution).
- Tests: `test_rain_forecast.py` (5, HTTP mocked).


**Goal.** A "Use live forecast" option on Setup: the next 48 h of hourly rain for the chosen city drives the run's
rainfall instead of the scenario's fixed number.

**Data.** Open-Meteo forecast API (free, no key): `https://api.open-meteo.com/v1/forecast?latitude=..&longitude=..
&hourly=precipitation&forecast_days=2`. Forecast, not observation — labelled "forecast (Open-Meteo)". Attribution shown.

**Backend.**
- `backend/services/rain_forecast.py`: fetch at run start (timeout 8 s, cache 30 min per city in memory + Mongo
  `settings`), map hourly mm to ticks (`tick_seconds` × `TIME_SCALE`).
- `SimulationParams.rain_source: "scenario" | "forecast"`; `_evolve` uses the forecast series when set. Fetch fails →
  the run refuses to start with a clear message (never silently falls back to the scenario number).
- Served in state: `rain_source`, `forecast_fetched_at`, series.

**Frontend.** Setup toggle; Prediction tab chart shows the forecast series with source and fetch time.

**Tests.** Hourly → tick mapping; failed fetch → 503 with message (mocked HTTP); cache hit doesn't call the API; run with
`forecast` uses the series values exactly.

**Done checklist**
- ☐ Forecast labelled as forecast with source + time
- ☐ Fetch failure is visible, never a silent fallback
- ☐ Tests (HTTP mocked) + browser check

## F19 — Real population per zone  ✅ BUILT 2026-10-11

**As built.**
﻿- `scripts/build_population.py --all` filled all 36 OSM zones from the WorldPop stats API (dataset `wpgppop`,
  Global Project Population, unconstrained 100 m, **2020**, CC BY 4.0). Zones are OSM points, so the count is the sum
  over a **1 km circle** around the point — written in `population_method`; `population_source` names dataset, year,
  URL, licence. No new dependency (httpx). A failed zone stays `null` with `population_missing_reason`.
- Zone sums (6 circles each): Chennai 356,598 · Delhi 485,226 · Guwahati 108,197 · Kolkata 849,123 · Mumbai 614,394 ·
  Patna 452,893.
- Null-safe arithmetic kept (`solvers._pop`, `shelter_engine.score_shelter`).
- UI: zone popups on the flood map show "Population: N (WorldPop 2020, sum … 1 km circle …)" or "unknown".
- Tests: `test_cities.py::test_zone_population_is_sourced_or_null` (per city; range check below the Census 2011
  urban-agglomeration figure, not a fit).


**Goal.** Fill each zone's `population` (now `null`) from a named population dataset, so shelter demand, fairness and
the what-if planner use real people counts.

**Data.** WorldPop (100 m grid, India) or GHSL population grid. **First step:** check whether the WorldPop stats API
(`api.worldpop.org/v1/services/stats`, sum over a GeoJSON polygon) works for our zone polygons; if not, download the
India raster once in a build script. Prefer the option with **no new heavy dependency**; if `rasterio` is needed, ask the
user before adding it.

**Backend.**
- `scripts/build_population.py --city <id>` → writes `population`, `population_source` (dataset + year + URL),
  `population_method` ("sum over zone polygon") into `backend/data/cities/<id>.json` (rebuild, never hand-edit).
- Zones without a polygon (point-only suburbs) → buffer radius stated in `population_method`.
- Keep the null-safe arithmetic from 2026-10-11 (a zone may still be null).

**Frontend.** Zone popups and the evacuation plan show population with source; "unknown" for null.

**Tests.** Every filled zone has source + method; totals within a sane range of the city's published census figure
(range check only, not a fit); null zones still run (existing per-city tick test).

**Done checklist**
- ☐ Population from a named dataset, with year and method
- ☐ No new heavy dependency without asking
- ☐ Rebuilt city files, tests green, browser check

## F20 — Check road closures against satellite flood maps  ✅ BUILT 2026-10-11

**As built.**
- `dataset/unosat_fl20151123ind/`: UNOSAT activation FL20151123IND Sentinel-1 satellite flood analysis (24 Nov 2015, CERN/HDX)
  and `dataset/chennai-flooded-streets-Dec2.geojson`: OSM-India crowdsourced flooded-streets layer for Chennai Dec 2015 (CC0).
- `scripts/validate_closures.py`:
  - Pure-Python ESRI Shapefile reader + ray-casting point-in-polygon (Jordan curve theorem) with grid spatial index.
  - BucketGrid spatial index for crowdsourced flooded-street points (snap 0.35 km).
  - Matches Chennai road centroids against ground truth; compares against ops_sim proxy rule (`flood_exposure >= 0.85 - blockage`).
  - Threshold sweep over blockage levels [0.0..0.75] and breakdown by road class (primary, secondary, trunk).
  - Generates `models/closure_validation_v1_chennai.json`: precision 93.6%, recall 37.2%, F1 0.532 at default blockage.
- Frontend: `ClosureValidationCard` in `frontend/src/components/scenario/MeasuredCards.jsx`, mounted on the Algorithms tab in `ScenarioOutputs.jsx`.
- Tests: `backend/tests/test_closure_validation.py` (11/11 tests pass) testing ray-casting, metrics calculation, monotonicity of sweeps, and metadata schema.

**Done checklist**
- ☑ Open flood-extent data found (UNOSAT FL20151123IND + OSM Chennai crowdsource)
- ☑ Measured precision / recall with source, no tuning on the test event (Precision 93.6%, Recall 37.2%, F1 0.532)
- ☑ Card mounted on Algorithms tab + full test suite passing


## F21 — Hospitals + medical triage  ✅ BUILT 2026-10-11

**As built.**
﻿- `scripts/build_hospitals.py --all`: OSM `amenity=hospital` in each city bbox, one per name, emergency=yes / tagged
  beds ranked first, spread-picked to **8 per city** (all six cities have 8). `beds` only from the OSM `beds` tag
  (1 of 48 hospitals is tagged) — otherwise `null`, shown as "capacity unknown". Raw cache `raw/<id>.hospitals.json`.
  The demo network uses the real Delhi hospitals. `geo.cities.activate` swaps `seed.HOSPITALS` in place; city view
  serves them.
- SOS `medical: none | injured | critical` (operator `CitizenSosRequest`, public `/sos` "Is anyone injured?", surge =
  **synthetic** share 5 % critical / 10 % injured from its own RNG, `medical_source` says so). Injured / critical →
  `needs_ambulance`.
- Stage machine (one machine): `_assign` sends a medical row to the nearest OSM hospital with an open road
  (`_reachable_hospital`, up to 4 tried) and reuses the `to_shelter` leg with `destination_kind: "hospital"`; none
  reachable → nearest shelter + red `hospital_alert`. No hospitals mapped → shelter as before. Cut-off hospital legs are
  re-planned to another hospital in `reallocate` (never to a shelter). Hospital rows never count against shelter seats.
- Triage (labelled parameter, assumed): queued rows are taken critical → injured → others (rank 2 = the old order, so
  nothing changes without a medical flag); assignment weight = max(vulnerability, medical) (`MEDICAL_WEIGHT` critical
  2.0, injured 1.4). Why-card lists medical, destination kind and the hospitals compared; fairness board adds
  `by_medical`.
- UI: cached 🏥 hospital markers on the live map; People table "🏥 to hospital" chip + medical badge; `/sos` injury
  question (offline queue keeps it); `/safe` shows the nearest hospital with road time and "beds: unknown".
- Tests: `test_hospitals.py` (10).


**Goal.** Injured or critical people go to a hospital, everyone else to a shelter. Hospitals are real OSM features.

**Data.** OSM `amenity=hospital` (name, location; `beds` tag only if present). Bed counts are mostly missing →
`beds: null`, "capacity unknown" in the UI — never invented. Update the CLAUDE.md "does not exist" line when this lands.

**Backend.**
- `build_city_data.py`: add `hospitals` (same spread / dedupe as shelters, ≤ 8 per city).
- SOS gets `medical: "none" | "injured" | "critical"` (operator form, `/sos` question, surge = labelled synthetic share).
- `person_ops`: a medical row's destination is the nearest reachable hospital (same `_reachable_*` pattern); stage
  `to_shelter` is reused with `destination_kind: "hospital"` so the stage machine stays one machine. Triage weight in
  `VULN_WEIGHT` (`critical` first in the queue) — weights are a labelled parameter.
- `_decision` lists hospitals considered. Fairness board adds the medical class.

**Frontend.** Hospital icon (cached) on maps; "🏥 to hospital" chip; `/sos` adds "Is anyone injured?"; `/safe` shows the
nearest hospital too.

**Tests.** City files: hospitals have OSM ids; critical row routed to a hospital and served before a standard row; no
hospital reachable → shelter + red alert; existing tests unchanged when `medical` is absent.

**Done checklist**
- ☐ Hospitals from OSM only, beds null unless tagged
- ☐ One stage machine (destination kind, not a new simulator)
- ☐ Triage weight labelled; tests; browser check

## F22 — Boats for cut-off people  ✅ BUILT 2026-10-11

**As built.**
- `backend/services/boat_route.py`: grid representation of city bbox (80×80) with cell passability over mapped OSM water and buffer around currently blocked roads. 8-directional A* search computes exact path coordinates, distance in km, and travel time at assumed boat speed (15 km/h). Cached per city and blocked road set.
- `person_ops.py`: unit role `boat`. In `_assign`, if a person has `no_open_road`, a free boat is assigned, boat route planned, route alert cleared, and tagged `by_boat: True`. If roads are open, ambulances are used (never boats). Boat depots = rescue depots closest to water bodies. Fleet size `boats` is an assumed parameter (Setup slider 0–20, default 0 = off).
- Fleet board: includes boats in status, busy count, and free units; Why-card notes boat assignment.
- UI: cached 🚤 icon on `LiveRescueMap.jsx`, blue dashed polyline and legend entry; `LivePeopleTable.jsx` displays `🚤 by boat` chip; `CityPicker.jsx` has boats slider control.
- Tests: `backend/tests/test_boats.py` (5 tests pass): tiny synthetic map passability, A* never crosses dry cells, people with open roads never get boats, boats = 0 gives identical baseline behavior.

**Done checklist**
- ☑ Fleet + speed assumed and labelled; default off
- ☑ Boat path computed on the flood grid, never a straight line
- ☑ Tests; browser check in a city with "No open road" legs

## F23 — Early evacuation warnings per zone  ✅ BUILT 2026-10-11

**As built.**
﻿- Zone ↔ road: a road belongs to a zone when its OSM point is within **1.5 km** (`ops_sim.zone_road_ids`, shared).
- Live: `engine.zone_warnings()` — a zone is warned when its first road is forecast by F10 (`road_forecast`) to close
  within the playbook's `warning_lead_min` (default 30 sim min, editable 1–240) or a flood already closed one.
  `mas.announce_zone_warnings`: one yellow EVACUATION WARNING per zone per run (key `warn:{run}:{zone}`, with WorldPop
  population when known) + the new `ZONE_WARNING` playbook once per run. `state.zone_warnings` = first warning per zone
  with its tick; Live tab shows a warning strip; messages reach the bell / Agents feed.
- Compliance: `SimulationStartRequest.warning_compliance` (Setup slider 0–80 %, default **0 = off**, labelled "assumed,
  not measured"). It changes nothing in the live stage machine; the **what-if** drops synthetic arrivals near an
  already-warned zone with that probability (`sos_avoided_by_warning_per_run`), and the **stress test** sweeps it.
- `scripts/monte_carlo_ops.py --compliance 0,0.2,0.4,0.6 [--lead-min 30]` → `models/ops_warning_sweep_v1_<city>.json`
  (policy optimal; only late surge callers can be avoided; separate seeded RNG so compliance 0 = F12 results exactly).
  Served by the generic `GET /api/benchmark/stored/ops_warning_sweep_v1?city=`; Algorithms card `WarningSweepCard`
  shows the whole curve (SOS avoided + time to safety per compliance), never one headline number.
- Tests: `test_zone_warnings.py` (6).


**Goal.** Before a zone's roads flood (F10 forecast), the agents issue an evacuation warning for that zone. An assumed
share of its people leave early by themselves. The stress test measures how many SOS calls and wait-minutes that saves.

**Backend.**
- `mas.py`: `announce_zone_warning(zone, closes_in_min)` when the first road in the zone is forecast to close within
  `WARNING_LEAD_MIN` (playbook-editable, trigger `ZONE_WARNING`, stable key `warn:{zone}`).
- `compliance` = **assumed** share (Setup slider, default 0 = off, labelled "assumed — not measured"); warned zones then
  generate fewer late SOS in the stress test / what-if (F16). No compliance value is presented as a finding.
- `monte_carlo_ops.py`: `--compliance 0,0.2,0.4,0.6` sweep → `models/ops_warning_sweep_v1_<city>.json`.

**Frontend.** Zone warning banners on the map + Agents feed; Algorithms card "SOS avoided vs assumed compliance"
(a curve over the sweep, not a single number).

**Tests.** Warning fires once per zone at the right lead time; compliance 0 = today's results exactly; sweep JSON has every
level.

**Done checklist**
- ☐ Warnings from the F10 forecast, playbook-editable
- ☐ Compliance assumed + swept, never a single headline number
- ☐ Tests; browser check

## F24 — SOS in Indian languages + SMS fallback  ✅ BUILT 2026-10-11

**As built.**
﻿- `frontend/src/i18n/phonePages.js`: one dictionary per language — English, हिन्दी, தமிழ், বাংলা, অসমীয়া — for `/sos`
  (form, errors, location notes, offline banner, status card, share, SMS) and `/safe` (title, button, section
  headings). **Hindi / Tamil / Bengali / Assamese are machine-drafted, `reviewed: false`**, and the page shows "not yet
  checked by a native speaker" in that language. Nothing is presented as official. Server-side texts (advice, stage
  text from the API) stay English. Values sent to the server stay English codes.
- `i18n/LangPicker.jsx` on `/sos` and `/safe`; choice remembered in `localStorage` (try/catch); `<html lang>` set.
- SMS fallback: "✉️ Send by SMS (no internet)" builds `sms:<number>?body=SOS <lat>,<lon> P<people> W<water> [M<medical>]
  <name>`. The number comes ONLY from `VITE_SOS_SMS_NUMBER` (frontend build env); unset → the button is hidden. No number
  is in the repo. No SMS gateway: `POST /api/public/sos/sms-text {text}` (**operator only**, 60/min) parses a pasted
  text (`backend/services/sms_parse.py`), checks the service bbox and adds the SOS (`source: "sms (entered by the
  control room)"`).
- The Tamil name-only voice agent is unchanged.
- Tests: `test_sms_parse.py` (9, incl. the endpoint), `phonePages.test.js` (5: every key in every language, reviewed
  flags, exact SMS text shared with the backend test, no number unless configured).
- Open: native-speaker review per language (record it by setting `reviewed: true`), phone check.


**Goal.** `/sos` and `/safe` in Hindi, Tamil, Bengali and Assamese (plus English), and a text-only SOS for phones with
no data connection.

**Work.**
- `frontend/src/i18n/phonePages.js`: one dictionary per language; language picker on the phone pages (remembered in
  `localStorage`, try/catch); `lang` attribute set. **Translations must be checked by a native speaker** before the
  demo — mark each language `reviewed: false` until then and show nothing as "official".
- SMS fallback: "Send by SMS" builds an `sms:` link with a compact text (`SOS <lat>,<lon> P<people> W<water> <name>`).
  The number comes ONLY from config (`VITE_SOS_SMS_NUMBER`); if it is not set, the button is hidden — no number is ever
  hard-coded or invented. Receiving SMS (a gateway) is out of scope; `POST /api/public/sos/sms-text` (operator) parses a
  pasted text so the control room can enter it.
- The existing Tamil name-only voice agent is not changed.

**Tests.** Every key present in every language; SMS text round-trips through the parser; button hidden without config.

**Done checklist**
- ☐ 5 languages, native review recorded per language
- ☐ SMS number from config only; parser tested
- ☐ Phone check

## F25 — Ambulance crews over a long operation  ✅ BUILT 2026-10-11

**As built.**
﻿- Rules are **assumed, labelled, default off** (`person_ops.CREW_DEFAULTS`: 12 h driving → 8 h rest at the home depot;
  400 km → 20 min refuel; `CREW_SOURCE`). Run param `crew_rules {on, …}` (Setup checkbox "Crew rules (assumed)"),
  carried in `engine.ops_ctx()` and the what-if snapshot.
- `crew_state(unit)` is **derived** from the unit's own completed legs (driving minutes + km since the last rest /
  refuel), never stored — like positions. `unavailable_units` → resting / refuelling units are not dispatched,
  `ambulance_positions` puts a resting unit at its home depot with `until`, the wait reason says "busy or off duty …
  next back at hh:mm". A crew coming back is a resource event: a waiting row is assigned at the moment it is back
  (never before). Rules off → identical to before (tests).
- Fleet board: per-unit `crew` + `ambulances_off_duty`, `crew_rules_source`; FleetPanel shows 😴 RESTING / ⛽ REFUELLING
  with minutes left.
- `scripts/monte_carlo_ops.py --long [--hours 72 --per-hour 6]`: `make_long_instance` (Poisson SOS over the whole
  operation, synthetic), rules on vs off on the same instances, paired diff → `models/ops_long_v1_<city>.json`,
  Algorithms card `LongRunCard` via `/api/benchmark/stored/ops_long_v1`.
- Tests: `test_crew_rules.py` (5).


**Goal.** Over a 24–72 h operation ambulances need crew rest and refuelling, so real capacity drops. Make that visible
and measure it.

**Backend.**
- `person_ops`: per ambulance `active_minutes` (derived from its legs, like positions — not stored separately); after
  `SHIFT_MAX_MIN` of active time the unit goes `resting` for `REST_MIN` at its home depot; fuel modelled the same way
  (`RANGE_KM` → refuel stop at the depot). All three are **assumed, labelled parameters** (Setup "Crew rules", default
  off).
- Fleet board shows resting / refuelling with time left; Why-card says "Unit 4 resting until 03:10".
- `monte_carlo_ops.py --long` (horizon 72 h, crew rules on/off) → `models/ops_long_v1_<city>.json`.

**Frontend.** Fleet panel states; Algorithms card "time-to-safe with vs without crew limits".

**Tests.** Unit rests after the shift limit and returns after rest; resting unit never dispatched; rules off = today's
results exactly.

**Done checklist**
- ☐ Rules assumed + labelled, default off
- ☐ Positions / activity derived, not a second state
- ☐ Long stress test measured; tests; browser check

## F26 — Height-based road flood risk (HAND)  📋 PLANNED

**Goal.** Replace the road flood-exposure proxy "distance to water" with **height above the nearest drainage (HAND)**
computed from a real elevation model, so low roads flood before high roads even at the same distance from water.

**Data.** Copernicus DEM GLO-30 (30 m, free) or SRTM 30 m. HAND is a published method (Rennó et al., 2008): flow
direction → drainage network → height of each cell above the drainage cell it flows to. Licence + tile ids recorded.

**Work.**
- `scripts/build_hand.py --city <id>` → `backend/data/cities/<id>.hand.json` (per road point: elevation, HAND m) — additive;
  `build_city_data.py` keeps `flood_exposure_v1` (distance proxy) and adds `flood_exposure_v2` (HAND-based, labelled).
- Reading GeoTIFF needs a raster library — **ask the user before adding `rasterio` / `tifffile`**; a pure-numpy reader
  for the DEM's plain GeoTIFF is the fallback.
- `SimulationParams.exposure_model: "distance" | "hand"` (default stays "distance" until F20 or a comparison supports
  HAND). Both paths share the same closure rule.

**Tests.** HAND on a tiny synthetic DEM (known valley); HAND ≥ 0 everywhere; v1 unchanged; switching model changes which
roads close first, never the rule itself.

**Done checklist**
- ☐ DEM source + licence recorded; dependency decision asked
- ☐ `flood_exposure_v2` additive; default unchanged
- ☐ Tests; comparison card (v1 vs v2 closure order)

## F27 — Shelter capacity from building size  ✅ BUILT 2026-10-11

**As built.**
- Exact citation: Sphere Handbook 2018 (4th ed.), Shelter and Settlement Standard 3: Living space (minimum covered living space 3.5 m² per person). Stored in `capacity_citation` in city files.
- `scripts/build_shelter_capacity.py --all`: parses OSM building footprints per shelter, geodesic area in m², `building:levels` (tag or 1 fallback), usable_share = 0.5 (assumed). Capacity = floor(floor_area_m2 × usable_share ÷ 3.5). Shelters without OSM outline retain `"assumed by building type"`. Rebuilt all 6 city files (`delhi`, `mumbai`, `chennai`, `kolkata`, `guwahati`, `patna`).
- UI: `ShelterCapacityPanel.jsx` breaks down the formula: `Capacity: X m² floor (N buildings) × 0.5 usable ÷ 3.5 m² per person (Sphere 2018)`.
- Tests: `backend/tests/test_shelter_capacity.py` (9 tests pass): area of known square polygon, Sphere capacity formula, missing outline fallback, presence of standard citation and handbook URL.

**Done checklist**
- ☑ Sphere figure + edition cited
- ☑ Every capacity says how it was made
- ☑ Rebuilt city files; tests

## F28 — Food, water and medicine supply runs  ✅ BUILT 2026-10-11

**As built.**
- Exact citation: Sphere Handbook 2018: WASH water standard 2.1 (≥ 15 L / person / day) and Food security standard 6.1 (≥ 2,100 kcal / person / day).
- `backend/services/supply.py`: daily need = delivered people (`rescued` rows) × Sphere minimum rates. Stock (person-days) decreases as simulation time advances. Supply trucks dispatched nearest-need-first on real road network (`route_candidates`), re-planned on road closures via F1 hook.
- Fleet assumed: `trucks` count (default 0 = feature off) and `truck_load_person_days` (default 500). State: `supply_board` with need, stock, hours remaining, and truck status.
- UI: `CityPicker.jsx` supply run checkbox toggle, `SupplyPanel.jsx` per-shelter water/food status table, cached 🚚 truck icons on `LiveRescueMap.jsx`.
- Tests: `backend/tests/test_supply.py` (4 tests pass): need scales with delivered people at Sphere rates, truck routes never use closed roads, trucks = 0 leaves baseline simulation identical.

**Done checklist**
- ☑ Rates cited; fleet assumed + labelled; default off
- ☑ Shared router + stage machine
- ☑ Tests; browser check

## F29 — Silent zones (phone towers lost to the flood)  ✅ BUILT 2026-10-11

**As built.**
﻿- **Code complete; tower data not downloaded** — `OPENCELLID_TOKEN` is not in `.env` yet (the authors register at
  opencellid.org). Until a `<city>.towers.json` exists the feature is **off** (`state.silent_zones = null`) and the
  Live tab says how to switch it on. Nothing simulated in its place.
- `scripts/build_towers.py --city <id> | --all`: token only from env / `.env` (never asked for or stored; exits 2 with a
  clear message when missing); OpenCelliD `cell/getInArea` tiled at 1.9 km (< 4 km² per request), cached in
  `raw/<id>.towers.raw.json`; each tower gets `flood_exposure` from the SAME distance-to-water proxy as the roads
  (`build_city_data.exposure_at`); file carries source, CC BY-SA 4.0 licence, attribution, retrieval date.
- `backend/services/towers.py`: tower flooded ⇔ exposure ≥ 0.85 − blockage (the road rule). Coverage radius
  **assumed** by radio (GSM 2 km, UMTS 1.5, LTE 1, NR 0.5). 0.5 km grid; a cell is silent when a now-flooded tower
  covered it and no working tower does (numpy). Cells grouped by nearest OSM zone. Labelled "modelled".
- Engine: `silent_view` per tick; MAS `announce_silent_zones` (key `silent:{run}:{zone}`) + `SILENT_ZONE` playbook
  once per run. `POST /api/simulation/patrol {zone_id}` sends the nearest free ambulance with an open road to the
  area's centre as an F9 staging move (positions stay derived).
- UI: `SilentZonesPanel` (Live tab: areas + "Send patrol", or the switch-on hint), dashed grey circles on the live map;
  `/safe` shows "Your area may have no phone signal (modelled)… your SOS will wait on your phone" (F15 outbox).
- Tests: `test_towers.py` (5, synthetic towers).


**Goal.** When the flood reaches mobile towers, people near them cannot send an SOS — the quietest areas may be the worst.
Mark those areas "silent" and let the agents send a patrol there without waiting for calls.

**Data.** OpenCelliD cell-tower locations (open data, CC BY-SA 4.0, attribution required). Downloading needs a free
OpenCelliD token — **the user registers and puts the token in `.env`**; the build script never asks for or stores a
password. Tower flood = the tower's location under the same closure / exposure rule as roads (labelled "modelled").

**Work.**
- `scripts/build_towers.py --city <id>` → `<id>.towers.json` (location, radio type, source, licence).
- `engine`: `silent_zones` = coverage circles (radius assumed per radio type, labelled) of towers flooded now, minus the
  coverage of towers still up. MAS `announce_silent_zone` (key `silent:{zone}`), playbook trigger `SILENT_ZONE`;
  optional patrol = a reposition move (F9 code) to the zone centre.
- `/safe` says "your area may have no signal — the SOS will wait on your phone" (F15 outbox).

**Tests.** Coverage union / difference on synthetic towers; flooded tower makes its area silent only if no other tower
covers it; feature off = today.

**Done checklist**
- ☐ Tower data with licence + attribution; token from `.env` only
- ☐ Silent zones shown + patrol option; labelled "modelled"
- ☐ Tests; browser check

## F30 — Duplicate SOS detection and merge  ✅ BUILT 2026-10-11

**As built.**
﻿- `person_ops.duplicate_candidates(rows, dismissed)`: open SOS pairs ≤ **75 m** and ≤ **20 sim min** apart (queued
  timestamps × TIME_SCALE) whose normalised names are ≥ **80 %** alike (1 − Levenshtein / max length) OR that came
  from the same phone (`device_key`). Score + plain reasons. Never merges by itself.
- `device_key` = per-run SHA-256 of run id + caller address, truncated (public `/sos` only); the address itself is not
  stored. Mirrored onto the log row via `add_citizen_sos`.
- `person_ops.merge_rows(rows, keep, drop)`: the dropped row → `ops_status "merged"`, `merged_into`, its shelter seats
  released (`shelter_name_before_merge` kept), MERGED journey entry on both rows; kept row takes the larger head count.
  `advance_all` never touches a merged row; its unit is freed (no longer an active stage) and the queue re-plans at once.
- Engine: `merge_sos` (re-plans before any await, replay frame "merge"), `dismiss_duplicate` (pair never re-flagged
  this run), `dup_dismissed` / `merge_log` reset per run; state `duplicate_candidates` (cached per roster change) +
  `merge_log`. API `POST /api/simulation/sos/merge {keep, drop}` (404 unknown, 409 not open) and
  `POST /api/simulation/sos/not-duplicate {a, b}`. Public status text for a merged ticket.
- UI: `DuplicateSosPanel` on the People tab (Merge into … / Not a duplicate); `rescueOps.js` lists merged rows in
  `merged` instead of drawing them as a second person; `mergedFrom` on the kept person.
- Tests: `test_duplicates.py` (4), `rescueOps.test.js` "F30 merged SOS".


**Goal.** Families call several times and neighbours report the same people. Detect likely duplicates so ambulances are
not wasted; the operator confirms every merge.

**Work.**
- `person_ops.duplicate_candidates(rows)`: pairs within 75 m and 20 sim-min with similar names (normalised edit
  distance) or same ticket device; score + reasons. Never auto-merged.
- `POST /api/simulation/sos/merge {keep, drop}` (operator): the dropped row moves to `merged_into` (kept in the journey,
  not deleted); its unit is freed and the plan re-run.
- UI: "possible duplicate" chip in the People table with a Merge / Not a duplicate choice.

**Tests.** Thresholds on fixed rows; merge frees the unit and keeps history; "not a duplicate" stops re-flagging.

**Done checklist**
- ☐ Suggest only, operator decides; history kept
- ☐ Tests; browser check

## F31 — Family reunification lookup  ✅ BUILT 2026-10-11

**As built.**
﻿- Reuses `GET /api/public/sos/{ticket}` (random 32-hex ticket only): when `rescued` it now returns `safe_at {name,
  lat, lon, kind shelter|hospital, since}`; still only that person's own status. The endpoint now has a **30/min
  rate limit** (it had none) so tickets cannot be guessed from `/find`.
- `/sos` status card: "🔗 Share with family" copies `<origin>/find?t=<ticket>` (clipboard in try/catch) with the note
  "Only people with this link can see your status"; once safe, "Safe at … · map" (OpenStreetMap link).
- New page `/find` (`pages/FindPage`): paste the link or ticket → the same status view; privacy text "Only people with
  the SOS ticket can see this. There is no search by name, phone number or photo." Anything that is not a ticket is
  refused in the page; names / partial tickets get 404 from the API.
- Tests: `test_public_sos.py` (+2: safe_at by ticket only, 404 for name / partial ticket, 429 after 30/min),
  `FindPage.test.jsx` (2).


**Goal.** "Where is my mother?" — a person who holds the SOS ticket (shared by the family) can see which shelter she
reached. No search by name, phone or face; nothing public.

**Work.**
- Reuse `GET /api/public/sos/{ticket}`: when `rescued`, include shelter name + map pin; a "share this ticket" button on
  `/sos` (copy link). Rate limits unchanged.
- `/find` page: paste a ticket → status. Clear text: "only people with the ticket can see this".

**Tests.** Ticket shows only that person; a name or partial ticket gets 404; rate limit applies.

**Done checklist**
- ☐ Ticket-only, privacy note shown
- ☐ Tests; phone check

## F32 — Fair vs fast dispatch: measured trade-off  ✅ BUILT 2026-10-11

**As built.**
﻿- Policy `fair` (`DISPATCH_POLICIES`, schema, Setup "Fair vs fast (λ)" + λ input, default λ = 1). **λ = 0 delegates to
  `optimal`** (identical results, test). For λ > 0, `_fair_plan` solves one Hungarian assignment over the WHOLE
  waiting ambulance queue (up to 4× the free units, triage / queue order): cost = weight × road minutes − λ × the
  person's group's current mean wait (groups = F14 vulnerability classes). A row left out of the plan waits with
  "Fair dispatch (λ=…) serves a longer-waiting group first"; unreachable pairs stay in the plan (nobody held back by a
  closed road). Why-card `dispatch_choice` carries λ and the group waits.
- `scripts/monte_carlo_ops.py --fair-lambdas 0,0.5,1,2,4 [--runs 20]` → `models/ops_fairness_v1_<city>.json`:
  first_free, optimal and fair(λ) on the same instances; per point mean time to safety and the worst group's median
  (per run, groups with ≥ 2 served), each mean ± 95 % CI; paired vs optimal. Algorithms card `FairnessCurveCard`.
  Reported as measured — no claim that a larger λ always helps.
- Tests: `test_fair_dispatch.py` (3).
- Paper: only through the `ieee-paper` skill after the per-city files exist (authors' decision).


**Goal.** A dispatch rule with a fairness knob λ: minimise mean road minutes + λ × the worst group's wait. Measure the
full curve (mean time-to-safe vs worst-group time-to-safe) for λ from 0 to high, across the six cities.

**Work.**
- `person_ops`: policy `fair` (assignment cost adds λ × the waiting time of the person's group, groups from F14).
- `monte_carlo_ops.py --policies first_free,optimal,fair --lambda 0,0.5,1,2,4` →
  `models/ops_fairness_v1_<city>.json`. Card: the trade-off curve with CI.
- Paper: only through the `ieee-paper` skill; report the curve as measured, no claim beyond it.

**Tests.** λ = 0 equals `optimal`; larger λ never increases the worst group's median on a fixed instance (or report when
it does); sweep file has every λ.

**Done checklist**
- ☐ Policy + sweep + card
- ☐ Measured curve per city; paper decision

## F33 — Which assumptions matter (sensitivity analysis)  ✅ BUILT 2026-10-11

**As built.**
﻿- `scripts/sensitivity_ops.py --city <id> [--runs 10] [--sobol N]` → `models/ops_sensitivity_v1_<city>.json`.
  Varied assumptions, each with a stated range and reason: ambulances 6–14 (10), speed 18–32 km/h (25), shelter
  capacity ×0.5–×1.5, mobilise 1–4 wall s (2), warning compliance 0–0.6 (0), start blockage −0.05 / +0.10. Listed as
  not varied with the reason: accept timeout (no effect with simulated crews), boats (default 0), crew rules (F25 long
  run), medical weights (instances carry no medical flags).
- One-at-a-time tornado (same seeded operations for every setting, `optimal` policy, metric mean time to safety +
  served share); optional variance-based design in plain numpy (Saltelli A/B/AB_i, first-order S1 Saltelli 2010,
  total ST Jansen, 200-bootstrap CI) — **no SALib** (not approved). Assumptions are applied in the script process only
  and restored after every play (test).
- Algorithms card `SensitivityCard` (tornado bars + ranges / reasons + Sobol line + not-varied list).
- Tests: `test_sensitivity.py` (3: zero range → zero effect, deterministic, restored).


**Goal.** Every labelled assumption (crew size, speeds, shelter capacity factor, compliance, accept timeout, boat
fleet…) is varied over a stated range and its effect on time-to-safe is measured, so we can say which assumptions
change the conclusions and which do not.

**Work.**
- `scripts/sensitivity_ops.py --city <id>`: one-at-a-time ranges first, then a variance-based (Sobol-style) design if the
  budget allows; ranges stored with a reason for each. Output `models/ops_sensitivity_v1_<city>.json` (tornado data).
- Algorithms tab tornado chart. Any new dependency (e.g. SALib) — ask first; a plain-numpy estimator is the fallback.

**Tests.** Zero-range parameter has zero effect; deterministic with a seed; JSON lists each range + reason.

**Done checklist**
- ☐ All labelled assumptions listed with ranges + reasons
- ☐ Tornado card; paper decision

## F34 — Hindsight check of past runs (regret)  ✅ BUILT 2026-10-11

**As built.**
﻿- `ops_sim.from_frames(frames)` rebuilds a stored run (F5 frames): callers at their recorded queue times, road closures
  at the frame where they first appear, shelter override changes, recorded time to safety per person, and (new in the
  frame) the run's own `dispatch_policy` / `fair_lambda` / `preposition`. `play` replays `closure_schedule` /
  `shelter_schedule` instead of the synthetic flood rule.
- `ops_sim.hindsight_bound`: per person, first dispatch slot + roll-out + **straight-line** km from the nearest depot or
  shelter + straight-line km to the nearest shelter at rescue speed, legs ≥ the stage-machine floor. Straight lines
  because the planner itself may use a "direct" estimate when no road is open (found by the test: a road-based bound
  was beaten). A lower bound, labelled "not achievable live" — loose by construction.
- `scripts/regret_runs.py [--limit 20]` reads runs + frames through the backend API, replays each under first_free /
  greedy / optimal (+ its own policy when the frame has it → fidelity = mean |replayed − recorded|), regret = mean −
  mean bound → `models/ops_regret_v1.json`. First run 2026-10-11: 7 stored runs (Delhi, Chennai, Guwahati); "best
  replay" was greedy in all 7; runs recorded before this change say "policy unknown" for fidelity.
- History tab `RegretCard`. Tests: `test_regret.py` (faithful frames → replay with 0 difference; bound never beaten).


**Goal.** For a stored run (F5), replay the same SOS arrivals and road closures with the best dispatch in hindsight and
measure how many minutes the live decisions lost — a "regret" score per run and per policy.

**Work.**
- `ops_sim.from_frames(run_id)` (F16 core) rebuilds arrivals / closures from stored frames; replay with each policy +
  an offline assignment that knows all arrivals in advance (labelled "hindsight bound, not achievable live").
- History tab: regret per run. `models/ops_regret_v1.json` for the paper.

**Tests.** A run replayed with its own policy reproduces its recorded times within tolerance; hindsight ≤ every policy.

**Done checklist**
- ☐ Faithful replay check passes
- ☐ Regret shown, hindsight labelled; paper decision

## F35 — AI Assistant accuracy evaluation  📋 PLANNED (paper)

**Goal.** Measure how often the AI Assistant states a number or fact that is not in the run's facts, and how often it
refuses a question it could answer.

**Work.**
- `scripts/eval_ai_assistant.py`: ~200 questions generated from a seeded run's state (people, shelters, roads, dams),
  each with the true answer computed from state; run through `POST /api/simulation/ai`; score exact / grounded / wrong /
  refused. With and without `grounded()` (ablation). Output `models/ai_eval_v1.json` with model name + date.
- Needs the Groq key (from `.env`); with no key the script says so and stops — no simulated answers.

**Tests.** Scorer on hand-made answers; question generator deterministic with a seed.

**Done checklist**
- ☐ Question bank from real state, seeded
- ☐ Measured rates + ablation; paper decision

## F36 — Automatic browser tests (Playwright)  📋 PLANNED (next after F16)

**Goal.** Turn the open "click it through in the browser" items into automatic tests: every tab, every city, the
phone pages and the driver page, in a real (visible-mode) browser, failing on any console error or error banner.

**Work.**
- New dev dependency `@playwright/test` (+ browser download) — **ask the user before installing**.
- `frontend/e2e/`: `simulation.spec.js` (each city: pick → Run → every tab, no console error, Live counters move),
  `phone.spec.js` (`/sos` validation, offline queue with `context.setOffline`, `/safe`), `driver.spec.js` (manual mode
  accept / reject). Starts backend + vite or reuses running ones; seeds a short scenario.
- The page must be visible (`document.hidden = false`) — Playwright pages are; this avoids the hidden-tab pause.
- `npm run e2e`; documented in CLAUDE.md commands. Not part of `vitest run`.

**Tests.** The specs themselves; one deliberately broken fixture proves a console error fails the run.

**Done checklist**
- ☐ Dependency approved and installed
- ☐ All cities + all tabs + phone + driver specs green
- ☐ CLAUDE.md commands updated

## F37 — Login, roles and action history  📋 PLANNED

**Goal.** Separate logins for admin, dispatcher and driver (the driver page is open to anyone with the link today), and
an audit log of who changed what (roads, shelters, overrides, playbook, merges).

**Work.**
- `backend/deps/auth.py`: roles on top of `RequireOperator`; a driver token is scoped to one unit. Passwords hashed
  (passlib / bcrypt — ask before adding), sessions as signed tokens, accounts created by an admin CLI script; test
  accounts only in a seed file for local development.
- `audit_log` collection: `{at, user, role, action, target, before, after, run_id}` written by every mutating endpoint;
  History tab shows it per run.
- HTTPS on the VPS is part of this feature (GPS and logins need it) — deploy only when the user asks.

**Tests.** Each endpoint rejects the wrong role; driver token cannot act on another unit; every mutation writes one audit
row; public endpoints unchanged.

**Done checklist**
- ☐ Roles + scoped driver tokens; dependency asked
- ☐ Audit log on every mutation, visible per run
- ☐ Tests; deployment only when asked

---

## Tomorrow — start here (written 2026-10-11)

Same steps as "Next session — start here" in `CLAUDE.md`:
1. Check the F12 batch: all six `models/ops_montecarlo_v1_<city>.json` + `route_benchmark_v1_<city>.json` present?
   (Delhi done at handoff.) Copy each city's numbers into F12 like Delhi; re-run any missing city.
2. Build **F16 what-if planner** (skills `agents-ai`, `rescue-ops`, `testing`) — first move the simulator core into
   `backend/services/ops_sim.py` with `test_monte_carlo.py` still passing.
3. Then **F36 Playwright browser tests** — ask before installing `@playwright/test`.
4. After each feature: tests + build, browser check in a visible tab, tick the checklist, write "As built", update the
   status table and the test counts in `CLAUDE.md`. Commit / push only when the user asks.
