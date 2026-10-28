# NEW_FEATURES.md — planned features (implementation guide)

Six features picked on 2026-10-08 from the 10-idea list (ideas 2, 3, 4, 5, 7, 8).
Each section says **what exists today**, **exactly what to change**, the
**API contract**, **tests**, and a **done checklist**. Work them in the
order below — later ones reuse earlier ones.

| # | Feature (idea no.) | Size | Depends on |
|---|---|---|---|
| F1 | Block a road on the map → live reroute (idea 2) | M | — |
| F2 | Close / shrink a shelter live → reallocation (idea 3) | M | F1's "reroute" helper |
| F3 | Driver app: Accept / Reject (idea 4) | M | — |
| F4 | Citizen SOS phone page with GPS + photo (idea 5) | M | — |
| F5 | Replay a past run + persistent playbook (idea 7) | L | — |
| F6 | Measured route comparison benchmark (idea 8) | M | F1 (blockage knob) |

Status: **F1 done (2026-10-08)** · **F2–F6 built 2026-10-09** (tests + build green; not yet clicked through in the
browser — see each "As built"). Open item: F6 report / paper update (needs a decision, see F6).
**Round 2 F7–F15 built 2026-10-09 → 2026-10-11** (tests + build green; not yet clicked through in the browser — see
each "As built" at the end of the file).

**Round 2 (picked 2026-10-09):** ideas 2, 3, 4, 5, 6, 8, 9, 10 from the second 10-idea list **plus** "not only Delhi —
the most flood-hit Indian cities on real maps". Planned as F7–F15 at the end of this file ("Round 2").

## Rules that apply to every feature (from CLAUDE.md)

- One authoritative state: everything lives on `SimulationEngine` (`backend/simulation/engine.py`)
  and is served by `engine.state()`; the 1.2 s poller (`frontend/src/state/simStore.js`) is the only poller.
  New UI reads `state`, never keeps its own copy.
- `backend/services/person_ops.py` is the only stage machine. Do not add a second simulator.
- Routes come from the real graph (`person_ops.road_route` → Yen candidates → QAOA choice). Never draw a decorative route.
- No fabricated numbers. Anything synthetic (surge callers, benchmark trips) is labelled synthetic.
- No hospitals, phone numbers or boats.
- Mutating endpoints use `RequireOperator` (`backend/deps/auth.py`) + a `limiter.limit(...)`, except F4's public SOS which has its own stricter limits.
- `uvicorn --reload` restarts the backend on every save and wipes the run — re-run the scenario after backend edits.
- New MAS messages need a stable `key` (`MultiAgentSystem._say` dedupes by key) or they repeat every poll.
- After each feature: `python -m pytest -q` and `cd frontend && npx vitest run && npx vite build`.

---

## F1 — Block a road on the map → live reroute (idea 2)  ✅ DONE 2026-10-08

**As built** (differs from the plan below in these points):
- `engine.roads_now()` is the one road list for the run = seed `ROADS` + `auto_blocked` (flood rules, grow-only per run)
  + `road_overrides` (operator wins). `start()` re-syncs Mongo `roads` to the seed — closures used to leak between runs.
  The pipeline rule honours `obs["road_overrides"]` and no longer mutates the seed `ROADS` list.
- `person_ops.road_route` returns `road_ids`; when the nearest junction is cut off it tries the 3 nearest junctions at
  each end. A disconnected trip returns `method: "direct", no_open_road: true`.
- `person_ops.reroute(rows, roads, reason, improve=False)` + `position_on` + `leg_progress`. **No open road →
  the plan is kept and `route_alert` is set (red "No open road" message); a straight line is never adopted as a
  re-route.** Allocation / pickup with no open road also set `route_alert`. Reopen (`improve=True`) re-plans alert
  legs and any leg ≥ 0.5 min faster.
- Operator re-plan runs **before any await** in `set_road` (the tick loop interleaved and stole the re-plan once).
  The loop re-plans only on NEW flood closures (operator roads excluded).
- API: `GET /api/simulation/roads`, `POST /api/simulation/road {road_id, blocked | clear}`; state has
  `road_status` (segments, source, `active_legs`) and `road_log`.
- MAS `announce_road` (kind `road`, yellow → pops up), per-unit "Rerouted", red "No open road", playbook trigger
  `ROAD_BLOCKED`.
- UI: `RoadControlPanel.jsx` (Routes tab), clickable road lines + popup in `LiveRescueMap.jsx`, "⛔ Block busiest
  road" in `LiveControls.jsx`, re-route / no-road chips + "Re-routed" filter in `RouteCasesPanel.jsx`.
- Tests: `backend/tests/test_reroute.py` (10), `RoadControlPanel.test.jsx` (3).
- Known limit: when the flood has closed most roads, blocking the last link leaves many legs with "no open road" —
  that is correct; F2 (shelter reallocation) is what moves those people to a reachable shelter.


**Goal.** The operator clicks a road on the Routes / Live map and toggles it Blocked / Open. Every unit whose
remaining route uses that road gets a new route at once (QAOA over fresh Yen candidates); the map, ETAs,
the person's stage timer and the notifications all update together.

### What exists today
- Roads: `backend/services/seed.py` `ROADS` (R01…; `road_id`, `name`, `lat/lon`, `blocked`, `flood_exposure`, `traffic`, `accessible`).
- Each tick `_loop` in `engine.py` auto-blocks roads with `flood_exposure >= 0.85 - obs["blockage"]` and upserts them to Mongo `roads`.
  It only ever sets `blocked=True` (never re-opens).
- `state()` passes `ctx = {"teams", "roads": snap.roads}` into `person_ops.advance_all`.
- Routes are computed **once**, in `person_ops._assign` (`route_to_person`, `route_to_shelter`, `eta_min`, `eta_to_shelter_min`).
- `route_engine.build_graph(roads)` drops blocked roads; edges carry `flood_exposure`.

### Backend
1. **Engine state** (`engine.py`): add `self.road_overrides: dict[str, bool] = {}` in `__init__` and clear it in `start()`.
2. **Apply overrides last** in `_loop`, right after the auto-block loop:
   `if r["road_id"] in self.road_overrides: r["blocked"] = self.road_overrides[...]; r["accessible"] = not r["blocked"]`.
   An operator "Open" must win over the auto-block, otherwise the next tick re-blocks it.
   Also apply the same overrides to `snap["roads"]` in `state()` before building `ctx` (the snapshot is from the last tick).
