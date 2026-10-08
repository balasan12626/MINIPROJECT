---
name: rescue-ops
description: Use when working on the live rescue operation view - the animated rescue map, moving units, the live SOS roster table, stage badges, or the event feed.
---

# Live Rescue Operations Workflow

## The backend already runs the operation

`backend/services/person_ops.py` is the authority. It advances every person
`queued → assigned → en_route → to_shelter → rescued`, one stage per
`STAGE_SECONDS = 12`, stamps `ops_stage_at` at each transition, and records a
full `journey[]` with timestamps and agent attribution.

**Do not build a second simulator.** Stages, assignments, shelters, ETAs and
timestamps are real backend state; inventing them would contradict the
"one authoritative simulation source" rule.

## The only thing the frontend computes

Position along the backend's own `team_paths` from/to segment, clocked by the
backend's own stage timestamp:

```
progress   = (serverNow - ops_stage_at) / STAGE_SECONDS
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
- Pause is **view-only** (freezes polling and animation). The backend's
  `resume()` re-ingests citizens and destroys progress.
- Bearing is constant for a leg, so bake it into the cached icon rather than
  writing to the DOM every frame.

## Does not exist

No hospitals, no phone numbers, no boats, no per-person zone. Units are the
backend's real `team_paths[].role` (`rescue` or `ambulance`); the table shows
the K-means `cluster` in place of a zone. `POST /api/simulation/sos` cannot add
a person mid-run without wiping everyone past `assigned`.

## Adding assets

- **Shelter** — add to `person_ops.SHELTER_POOL`, give it coordinates in
  `seed.py` or `rescue_desk.py`, then mirror into `data/rescueAssets.js`.
  A test fails if any pool name cannot resolve to coordinates.
- **Rescue team** — add to `seed.RESCUE_TEAMS`, mirror into `rescueAssets.js`.
- **SOS count** — set `sos_count` in the scenario's `sim.params`; the roster is
  sized from `data/citizens.js`.
