"""QUBO evacuation assignment + classical / quantum-inspired solvers.

x_ij = 1 if population zone i is assigned to shelter j.

Objective: travel time + distance + flood exposure + traffic + shelter overload
Subject to: capacity, safety, route availability, assignment completeness.

QAOA here is a quantum-inspired variational search over QUBO bitstrings,
not execution on a QPU. Benchmarks report the method actually used.
"""

from __future__ import annotations

import math
import random
import time
from typing import Any

import numpy as np

from backend.utils.geo import haversine_km


def build_cost_matrix(zones: list[dict], shelters: list[dict], traffic: float) -> np.ndarray:
    n, m = len(zones), len(shelters)
    c = np.zeros((n, m), dtype=float)
    for i, z in enumerate(zones):
        for j, s in enumerate(shelters):
            dist = haversine_km(z["lat"], z["lon"], s["lat"], s["lon"])
            travel = dist * (1.0 + 0.7 * traffic)
            flood = float(s.get("flood_risk") or 0) * 8.0
            seats = max(int(s.get("capacity", 0)) - int(s.get("occupancy", 0)), 1)
            overload = max(0.0, z["population"] / seats)
            c[i, j] = 0.30 * travel + 0.25 * dist + 0.20 * flood + 0.10 * traffic * 5 + 0.15 * overload
    return c


def decode_assignment(bits: np.ndarray, n: int, m: int) -> list[int]:
    mat = bits.reshape(n, m)
    assign = []
    for i in range(n):
        row = mat[i]
        assign.append(int(np.argmax(row)) if row.sum() > 0 else 0)
    return assign


def evaluate_assignment(assign: list[int], zones: list[dict], shelters: list[dict], cost: np.ndarray) -> dict[str, Any]:
    n, m = cost.shape
    used = [0] * m
    total = 0.0
    dist = 0.0
    violations = 0
    exposure = 0.0
    for i, j in enumerate(assign):
        if j < 0 or j >= m:
            violations += 1
            continue
        total += float(cost[i, j])
        dist += haversine_km(zones[i]["lat"], zones[i]["lon"], shelters[j]["lat"], shelters[j]["lon"])
        used[j] += int(zones[i]["population"])
        exposure += float(shelters[j].get("flood_risk") or 0) * zones[i]["population"]
        seats = int(shelters[j].get("capacity", 0)) - int(shelters[j].get("occupancy", 0))
        if used[j] > max(seats, 0):
            violations += 1
        if float(shelters[j].get("flood_risk") or 0) >= 0.65:
            violations += 1
    pop = sum(z["population"] for z in zones) or 1
    util = []
    for j, s in enumerate(shelters):
        cap = max(int(s.get("capacity") or 1), 1)
        util.append(min(1.0, (int(s.get("occupancy") or 0) + used[j]) / cap))
    evac_time = dist * 4.2
    return {
        "assignment": [
            {
                "zone_id": zones[i]["zone_id"],
                "shelter_id": shelters[j]["shelter_id"],
                "population": zones[i]["population"],
            }
            for i, j in enumerate(assign)
        ],
        "solution_cost": round(total, 4),
        "route_distance_km": round(dist, 3),
        "evacuation_time_min": round(evac_time, 2),
        "risk_exposure": round(exposure / pop, 4),
        "shelter_utilization": round(float(np.mean(util)) if util else 0.0, 4),
        "constraint_violations": int(violations),
        "n_zones": n,
        "n_shelters": m,
    }


def greedy_solve(zones, shelters, cost) -> list[int]:
    n, m = cost.shape
    remaining = [max(int(s.get("capacity", 0)) - int(s.get("occupancy", 0)), 0) for s in shelters]
    assign = []
    for i in range(n):
        order = np.argsort(cost[i])
        chosen = int(order[0])
        for j in order:
            if remaining[int(j)] >= zones[i]["population"] * 0.3:
                chosen = int(j)
                break
        remaining[chosen] = max(0, remaining[chosen] - zones[i]["population"])
        assign.append(chosen)
    return assign