3. **Reroute helper** in `person_ops.py` (pure, testable):
   ```python
   def reroute(rows, roads, at, reason) -> list[str]:
       """Recompute the remaining legs of every active row whose current
       polyline crosses a now-blocked road. Returns changed citizen names."""
   ```
   - `assigned`: recompute both legs from `unit_base` (same as `_assign`, keep unit + shelter).
   - `en_route`: the unit is mid-leg. Current position = `lerp(route_to_person.points, progress)` where
     `progress = (now - ops_stage_at) / ops_stage_seconds` (same formula the frontend uses — put the lerp in
     a small shared function `position_on(points, frac)`). New `route_to_person = road_route(current_pos, person)`;
     set `ops_stage_at = now`, `ops_stage_seconds = leg_seconds(new.sim_minutes)`; also recompute `route_to_shelter`.
   - `to_shelter`: same, from current position to the shelter.
   - To know which road a polyline uses, store the road ids on the route: in `road_route`, carry the edge
     `road_id` list into the returned dict (`route["road_ids"]`). Rows routed before this change have no
     `road_ids` → reroute them if any blocked road is within ~150 m of the polyline (fallback), or simply always reroute them once.
   - Add a journey entry `REROUTED` (`_journey(row, at, "REROUTED", f"{reason}: +{delta} min", "Route Agent", "info")`)
     and keep `row["reroutes"] = [{at, reason, old_min, new_min, method}]`.
4. **Endpoint** (`backend/api/simulation.py`):
   ```
   POST /api/simulation/road   {road_id: "R02", blocked: true}      → state
   POST /api/simulation/road   {road_id: "R02", clear: true}        → hands the road back to the physics
   ```
   Validate `road_id` against `ROADS`. Handler: set override → build roads → `reroute(...)` → `mas.announce_reroute(...)` → broadcast.
   Add `RoadOverrideRequest` to `backend/schemas/common.py`.
5. **MAS** (`backend/agents/mas.py`): `announce_reroute(run_id, road, changed)` — Route Agent → Ambulance/Rescue,
   yellow (`"Road R02 blocked — 3 units rerouted"`), key `f"road:{road_id}:{blocked}:{tick}"`. Add a `ROAD_BLOCKED`
   trigger to `DEFAULT_PLAYBOOK` so it is editable like the others.
6. **State**: add `"road_status": [{road_id, name, lat, lon, blocked, source: "physics"|"operator"}]` to `state()`.

### Frontend
- `components/rescue/LiveRescueMap.jsx`: draw road markers from `sim.road_status` (red ⛔ blocked / green open, operator ones outlined).
  Click → small popup with **Block** / **Open** / **Back to physics**. Cache the `L.divIcon`s (CLAUDE.md Leaflet rules).
- `services/api.js`: `setRoad(road_id, body)`.
- `RouteCasesPanel.jsx`: show a "Rerouted" chip and the `reroutes[]` list (old → new minutes, reason).
- Add a "Block busiest road" quick button to `components/agents/LiveControls.jsx` (picks the road used by most active routes — computed from state, not hard-coded).

### Tests
- `backend/tests/test_reroute.py`: blocking a road on a row's path changes its polyline and `ops_stage_at`;
  a row not using the road is untouched; `rescued` rows are never touched; "Open" override beats auto-block.
- `rescueOps.test.js`: a rerouted row (new `ops_stage_at`) interpolates from progress 0 on the new polyline.

### Done checklist
- ☑ Override wins over auto-block on the next tick
- ☑ Moving unit continues from where it is (no jump back to the depot)
- ☑ ETA, map line, people table and notification change in the same poll
- ☑ Playbook has `ROAD_BLOCKED`
- ☑ Tests + build green

---

## F2 — Close / shrink a shelter live → automatic reallocation (idea 3)  ✅ BUILT 2026-10-09

**As built:**
- `engine.shelter_overrides {name: {closed, capacity}}` + `shelter_log`, cleared in `start()`; `engine.set_shelter()`
  re-plans BEFORE any await; `engine.ops_ctx()` is now the one ctx for every stage-machine call.
- `person_ops.shelter_registry(overrides)` (adds `closed`, `base_capacity`), `_shelter_options` / `_pick_shelter(..., overrides, exclude)`,
  `_reachable_shelter()` (nearest open shelter with seats AND an open road; used at allocation too), `reallocate()`.
- `reallocate` targets, in order: closed → over capacity (newest `timestamps.assigned` released first) → unreachable
  (`route_alert.leg == "route_to_shelter"`, moved only if another shelter IS reachable) → `shelter_wait`.
  No seats anywhere → `shelter_wait` + `ops_wait_reason = "No shelter with free seats"`; a `to_shelter` row then HOLDS at the
  end of its leg (advance_all skips it) until a shelter frees up. `rescued` rows never move.
- Road closures (operator + flood) also call `_reallocate`, so F1's "No open road to the shelter" legs move automatically.
- API `POST /api/simulation/shelter {name, closed?, capacity?, clear?}`; state has `shelter_overrides`, `shelter_log`;
  board rows have `closed`, `base_capacity`, `operator`, `moved_away`. MAS `announce_shelter_change` + `SHELTER_CLOSED` playbook.
- UI: `ShelterCapacityPanel` Edit → Close / Reopen / Set capacity / Reset (bar: registry | delivered | incoming | free),
  🚫 cached map icon, "🏠 shelter moved" chip in `RouteCasesPanel`, AI facts say CLOSED.
- Tests: `test_reallocate.py` (9), `ShelterCapacityPanel.test.jsx` (3).

**Goal.** The operator closes a shelter (or lowers its capacity). Everyone heading there is moved to the
nearest shelter with free seats, units get new routes, and the shelter board shows it live.

### What exists today
- `person_ops.shelter_registry()` builds `{name: {lat, lon, capacity, occupancy}}` from `rescue_desk.SHELTERS` + `seed.SHELTERS` (static).
- `_pick_shelter(row, rows)` = nearest shelter in `SHELTER_POOL` with `capacity - occupancy - committed >= people`.
- `shelter_allocation_board(rows)` serves the live seat view. CLAUDE.md: backend occupancy is a growth curve,
  **report "delivered this run" separately** — keep that split.

### Backend
1. `engine.py`: `self.shelter_overrides: dict[str, dict] = {}` → `{name: {"closed": bool, "capacity": int|None}}`; clear in `start()`.
2. `person_ops.py`: give `shelter_registry(overrides=None)` and `_pick_shelter(row, rows, overrides=None)` an overrides argument
   (closed → skipped; capacity replaced). Pass it through `ctx["shelter_overrides"]` from `state()` → `advance_all` → `_assign`.
   Also pass to `shelter_allocation_board(rows, overrides)` so the board shows `closed` and the edited capacity.
