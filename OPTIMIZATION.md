# Optimization

After classical shelter scoring and Yen/Dijkstra routes, zone→shelter assignment is a QUBO-style binary problem:

`x_ij = 1` if zone `i` is assigned to shelter `j`.

Cost terms: travel time, distance, flood exposure, traffic, overload. Penalties: capacity, unsafe shelters.

## Solvers (`backend/optimization/solvers.py`)

| Method | What it is |
| --- | --- |
| Greedy | Capacity-aware cheapest column per zone |
| Dijkstra | Same cost matrix, nearest-feasible proxy |
| Simulated annealing | Local reassignment search |
| QAOA-inspired | Variational mixer/cost phases over one-hot bitstrings — **not a QPU** |

The UI shows the **method actually used**. No quantum-supremacy claim is made.

Compare via `POST /api/optimization/benchmark`. Metrics recorded: runtime_ms, solution_cost, route_distance_km, evacuation_time_min, risk_exposure, shelter_utilization, constraint_violations, scalability_vars.