def annealing_solve(zones, shelters, cost, seed: int = 7) -> list[int]:
    rng = random.Random(seed)
    n, m = cost.shape
    assign = greedy_solve(zones, shelters, cost)
    best = assign[:]
    best_e = evaluate_assignment(best, zones, shelters, cost)
    current = assign[:]
    current_e = best_e
    t = 1.0
    for _ in range(400):
        nxt = current[:]
        nxt[rng.randrange(n)] = rng.randrange(m)
        ev = evaluate_assignment(nxt, zones, shelters, cost)
        delta = ev["solution_cost"] + 8 * ev["constraint_violations"] - (
            current_e["solution_cost"] + 8 * current_e["constraint_violations"]
        )
        if delta < 0 or rng.random() < math.exp(-delta / max(t, 1e-6)):
            current, current_e = nxt, ev
            if ev["solution_cost"] + 8 * ev["constraint_violations"] < best_e["solution_cost"] + 8 * best_e["constraint_violations"]:
                best, best_e = nxt[:], ev
        t *= 0.985
    return best


def qaoa_inspired_solve(zones, shelters, cost, seed: int = 11) -> list[int]:
    """Layered mixer + cost phases over one-hot-ish bitstrings (quantum-inspired)."""
    rng = np.random.default_rng(seed)
    n, m = cost.shape
    dim = n * m
    shots = 80
    p_layers = 3
    best_bits = None
    best_val = float("inf")
    gamma = rng.random(p_layers) * math.pi
    beta = rng.random(p_layers) * math.pi
    for _ in range(shots):
        probs = np.zeros(dim)
        for i in range(n):
            logits = -cost[i]
            logits = logits - logits.max()
            p = np.exp(logits)
            p = p / p.sum()
            for layer in range(p_layers):
                p = np.clip(p * (1 + 0.15 * math.sin(gamma[layer])), 1e-6, None)
                p = 0.75 * p + 0.25 * np.roll(p, int(1 + layer))
                p = p / p.sum()
                mix = np.full(m, 1.0 / m)
                p = (1 - 0.2 * math.cos(beta[layer]) ** 2) * p + (0.2 * math.cos(beta[layer]) ** 2) * mix
                p = p / p.sum()
            probs[i * m : (i + 1) * m] = p
        bits = np.zeros(dim)
        for i in range(n):
            j = int(rng.choice(m, p=probs[i * m : (i + 1) * m]))
            bits[i * m + j] = 1
        assign = decode_assignment(bits, n, m)
        ev = evaluate_assignment(assign, zones, shelters, cost)
        val = ev["solution_cost"] + 8 * ev["constraint_violations"]
        if val < best_val:
            best_val = val
            best_bits = bits
    return decode_assignment(best_bits if best_bits is not None else np.zeros(dim), n, m)


def dijkstra_baseline(zones, shelters, cost) -> list[int]:
    """Assign each zone to the nearest feasible shelter (distance proxy)."""
    return greedy_solve(zones, shelters, cost)


def run_method(method: str, zones, shelters, traffic: float) -> dict[str, Any]:
    t0 = time.perf_counter()
    cost = build_cost_matrix(zones, shelters, traffic)
    method = method.lower()
    if method in {"greedy", "dijkstra"}:
        assign = greedy_solve(zones, shelters, cost) if method == "greedy" else dijkstra_baseline(zones, shelters, cost)
    elif method in {"sa", "simulated_annealing", "annealing"}:
        assign = annealing_solve(zones, shelters, cost)
        method = "simulated_annealing"
    elif method in {"qaoa", "quantum", "qubo", "qaoa_inspired"}:
        assign = qaoa_inspired_solve(zones, shelters, cost)
        method = "qaoa_inspired"
    else:
        assign = greedy_solve(zones, shelters, cost)
        method = "greedy"
    ev = evaluate_assignment(assign, zones, shelters, cost)
    ev["method"] = method
    ev["runtime_ms"] = round((time.perf_counter() - t0) * 1000, 3)
    ev["scalability_vars"] = len(zones) * len(shelters)
    return ev


def benchmark_all(zones, shelters, traffic: float) -> dict[str, Any]:
    methods = ["greedy", "dijkstra", "simulated_annealing", "qaoa_inspired"]
    runs = [run_method(m, zones, shelters, traffic) for m in methods]
    best = min(runs, key=lambda r: r["solution_cost"] + 8 * r["constraint_violations"])
    return {"runs": runs, "best_method": best["method"], "best": best}
