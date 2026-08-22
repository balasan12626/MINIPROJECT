# Simulation

Digital twin in `backend/simulation/engine.py`. Values evolve **monotonically with the scenario**, not as unrelated random draws:

rainfall ↑ → river/dam stage ↑ → ML probability updates → roads with high flood exposure block → shelter occupancy rises → SOS count rises.

## Phase 1 — Scenario Builder

Scenarios: heavy rainfall, dam overflow, river rise, road blockage, shelter congestion, mass evacuation, multiple SOS.

Only parameters the engine reads are exposed (intensity, levels, blockage, population, traffic, SOS, ticks).

## Phase 2 — Execution

Ticks call `run_pipeline(mode="simulation", observations=...)`. Timeline events are stored with `sim_time_sec`. The execution page badge is orange **SIMULATION MODE — SYNTHETIC DATA / DIGITAL TWIN**.

Results compare before/after optimization costs from the same run, not invented deltas.