3. `reallocate(rows, overrides, ctx, at) -> list[str]`:
   - `assigned` / `en_route` rows whose `shelter_name` is closed (or now over capacity — release the latest-assigned first):
     `_pick_shelter` again; if found, replace `shelter_*` and recompute `route_to_shelter`; `en_route` keeps its current leg.
   - `to_shelter`: reroute from the current position (reuse F1's `position_on` + `road_route`).
   - No shelter left → keep the row moving but set `ops_wait_reason = "No shelter with free seats"`; MAS posts red.
   - `rescued`: already delivered — never move them; the board shows "delivered before closure".
   - Journey entry `SHELTER_CHANGED` (old → new, reason).
4. Endpoint: `POST /api/simulation/shelter {name, closed?: bool, capacity?: int, clear?: true}` (validate name against `SHELTER_POOL`,
   `capacity >= 0`). Then `reallocate` → `mas.announce_shelter_change` (Shelter Agent, yellow; red when nobody can be placed) → broadcast.
5. Playbook trigger `SHELTER_CLOSED`.

### Frontend
- `components/rescue/ShelterCapacityPanel.jsx`: per shelter an **Edit** button → Close / Reopen / capacity input / Reset.
  Closed shelters greyed with a 🚫 chip; bars keep "delivered this run" and "allocated" as separate segments.
- `LiveRescueMap.jsx`: closed shelter icon (cached icon variant).
- People table / AI cards: show `SHELTER_CHANGED` in the timeline.
- `ai_assistant.py`: `_shelters()` facts include `closed` so "is X shelter open?" is answerable.

### Tests
- `test_reallocate.py`: closing a shelter moves all its `assigned` rows to the nearest open one; `rescued` rows unchanged;
  capacity cut releases the newest allocations first; with every shelter closed, rows get the wait reason (no crash).
- Board test: closed shelter shows `closed: true` and 0 seats free.

### Done checklist
- ☑ Close → people reassigned within one poll, map lines change (tests; browser check pending)
- ☑ Reopen restores the original capacity (Reset clears the override → seeded capacity)
- ☑ Delivered-this-run never blended with backend occupancy
- ☑ AI tab knows a shelter is closed

---

## F3 — Driver app: Accept / Reject (idea 4)  ✅ BUILT 2026-10-09

**As built:**
- `engine.accept_mode` ("auto" | "manual", reset to auto by `start()`), `set_accept_mode`, `unit_view`, `driver_answer`.
- `person_ops.ACCEPT_TIMEOUT_SECONDS = 20`; manual mode: `_due()` of an `assigned` row = request time + timeout, and when it
  fires `reject(..., "no answer")` runs. `accept()` calls the one `_transition(row, "en_route")` (sets `accepted_via`).
  `reject()` records `rejected_units` / `rejections[]`, frees the unit and re-runs `_assign` right away; `_assign` skips
  rejected ambulances and, for a rejected cluster team, falls back to the nearest other depot.
- API: `POST /api/simulation/accept-mode {mode}`, `GET /api/simulation/unit/{unit}`, `POST .../accept`, `POST .../reject {reason}`
  (409 when no request is waiting). MAS: "Driver rejected" (yellow), "No answer → reassigned" (red from the 2nd time);
  "Unit dispatched" key now includes the unit so a re-offer announces again.
- UI: `/driver/:unit` (lazy, no app chrome, 2 s poll, mini map, countdown from backend `seconds_left`), Auto-accept /
  Drivers decide toggle + "Open driver view ↗" links in `FleetPanel`, answer-by time from backend timestamps,
  rejections listed above `RescueStepper`. PDF `STAGE_TIMES` has `rejected`.
- Tests: `test_driver_accept.py` (10), `DriverApp.test.jsx` (3).

**Goal.** A phone-sized page per unit (`/driver/Ambulance%20Unit%203`). When a job arrives the driver sees the
person, water depth, route and shelter, and taps **Accept** or **Reject**. Reject (or no answer in time) sends the job
to the next free unit. The control room still works hands-free in "auto-accept" mode.

### What exists today
- `_transition` → `assigned`: sets `dispatch_request`, `driver_accepted=False`, journey `REQUEST_SENT`, stage lasts `MOBILISE_SECONDS`.
- `assigned → en_route` happens automatically when due; that transition is treated as the driver accepting
  (`driver_accepted=True`, `accepted_at`, `timestamps["accepted"]`).
- `fleet_board(rows)` lists units free / busy with their job.

### Backend
1. Engine setting `self.accept_mode = "auto"` (`"auto" | "manual"`), toggled by `POST /api/simulation/accept-mode {mode}`; served in `state()`.
2. `person_ops`:
   - In `advance_all`, when `ctx["accept_mode"] == "manual"` a row in `assigned` does **not** advance on its timer. Instead, if
     `now - ops_stage_at > ACCEPT_TIMEOUT_SECONDS` (new constant, e.g. 20 wall s) → treat as a reject with reason `"no answer"`.
   - `accept(row, at)` → runs the existing `en_route` transition (keep one code path — call `_transition(row, "en_route", ...)`).
   - `reject(row, rows, ctx, at, reason)` → `row.setdefault("rejected_units", []).append(unit)`; journey `REJECTED`; clear unit fields;
     back to `queued` and call `_assign` with the rejected units excluded (`_assign` gains `exclude=set(...)` used in the ambulance
     `free` list and for rescue teams fall back to the nearest other depot). No unit free → `ops_wait_reason`.
3. Endpoints (operator auth; a real driver login is idea 10, out of scope here — say so in the UI):
   ```
   GET  /api/simulation/unit/{unit_name}            → {unit, status, job: {citizen_name, age, people, water, lat, lon,
                                                       route_to_person, route_to_shelter, shelter_name, requested_at, timeout_s}}
   POST /api/simulation/unit/{unit_name}/accept     → state
   POST /api/simulation/unit/{unit_name}/reject     {reason} → state
   ```
   Look the row up by `unit_name` + `ops_status == "assigned"`; 409 if the job already moved on (double tap).
4. MAS: `_on_person` already has the accepted message; add `REJECTED` (yellow, key `rej:{name}:{unit}`) and
   "no answer → reassigned" (red when it happens twice for the same person).

### Frontend
- New page `frontend/src/pages/DriverApp/DriverApp.jsx`, route `/driver/:unit` in `App.jsx` (lazy-loaded). Mobile-first:
  big job card, a small Leaflet map with both legs, countdown to timeout, two big buttons. Polls
  `GET /api/simulation/unit/{unit}` every 2 s (separate page, so not a second poller on `/simulation`).
- `/simulation` → Live tab: an **Auto-accept / Drivers decide** toggle; `FleetPanel.jsx` gets an "Open driver view ↗" link per unit
  and shows "waiting for driver (12 s)".
- `RescueStepper.jsx`: show "Rejected by Unit 2 → Unit 5" in the timeline.

### Tests
- `test_driver_accept.py`: manual mode holds `assigned`; accept → `en_route` with `accepted_at`; reject → new unit, rejected unit
  excluded; timeout → reassigned; second accept on a moved job → 409; auto mode unchanged (existing tests keep passing).
- Vitest: DriverApp renders the job and disables buttons while posting.

### Done checklist
- ☑ Auto mode behaves exactly as today (all earlier tests unchanged and passing)
- ☑ Manual mode: accept / reject / timeout reflected in fleet, notifications, PDF (tests; map/browser check pending)
- ☐ Works on a phone width (360 px) — CSS is phone-first (max 480 px, 64 px buttons) but not yet checked on a device

---

## F4 — Citizen SOS phone page with GPS + photo (idea 5)  ✅ BUILT 2026-10-09

**As built:**
- `backend/api/public_sos.py`: `POST /api/public/sos` (multipart; 5/minute per IP + 10 per IP per run; 409 no running run;
  422 outside the road-network bbox + 0.05°; 415 bad magic bytes; 413 > 3 MB), `GET /api/public/sos/{ticket}` (32-hex
  ticket only, this person's status only), `GET /api/simulation/photo/{ticket}` (operator).
- Photos re-encoded by Pillow (EXIF dropped, `exif_transpose`, ≤ 1600 px) to `uploads/sos/{run_id}/{ticket}.jpg`
  (git-ignored). GridFS was NOT used — local files only.
- `engine.add_citizen_sos` carries `ticket`, `photo_url`, `source`, `accuracy_m` (also in `SYNC_KEYS`); MAS "New SOS via 📱 citizen app".
- UI: `/sos` (lazy, no chrome): form, Share my location (high accuracy, accuracy circle, draggable pin, tap-to-place when
  denied), camera input + client resize, status screen polling every 5 s with the ticket in `localStorage`.
  📱 badge + photo in People table and AI person card; QR card (`qrcode` npm, generated locally) on the Live tab.
- `DEPLOYMENT.md`: HTTPS section (GPS needs https), photo retention note. `Pillow` added to `backend/requirements.txt`.
- Note: `vite` listens on 127.0.0.1 locally, so a phone on the LAN cannot reach the dev server without `--host`.
- Tests: `test_public_sos.py` (6), `CitizenSos.test.jsx` (3).

**Goal.** A public page `/sos` a citizen opens on a phone: name, age, people, water depth, **Share my location**,
optional photo → the person appears in the live run at `queued` and goes through the normal pipeline.

### What exists today
- `POST /api/simulation/sos` (`CitizenSosRequest`: name, age 0–120, lat, lon, people 1–50, water_level_note) → `engine.add_citizen_sos`
  — appends at `queued`, nearest existing cluster, no re-clustering. It is **operator-only** (`RequireOperator`).
- No public endpoint, no file upload anywhere.

### Backend
1. New router `backend/api/public_sos.py` (include it in `backend/main.py`):
   ```
   POST /api/public/sos      multipart: name, age, people, water, lat, lon, accuracy_m, photo? (jpeg/png/webp ≤ 3 MB)
   GET  /api/public/sos/{ticket}   → {stage_text, unit, shelter, eta_min}   (only this person's status)
   ```
   - No auth, but `limiter.limit("5/minute")` per IP plus a per-IP cap per run; reject when no run is `running` (409 "No live operation").
   - Validate lat/lon inside the simulation bounding box (derive from `seed.GRAPH_NODES` min/max + margin) → 422 otherwise.
   - Photo: check magic bytes (not just the extension), re-encode with Pillow to strip EXIF, store as
     `uploads/sos/{run_id}/{ticket}.jpg` (add `uploads/` to `.gitignore`), or Mongo GridFS when connected.
   - Call `engine.add_citizen_sos({..., "mode": "citizen"}, quick=False)`; return a random `ticket` (uuid4 hex) stored on the row
     (`row["ticket"]`) — the status endpoint looks up by ticket so names are never enumerable.
   - Add `ticket`, `photo_url`, `source: "citizen"` to `SYNC_KEYS`.
2. Serve photos via `GET /api/simulation/photo/{ticket}` (operator only).
3. MAS: SOS received message says "📱 citizen app" for `source == "citizen"`.
4. `.env`/`DEPLOYMENT.md`: note that the VPS must serve over HTTPS for browser geolocation to work (geolocation is blocked on plain
   http except localhost) — put nginx + Let's Encrypt in front of :5173 and :8000.

### Frontend
- `frontend/src/pages/CitizenSos/CitizenSos.jsx`, route `/sos` — no app chrome, large inputs, `navigator.geolocation.getCurrentPosition`
  (high accuracy, show the accuracy circle on a mini map, allow dragging the pin), camera input `accept="image/*" capture="environment"`,
  client-side resize to ≤ 1600 px before upload.
- After submit: status screen polling `GET /api/public/sos/{ticket}` every 5 s (Waiting → Unit on the way → Going to shelter → Safe).
  Keep the ticket in `localStorage` (wrapped in try/catch) so a refresh keeps the status.
- `/simulation` People tab + AI person card: 📱 badge and photo thumbnail for citizen SOS.
- QR code on the Live tab linking to `/sos` (generate with a small lib from cdnjs or a tiny QR component) for the demo.

### Tests
- `test_public_sos.py`: valid post appears at `queued`; outside bbox → 422; no running run → 409; non-image photo → 415;
  ticket status hides other people; rate limit returns 429.
- Vitest: form validation, geolocation denied → manual pin message.

### Done checklist
- ☑ Phone → SOS → joins the run at `queued`, normal pipeline (test runs the real `add_citizen_sos`; phone check pending)
- ☑ EXIF stripped, size/type checked, uploads ignored by git
- ☑ HTTPS note in DEPLOYMENT.md

---

## F5 — Replay a past run + persistent playbook (idea 7)  ✅ BUILT 2026-10-09

**As built:**
- `backend/services/replay.py` (`ReplayStore`, `store`): `record(engine, cause)` writes one compact frame
  (`simulation_frames`, `seq` 1-based) + drains `mas.outbox` into `mas_messages` + upserts the run summary into
  `simulation_runs`. Called from `_loop` once per tick, at completion, and after SOS / surge / override / road / shelter /
  driver answer / accept-mode. Mongo down → last run only, ring of 400 frames / 600 messages, `persisted: false`.
- MAS `_say` appends to `outbox` (bounded 2000); the engine drains it — no Mongo call inside the 1.2 s poll.
- Playbook: `PUT /api/simulation/playbook` saves `settings {_id: "playbook"}` (`{reset: true}` deletes it) and returns
  `persisted`; lifespan loads it via `mas.load_playbook` (merged over defaults). Retention: keep newest 50 runs (startup, printed).
- API: `GET /api/simulation/runs`, `/runs/{id}`, `/runs/{id}/frames?start=&end=&limit=` (paged by `seq`, ≤ 200),
  `/runs/{id}/messages`, `/runs/{id}/report.pdf` (services/report.py from stored frames).
- UI: 📼 History tab → `components/replay/ReplayPlayer.jsx` (run list, ▶/⏸, slider, 1×/4×/16×), adapter
  `state/replay.js frameToView()` feeds the EXISTING `deriveRescueOps` / `LiveRescueMap` / `FleetPanel replay` /
  `ShelterCapacityPanel` (no `onState` → read-only). Purple "REPLAY — not live" banner. Road lines are not replayed
  (frames keep only `roads_closed` ids). Compare mode (stretch) not built.
- Tests: `test_replay.py` (6), `replay.test.js` (3), `ReplayPlayer.test.jsx` (1).

**Goal.** Every run is saved. A **History** tab lists past runs; opening one gives a time slider that replays the map,
people stages, notifications and charts exactly as they were. The playbook survives restarts.

### What exists today
- Mongo via Motor is optional (`backend/database/mongo.py`; `insert`, `upsert`, `find_many` no-op/fallback when disconnected).
- `simulation_runs` already gets `{run_id, params, status}` at start and `{status, after, before}` at completion.
- `engine.history` (per tick), `self.events`, `mas` messages (capped 200) live only in memory; playbook is in-memory in `mas.py`.

### Backend
1. **Frames.** In `_loop`, after `hub.broadcast(...)` each tick, save a compact frame:
   `simulation_frames {run_id, tick, at, probability, tier, rain, river, dam, citizens: [{name, lat, lon, ops_status, unit_name,
   shelter_name, route ids/points}], fleet_board, shelter_allocation, counts}`. **Do not** store the full `state()` (too big).
   Also save a frame on every operator action (SOS, surge, override, road, shelter) with `cause`.
   Index `(run_id, tick)` in `mongo.ensure_indexes`. When Mongo is down, keep the last run in an in-memory ring buffer (≤ 400 frames)
   and say "not persisted" in the UI.
2. **Messages.** Persist every new MAS message (`mas_messages {run_id, id, at, severity, kind, title, text, from, to}`) — do it in
   `_say` through a queue the engine flushes once per tick (no Mongo call inside the 1.2 s `state()` poll).
3. **Playbook.** `set_playbook` writes `settings {_id: "playbook", data}`; on startup (`backend/main.py` lifespan) load it into
   `mas` before the first run. `reset` deletes the doc.
4. Endpoints:
   ```
   GET /api/simulation/runs?limit=20            → [{run_id, scenario, started_at, status, ticks, sos, rescued, peak_probability}]
   GET /api/simulation/runs/{run_id}            → params, before/after, summary
   GET /api/simulation/runs/{run_id}/frames?from=&to=   → frames (paged)
   GET /api/simulation/runs/{run_id}/messages   → messages
   GET /api/simulation/runs/{run_id}/report.pdf → reuse services/report.py with stored data
   ```
5. Retention: keep the last 50 runs (delete older frames in a startup task) — print how many were removed.

### Frontend
- New tab `history` (📼 History) in `SIM_TABS` (`SimulationLab.jsx`), rendered by `ScenarioOutputs` (hide the live slot like `ai`).
- `components/replay/ReplayPlayer.jsx`: run list → open → slider + ▶/⏸ + speed (1×/4×/16×). It renders the **existing**
  components (`LiveRescueMap`, `ShelterCapacityPanel`, `FleetPanel`, message list) with a frame converted to the same shape
  as `sim` — write one adapter `frameToView(frame)` so the components are reused, not copied.
- A clear **REPLAY — not live** banner (CLAUDE.md: no static results presented as live); no edit controls in replay.
- Compare mode (stretch): two runs side by side, KPI deltas.

### Tests
- `test_replay.py`: frames saved per tick with fallback buffer when Mongo is off; frames endpoint pages correctly;
  playbook round-trips through `settings` and reset removes it.
- Vitest: `frameToView` produces the shape `LiveRescueMap` expects; banner shown.

### Done checklist
- ☑ Restart backend → playbook edits still there (round-trip test with a fake store; needs MongoDB running for real)
- ☑ Past run replays map + notifications in step (messages filtered to `at <= frame.at`; browser check pending)
- ☑ Replay clearly labelled, read-only
- ☑ Storage bounded (retention 50 runs in Mongo; 400-frame ring in memory)

---

## F6 — Measured route comparison benchmark (idea 8)  ✅ BUILT 2026-10-09 (report / paper NOT updated)

**As built:**
- `person_ops.route_candidates()` extracted from `road_route` (same Yen candidates, now also `hazard_km`); the live
  app and the benchmark share it.
- `scripts/bench_routes.py` → `models/route_benchmark_v1.json` (deterministic: same seed → identical file) +
  `models/route_benchmark_v1.timing.json` (cold `qaoa_choose` wall ms, `_solve` cache cleared per trip; varies per run).
  Unroutable trips are split into `no_open_road` and `same_junction`.
- `GET /api/benchmark/routes` (`backend/api/benchmark.py`; `?details=true` for every trip). Algorithms tab:
  `RouteBenchmarkCard.jsx` (travel + hazard bars, agreement line, per-level table).
- **Measured result (200 synthetic trips, seed 42):** the road graph is small (17 junctions, 8 roads), so trips have at
  most 2 candidates, and only at 0 % blockage (165 of 195 routed trips). There QAOA = exhaustive on 100 % of them and
  = Dijkstra on 99.39 % (1 trip differs: a lower-hazard, slightly longer route; means 59.719 vs 59.702 min, hazard
  4.595 vs 4.606). From 10 % blockage (R08 closed) every
  trip has ONE candidate, so all methods coincide; at 30 %, 87 of 200 trips have no open road.
- Tests: `test_bench_routes.py` (5), `RouteBenchmarkCard.test.jsx` (2).
- **Not done:** project report / IEEE paper. The result says QAOA has at most 2 options on this graph, so putting it
  in the paper is an editorial decision for the authors (it is honest, but it does not support a novelty claim).

**Goal.** A seeded, repeatable experiment that compares route choices on the real road graph and produces numbers you
can put in the report and paper: **Dijkstra (shortest)**, **QAOA choice**, **exhaustive best over the same candidates**,
and **direct line** (reference only), across blockage levels.

### What exists today
- `person_ops.road_route(a, b, roads)` → Yen candidates (`QAOA_CANDIDATES = 4`), `candidate_costs`, `qaoa_choose`;
  stores `quantum` diagnostics (`matches_exhaustive`, `agrees_with_dijkstra`, probabilities).
- `scripts/benchmark_20_models.py` is the pattern for an experiment script writing `models/*.json`.

### Backend / script
1. `scripts/bench_routes.py` (CLI: `--trips 200 --seed 42 --blockage 0,0.1,0.2,0.3 --out models/route_benchmark_v1.json`):
   - Trips: seeded random (origin, destination) pairs — origins from SOS-like points around `seed.ZONES`, destinations from
     `SHELTER_POOL` coordinates. Label them **synthetic trips**.
   - Blockage: reuse the engine's rule (`flood_exposure >= 0.85 - blockage` → blocked) so the benchmark matches the live sim.
   - For each trip: candidates once, then per method record `travel_min`, `hazard` (sum of edge `flood_exposure` × length),
     combined cost (same formula as `candidate_costs`), `km`, solver wall time; QAOA also `chosen_probability`, `matches_exhaustive`.
   - Summary per blockage level: mean/median/p95 travel, mean hazard, % trips where QAOA = exhaustive best, % = Dijkstra,
     unreachable count, mean QAOA time. Store `seed`, `trips`, git commit, `QAOA LAYERS/SHOTS/PENALTY`.
2. Endpoint `GET /api/benchmark/routes` → serves the JSON file (404 with a "run scripts/bench_routes.py" hint if missing).
   **Never** run the benchmark inside a request.

### Frontend
- Algorithms tab (`ScenarioOutputs.jsx` → algorithms section): a "Route choice benchmark" card — grouped bar chart
  (travel / hazard per method per blockage), line chart "% QAOA = exhaustive" vs blockage, and the settings used.
  Read from the endpoint; show "not generated yet" when missing. Use `config/chartTheme.js`.

### Report and paper (only via the skills)
- Project report: add the table through `.claude/skills/project-report/scripts/content.py` and rebuild — numbers from the JSON only.
- IEEE paper: edit `paper.tex` + `build_paper_docx.js`; add the JSON to what `verify.py` checks.
- Wording: QAOA is **simulated classically**, it chooses among the same k candidates, so it can at best equal exhaustive
  search over them — **no speed-up or optimality claim**. Report mismatches honestly.

### Tests
- `test_bench_routes.py`: tiny run (`--trips 5`) is deterministic for a fixed seed; exhaustive cost ≤ QAOA cost ≤ ... for every
  trip; blocked edges never appear in a chosen path; JSON has the documented keys.

### Done checklist
- ☑ Same seed → identical JSON
- ☑ Algorithms tab shows the measured results
- ☐ Report / paper updated through the skills, `verify.py` passes — waiting for the authors' decision (see "As built")

---

# Round 2 — F7–F15 (planned 2026-10-09, built 2026-10-09 → 2026-10-11)

| # | Feature (round-2 idea no.) | Size | Depends on |
|---|---|---|---|
| F7 | Six cities on real OpenStreetMap road networks (user request) | L | — |
| F8 | Best overall dispatch (assignment) + tracked ambulance positions (idea 2) | M | F7 |
| F9 | Pre-position idle ambulances at predicted hotspots (idea 3) | M | F8 |
| F10 | Road flood-time forecast → avoid roads that close before the unit arrives (idea 4) | M | F7 |
| F11 | Measured uncertainty (conformal) for the v2 flood model (idea 5) | M | — |
| F12 | Headless Monte-Carlo evaluation of the whole operation (idea 6) | M | F8–F10 |
| F13 | "Why this decision?" card per person (idea 8) | S | F8 |
| F14 | Fairness dashboard: time-to-safety by vulnerability / cluster (idea 9) | S–M | F5 frames |
| F15 | Public "Am I safe?" page + offline SOS queue (idea 10) | M | F4 |

## F7 — Six cities on real road networks  ✅ BUILT 2026-10-09 (Guwahati rebuilt 2026-10-11)

**As built:**
- `backend/data/cities/{delhi,mumbai,chennai,kolkata,guwahati,patna}.json` from `scripts/build_city_data.py` (raw Overpass
  cache in `backend/data/cities/raw/`, re-used on re-run; `--refresh` downloads again). The hand-made network stays as
  `delhi_seed`. Guwahati's first build was cut short by an overloaded Overpass server (96 junctions, no depots); the
  rebuild has 272 junctions, 416 named roads, 10 shelters, 6 depots.
- Depots: real OSM fire stations; where fewer than `MIN_DEPOTS` (3) are mapped, OSM police stations fill the slots, each
  marked `kind: "police"` and the `scope` text says so. **Patna** has 1 fire station + police; **Guwahati has no fire
  station in OSM at all** → all 6 depots are police (one is the "state police accountability commission" office — an
  OSM `amenity=police` entry, kept as-is, not invented).
- Only Delhi has a real INDOFLOODS gauge (Yamuna, danger 205.33 m). The other five are rainfall-driven and the UI says so.
- Shelter capacity (`capacity_source: "assumed by type"`), crew size and road traffic are estimates and labelled.
- Road flood exposure = distance proxy to river / coast / canal / pond / drain, bridges capped; every city starts with all
  roads open and loses them as `blockage(t)` grows.
- `backend/geo/cities.py` (`list_cities / load_city / activate`), `GET /api/cities`, `GET /api/cities/{id}`,
  `CityPicker` on Setup, `useCityView` for the map. The build script's final print used "→", which crashes on a cp1252
  console — replaced with "->" (2026-10-11).
- Tests: `test_cities.py` (schema + labelled assumptions, activate swaps and back, routes on each city, rainfall city has
  no stage term, roster re-anchored, unknown city raises).
- **Runtime fixes 2026-10-11** (found in the browser): (1) the live loop crashed on tick 1 in every OSM city —
  `score_shelter` / `solvers` did `None - int` on `zone.population` (null by the data rule); null now means "no known
  load" (`solvers._pop`), regression test `test_one_engine_tick_runs_in_every_city` (6 cities). (2) The Live tab's SOS
  form, the page eyebrow and the voice-agent fallback pin were fixed to Delhi; they now follow the run's city. (3) The
  transfer-warning fallback text said INDOFLOODS was "Indonesia" — it is Indian river gauges.

### Done checklist
- ☑ six city files built from OSM, assumptions labelled · ☑ activate / API / picker · ☑ tests
- ☐ clicked through in the browser for every city

**Cities.** Delhi plus the five most-cited flood-hit cities: **Mumbai** (2005, every monsoon), **Chennai** (2015, 2023),
**Kolkata**, **Guwahati** (Brahmaputra, every year), **Patna** (Ganga, 2019). A city is data, not code — swapping one
is re-running the fetch script with a new spec.

**Data rule — nothing invented.**
- Roads, fire stations (rescue depots), candidate shelters (stadiums, colleges, schools, community centres), suburbs
  (flood zones) and water bodies come from **OpenStreetMap** (Overpass API, ODbL, attribution in the JSON and on the map).
- Road `flood_exposure` = a **proxy from distance to the nearest mapped river / canal / drain / coast**, labelled so.
- Shelter capacity: OSM has none → **assumed by building type**, field `capacity_source: "assumed by type"`, shown in UI.
- River gauge: the nearest **INDOFLOODS** gauge (real warning / danger level + catchment attributes for the ML model)
  when within 30 km (Delhi 6.5 km). Otherwise the city is **rainfall-driven**: no river card, no stage term, said in the UI.
  Mumbai / Chennai / Kolkata / Guwahati / Patna have no INDOFLOODS gauge within 30 km.
- Population: OSM `population` tag only when present, else `null` (never a guess).

**Build.** `scripts/build_city_data.py --city chennai` → `backend/data/cities/chennai.json`
(main roads motorway…secondary, largest connected component, degree-2 nodes contracted, segments grouped into named
roads `CHE-R01…` by length). The old hand-made Delhi network stays as city `delhi_seed` (tests + route benchmark v1).

**Runtime.** `backend/geo/cities.py`: `list_cities()`, `load_city(id)`, `activate(id)`. One engine = one active city:
`activate` swaps the seed lists in place (`seed.SHELTERS/ROADS/ZONES/RESCUE_TEAMS/GRAPH_NODES/GRAPH_EDGES`,
`person_ops.SHELTER_POOL`) and re-syncs Mongo `shelters/roads/rescue_teams`. `engine.start(params.city)` activates.
`_evolve` builds the river doc from the city gauge (scenario river/barrage inputs applied as the same metres above /
below the danger mark) or marks it unavailable; the pipeline passes the city's catchment to the models.
Graph cache per (city, blocked set) so routing stays fast on ~500 junctions.

**API.** `GET /api/cities` (list + summary), `GET /api/cities/{id}` (full geo for the map); state gets `city` block.

**Frontend.** City picker on Setup (ScenarioContext `city`), map centre/zoom/pins/roads from `sim.city`, rainfall-driven
cities hide river/barrage controls, SOS roster re-anchored to the city's flood zones (synthetic, labelled).

**Tests.** city JSON schema + "no invented field" checks; activate swaps everything and back; every shelter / depot
resolves; route on each city graph; rainfall city has no stage term.

## F8 — Best overall dispatch + tracked ambulance positions  ✅ BUILT 2026-10-09

**As built** (differs from the plan):
- Positions are **derived, not stored**: `person_ops.ambulance_positions(rows, ctx, now)` reads them off the stage machine
  (home depot round-robin → last drop-off shelter → interpolated along a staging move). No `ambulance_state` dict.
- `DISPATCH_POLICIES = ("nearest_depot", "first_free", "greedy", "optimal")`. `nearest_depot` is the original rule and is
  **idealised** (launches from the depot nearest the person, ignoring where the ambulance is); `first_free` is the same
  choice from the tracked position — the fair baseline. `optimal` = `scipy.optimize.linear_sum_assignment`, cost = road
  minutes × `VULN_WEIGHT` (child / elderly 1.6, chest-deep 1.3). `dispatch_policy` in `SimulationParams`, served in state.
- Tests: `test_dispatch_policy.py` (positions, greedy picks closest by road, nearest_depot unchanged, optimal ≤ greedy,
  schema rejects unknown policy).
- New authoritative state in `person_ops`: `ambulance_state {name: {lat, lon, place, since, moving?}}` — home depot
  round-robin at start, the drop-off shelter after each job (CLAUDE.md "unit positions never stored" is updated).
- `dispatch_policy`: `"nearest_depot"` (today), `"greedy"` (nearest free ambulance by road time, from where it is),
  `"optimal"` (all waiting SOS × all free ambulances in one `scipy.optimize.linear_sum_assignment`, cost = road minutes
  × vulnerability weight). Selected per run; served in state.
- Tests: optimal total ≤ greedy total on a fixed instance; positions update on drop-off.

## F9 — Pre-position idle ambulances  ✅ BUILT 2026-10-09

**As built:** `person_ops.staging_points` (greedy weighted k-median over junctions, ≤ `STAGING_MAX_POINTS` 6) and
`plan_staging`; weight = exposure proxy × flood probability × (1 + SOS within 1.5 km). Engine runs it each tick when
`params.preposition` is on; moves are real road routes shown on `LiveRescueMap`; a dispatch mid-move starts from the
interpolated point. Test: `test_staging_moves_idle_ambulances_toward_demand_and_dispatch_starts_mid_move`.
- Every tick, free ambulances not already staged are sent to staging points = weighted k-medoids over the city's
  graph junctions, weight = road flood-exposure proxy × current flood probability × SOS so far near that junction.
  The move is a real road route (`repositioning` leg, animated like any unit); a dispatch mid-move starts from the
  interpolated position. Toggle per run; effect measured only in F12.

## F10 — Road flood-time forecast  ✅ BUILT 2026-10-09

**As built:** `engine.road_forecast()` replays the engine's own closure rule on future ticks (cached per run / tick /
overrides); operator-blocked and already-closed roads are skipped. `ctx["closing"]` is passed to `route_candidates`, which
drops a candidate that reaches a road after its forecast close time; legs carry `flood_forecast`. Shown in
`RoadControlPanel` ("floods in ~N min"), `DecisionCard` and `/safe`. Labelled as a forecast of the simulation's rule, not
a hydraulic model. Tests: `test_road_forecast.py` (4).
- The engine's own closure rule (`flood_exposure >= 0.85 - blockage(t)`) is evaluated on future ticks of `_evolve`
  (deterministic given params + overrides) → `road_forecast {road_id: closes_in_ticks, closes_at_sim_min}`.
- `route_candidates(..., closing=, depart_sim_min=)` drops candidates that reach a road after it closes; the map /
  road panel shows "floods in ~N min". Labelled: forecast of the simulation's rule, not a hydraulic model.

## F11 — Measured uncertainty (conformal), v2 model  ✅ BUILT 2026-10-09

**As built:** `scripts/conformal_v2.py` → `models/conformal_v2.json` (additive). The production v2 path uses the **v3
stage-1 regressor** (`flood_regressor_v3.pkl`), so that is the model calibrated; the alert set uses
`flood_alert_model_v2.pkl` fed the v3 level, as at inference. GroupKFold(5) on training gauges only; coverage measured
once on 31 held-out gauges (788 rows), no test tuning. Measured (α = 0.1, target 90 %):
- absolute peak level: ±210.1 m, coverage **86.4 %** (below target — INDOFLOODS levels are gauge elevations on different
  datums);
- multiplicative (log) interval: coverage 98.0 %, median width ≈ 837 m;
- alert prediction set: coverage 96.5 %, but **83 % of sets contain both classes** (only 17 % are a single answer).
Shown as-is in the Prediction tab (`SimulationExecution.jsx`) with the caveats; the hybrid operational probability has no
interval. Tests: `test_conformal.py` (4).
- `scripts/conformal_v2.py`: CV+ (GroupKFold by gauge on the TRAIN gauges only) residuals → 90 % interval for the v2 peak
  level and a prediction set for the v2 alert; coverage measured once on the held-out test gauges →
  `models/conformal_v2.json` (new, additive). No test-set tuning.
- Prediction tab + AI facts show "peak 3.1 m (90 % interval 2.4–3.9 m), coverage 0.9x on unseen gauges". The hybrid
  operational probability stays labelled uncalibrated.

## F12 — Headless Monte-Carlo evaluation  ✅ BUILT 2026-10-09 (per-city results below)

**As built:** `scripts/monte_carlo_ops.py --city <id> --runs 60 --seed 1` (person_ops on a virtual clock, no UI / no ML,
fixed flood probability 0.7 for hotspot weights, horizon 1500 demo-s; unserved = censored) →
`models/ops_montecarlo_v1_<city>.json` + `.timing.json`. `scripts/bench_routes.py --city <id>` →
`models/route_benchmark_v1_<city>.json`. `GET /api/benchmark/ops`, `OpsBenchmarkCard` on the Algorithms tab.
`nearest_depot` is reported as **"not comparable"** (it teleports ambulances to a depot). Tests: `test_monte_carlo.py`
(same seed → same result, honest labelling, endpoint).
**Results:** the full 60-run batch for all six cities was restarted 2026-10-11 00:08 (≈ 30 min per city, logs in the session scratchpad). Until `models/ops_montecarlo_v1_<city>.json` exists for a city, only the 2-run trial is known (optimal ≈ 4 min faster than `first_free`) — do not quote it as a result.
- `scripts/monte_carlo_ops.py --runs 200 --seed 1 --city chennai --policy nearest_depot,greedy,optimal,prepos`:
  person_ops stage machine on a virtual clock (no UI, no ML), synthetic SOS in city zones, random closures / surges /
  a shelter closure → time-to-pickup / time-to-safe mean, p50, p90 per policy and vulnerability → `models/ops_montecarlo_v1.json`.
- Algorithms tab card; `GET /api/benchmark/ops`.

## F13 — "Why this decision?" card  ✅ BUILT 2026-10-09

**As built:** `person_ops._decision(...)` → `row["decision"]` at assignment: queue reason, ambulances considered
(ETA, free / busy / rejected), policy, shelters considered (distance, seats, reachable, closed), chosen + why — only real
alternatives. `DecisionCard.jsx` is used in `RescueOpsPanel`, `LivePeopleTable` and the AI Assistant person card.
Test: `test_assign_records_why_with_only_real_alternatives`.
- `_assign` records `row["decision"]`: queue rank reason, units considered (ETA, free/busy, rejected), policy, shelters
  considered (distance, seats, reachable, closed), chosen + why. Shown in PersonFocus, People row, AI person card.

## F14 — Fairness dashboard  ✅ BUILT 2026-10-09

**As built:** `person_ops.equity_board(rows, now)` — time-to-pickup / time-to-safe by vulnerability and cluster (median,
p90, n, still waiting); flags a group with median ≥ `EQUITY_FLAG_RATIO` (1.5) × overall, small groups are not flagged.
`EquityPanel.jsx` on the Live tab and in `ReplayPlayer` (📼 History). Tests: `test_decision_equity.py`.
- `person_ops.equity_board(rows)`: time-to-pickup / time-to-safe by vulnerability class and cluster (median, p90, n),
  flags a group whose median is > 1.5× the overall median. Live in state, per stored run in History.

## F15 — Public "Am I safe?" page + offline SOS  ✅ BUILT 2026-10-11

**As built:**
- `GET /api/public/safety?lat&lon` (`backend/api/public_sos.py`, 30/min, bbox-checked, stores nothing): `live`, alert
  tier + probability + advice, nearest open shelter with seats that an open road reaches (route points, road km, vehicle
  min, on-foot min at 4.5 km/h, `flood_forecast`), closed / soon-flooding roads within 2 km, river gauge if the city has
  one. With no live run it says so and returns no tier / probability.
- `/safe` (`SafePage.jsx`, polls every 30 s). `/sos` outbox: an SOS made offline (or whose send gets no HTTP answer) is
  kept in `localStorage["aq_sos_outbox"]` (photo kept if ≤ 1.5 MB as a data URL) and sent on `online` / every 15 s; a
  server refusal drops it and tells the person why.
- Offline shell: `frontend/public/sw.js` + `utils/offlinePages.js`, registered from `/sos` and `/safe` in **production
  builds only**. Network-first for navigations to `/sos` / `/safe` with the cached `index.html` as fallback; cache-first
  for hashed `/assets/*` (capped at 80); the page posts the build files it already loaded so the first visit is enough.
  `/api`, `/ws`, map tiles and other pages are never cached — offline the map tiles do not load, the form does.
- Tests: `test_public_sos.py` (+5 safety: 422 outside area, no-run answer stores nothing, live route to an open
  shelter, operator-closed road listed, 429 after 30/min); `CitizenSos.test.jsx` (+3: offline queue → sent on
  `online`, no-answer send is queued, refusal drops it); `offlinePages.test.js` (2).

### Done checklist
- ☑ endpoint + page · ☑ offline outbox · ☑ service worker · ☑ tests
- ☐ tried on a real phone in airplane mode (needs a production build served over HTTPS or localhost)
- `GET /api/public/safety?lat&lon` (rate-limited, inside the active city's bbox): current tier + probability,
  nearest open shelter with seats + road route + ETA, closed roads near you, river status if the city has a gauge.
- `/safe` page (phone, no chrome). `/sos` gets an offline queue: SOS saved locally when offline, sent on `online`;
  a small service worker caches the phone pages so they open without signal.

---

## Still open after Round 2 (2026-10-11)

1. Browser walk-through of F2–F15 (none clicked through yet): city picker per city, dispatch policy + pre-positioning
   toggles, "floods in ~N min" on roads, Why-card, Fairness panel, Algorithms → Ops benchmark, `/safe`, `/sos` offline.
2. Decide whether the F6 / F12 benchmarks and the F11 coverage numbers go into the report / paper (skills only).
3. Code is not yet committed or pushed; the VPS (209.159.153.35) runs an old build — push + redeploy only when asked.
