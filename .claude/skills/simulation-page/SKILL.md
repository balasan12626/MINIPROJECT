---
name: simulation-page
description: Use when changing the unified /simulation page - the scenario picker, scenario config, inputs, the single RUN SCENARIO flow, or the dam / evacuation / HQRL benchmark results.
---

# /simulation Page Workflow

One page, one scenario, one run button. Flow is strictly top-to-bottom:
**pick scenario → review/edit inputs → RUN SCENARIO → results**.

## Structure

| File | Role |
| --- | --- |
| `pages/SimulationLab/SimulationLab.jsx` | Layout only; wraps everything in `ScenarioProvider` |
| `config/scenarios.js` | THE scenario catalogue (groups, presets, HQRL mode) |
| `state/ScenarioContext.jsx` | Selection, inputs, dam registry, roster, and the one run flow |
| `components/scenario/ScenarioPicker.jsx` | Searchable combobox + grouped cards |
| `components/scenario/ScenarioInputs.jsx` | Editable inputs + Custom badge + reset |
| `components/scenario/RunScenarioBar.jsx` | The single button + per-step progress |
| `components/scenario/ScenarioOutputs.jsx` | Empty state / skeletons / results |

## Rules

- **Nothing runs on mount.** The only load-time request is `GET /api/dams`, which populates the dam selector. Selecting a scenario fills inputs and runs nothing.
- One `RUN SCENARIO` click drives three backends in order: dam → evacuation → HQRL benchmark. Each step has its own try/catch so a failure never wipes the other steps' results, and each can be retried alone via `runScenario({ only: "<step>" })`.
- Every run write is guarded by a monotonic run id (`runSeq`); a superseded run must never land on top of a newer one.
- Results are marked **outdated** (dimmed) when the scenario or any input changes after a run. Never auto-rerun.
- Every displayed value must trace to that run's response. No hardcoded or stale numbers.

## Adding a scenario

Append one entry to `SCENARIOS` in `config/scenarios.js` with:

- `group` — one of `dam`, `simulation`, `hqrl`
- `sim.scenario` — an id that exists in `backend/simulation/engine.py`
- `sim.params` — the **complete** engine parameter set (the backend does not merge defaults)
- `dam.controls` — raw reservoir controls; `dam.preset` is provenance metadata only and is never sent
- `hqrl.mode` — `benchmark` or `ablation`
- `provenance` — `native` only when both halves are verbatim backend values

`state/ScenarioContext.test.jsx` fails if a scenario references a backend id that does not exist or omits an engine parameter.

## Traps

- Never send `scenario` to `POST /api/simulation/run` — it overwrites every typed input.
- `Number(null) === 0`, so `Number.isFinite(Number(x))` passes on a missing value. Use `typeof x === "number"` when a field may be absent (this shipped a "0 h" time-to-overflow once).
- Do not blend backend shelter occupancy with rescues completed this run; show them separately.

## Tabs (`?tab=`)

`setup · live · agents · ai · people · routes · prediction · dam · algorithms · report`
(`SIM_TABS` in `SimulationLab.jsx`).

- `ScenarioOutputs` is always mounted; `SimulationExecution` sits in a fixed
  slot that is only **hidden** on `setup` / `dam` / `ai`, so the single
  1.2 s poller (`simStore.js`) never restarts on a tab switch. Never mount a
  second poller per tab.
- `ai` needs no run (it answers from whatever state exists). `dam` uses the
  dam registry + the run's dam response; `capacity_override_m` /
  `current_level_m` edits survive a scenario reload (`userPickedDam` ref).
- Mettur shows its gauge in ft (`gauge_unit/gauge_full/gauge_zero_m` in
  `backend/data/dams.py`); other dams show m MSL. Never convert one dam's
  gauge offset to another.
- Notifications are a portal (`NotificationCenter`) visible on every tab.
- Agents, QAOA routes, live controls and the AI tab: see the `agents-ai` skill.
