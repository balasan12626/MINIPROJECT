---
name: rescue-ops
description: Use when working on the live rescue operation view - the animated rescue map, moving units, the live SOS roster table, stage badges, or the event feed.
---

# Live Rescue Operations Workflow

## The backend already runs the operation

`backend/services/person_ops.py` is the authority. It advances every person
`queued → assigned → en_route → to_shelter → rescued`. Each stage lasts the
person's own `ops_stage_seconds` (route travel time ÷ `TIME_SCALE`), stamps
`ops_stage_at` and `timestamps[stage]`, and records a full `journey[]` with
agent attribution. `assigned` sends the `dispatch_request` to the driver;
`en_route` is the driver accepting (`driver_accepted`, `accepted_at`,
`timestamps["accepted"]`). `fleet_board()` / `shelter_allocation_board()` are
the free-ambulance and live shelter-seat views.

**Do not build a second simulator.** Stages, assignments, shelters, ETAs and
timestamps are real backend state; inventing them would contradict the
"one authoritative simulation source" rule.

## The only thing the frontend computes

Position along the backend's own `team_paths` from/to segment, clocked by the
backend's own stage timestamp:

```
progress   = (serverNow - ops_stage_at) / ops_stage_seconds
en_route   -> lerp(depot,  person)
to_shelter -> lerp(person, shelter)
```

Any other stage draws **no** unit — nothing is moving, so nothing is shown.
`state/rescueOps.js` holds this as pure functions; `hooks/useRescueOps.js`
re-derives once per poll.

## Files

| File | Role |
| --- | --- |
| `state/rescueOps.js` | Pure derivation: people, units, shelters, counters, event feed |
| `state/rescueOps.test.js` | Interpolation, clamping, shelter resolution, feed merge |
| `hooks/useRescueOps.js` | Per-poll view model, view pause, stage-change flash |
| `data/rescueAssets.js` | Mirrors of backend shelters / teams / stage vocabulary |
| `components/rescue/LiveRescueMap.jsx` | Pins, moving units, shelters, legend, counters |
| `components/rescue/LivePeopleTable.jsx` | Filters, search, sort, expandable timeline |
| `components/rescue/RescueOpsPanel.jsx` | Composes map + event feed + table |

Mounted from `SimulationExecution.jsx`, which already polls `/api/simulation/state`
every 1.2 s — **never add a second poller**.

## Rules

- The clock offset must be **stable**. Recomputing `newest - Date.now()` each
  poll collapses the derived "now" to `newest`, so time stops and units freeze.
  Keep the largest offset observed.
- Row identity is `citizen_name`. `_id` only exists when Mongo is connected and
  `rescue_order` is re-ranked whenever the roster changes, so neither is a safe
  React key for an animated list.
- Flash on stage change keyed by `${stage}@${ops_stage_at}`, not array identity —
  `sim.citizens` is a fresh array every poll.
- Pause is **view-only** (freezes polling and animation). Backend
  `start`/`pause`/`reset` go through `engine._stop_task()`, which awaits the
  cancelled loop — never call `task.cancel()` without awaiting it.
- Bearing is constant for a leg, so bake it into the cached icon rather than
  writing to the DOM every frame.

## Does not exist

No hospitals, no phone numbers, no boats, no per-person zone. Units are the
backend's real `team_paths[].role` (`rescue` or `ambulance`); the table shows
the K-means `cluster` in place of a zone.

## Adding SOS mid-run

`engine.add_citizen_sos()` (`POST /api/simulation/sos`) appends one person at
`queued`, attached to the nearest existing cluster — nobody is re-clustered.
`add_sos_surge(count)` (`POST /api/simulation/sos/surge`, 1–100) adds synthetic
callers with `quick=True` and one shared ML result, then calls
`mas.announce_surge`. Surge callers are synthetic — say so in any write-up.

## Adding assets

- **Shelter** — add to `person_ops.SHELTER_POOL`, give it coordinates in
  `seed.py` or `rescue_desk.py`, then mirror into `data/rescueAssets.js`.
  A test fails if any pool name cannot resolve to coordinates.
- **Rescue team** — add to `seed.RESCUE_TEAMS`, mirror into `rescueAssets.js`.
- **SOS count** — set `sos_count` in the scenario's `sim.params`; the roster is
  sized from `data/citizens.js`.
