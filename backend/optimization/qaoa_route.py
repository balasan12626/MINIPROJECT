"""Route choice with QAOA, simulated exactly on a classical statevector.

For one trip the road graph gives up to K candidate routes (Yen's k-shortest
simple paths over the flood-weighted graph). Picking one is a one-hot QUBO
over K binary variables x_i (costs rescaled to [0, 1]):

    minimise  Σ c_i x_i  +  A (Σ x_i − 1)²
    c_i = travel_i / max(travel) + λ · hazard_i      (hazard = worst flood
                                                      exposure on the route)

That QUBO is mapped to a diagonal cost Hamiltonian H_C over 2^K basis states
and solved with p-layer QAOA:

    |ψ(γ, β)⟩ = Π_l  e^{-iβ_l Σ X_j} e^{-iγ_l H_C}  |+⟩^{⊗K}

The circuit is simulated exactly with numpy (2^K ≤ 32 amplitudes), the angles
are tuned classically (angle grid, then COBYLA) to minimise ⟨H_C⟩, the
circuit is measured SHOTS times, and the cheapest sampled route wins. This is a faithful QAOA
*simulation*: no quantum hardware runs, and no speed-up is claimed — with
K ≤ 5 an exhaustive classical search is trivially fast, and it is reported
alongside as the reference answer.
"""

from __future__ import annotations

import math
from functools import lru_cache
from typing import Any

import numpy as np

HAZARD_WEIGHT = 0.5  # λ: how much flood exposure counts against travel time
PENALTY = 2.0  # A: one-hot constraint weight (> the [0, 1] cost spread)
LAYERS = 3
SHOTS = 512


def _energies(costs: np.ndarray) -> np.ndarray:
    k = len(costs)
    states = np.arange(2**k)
    bits = ((states[:, None] >> np.arange(k)) & 1).astype(float)  # bit i = route i
    return bits @ costs + PENALTY * (bits.sum(axis=1) - 1.0) ** 2


def _mixer(k: int, b: float) -> np.ndarray:
    """e^{-iβ Σ X_j} = ⊗_j RX(2β), as one 2^k × 2^k matrix."""
    rx = np.array([[math.cos(b), -1j * math.sin(b)], [-1j * math.sin(b), math.cos(b)]])
    m = np.array([[1.0 + 0j]])
    for _ in range(k):
        m = np.kron(m, rx)
    return m


def _state(energy: np.ndarray, k: int, gammas, betas) -> np.ndarray:
    psi = np.full(2**k, 1 / math.sqrt(2**k), dtype=complex)
    for g, b in zip(gammas, betas):
        psi = _mixer(k, b) @ (psi * np.exp(-1j * g * energy))  # cost layer, then mixer
    return psi


@lru_cache(maxsize=512)
def _solve(costs: tuple[float, ...], seed: int) -> dict[str, Any]:
    from scipy.optimize import minimize

    c = np.asarray(costs, dtype=float)
    k = len(c)
    energy = _energies(c)

    def expectation(x):
        psi = _state(energy, k, x[:LAYERS], x[LAYERS:])
        return float(np.real(np.vdot(psi, energy * psi)))

    # p = 1 grid for a good start, then COBYLA over all 2p angles.
    best = None
    # Small circuits are cheap, so they get a finer angle grid.
    ng, nb, iters = (24, 16, 250) if k <= 3 else (14, 10, 120)
    for g in np.linspace(0.05, math.pi, ng):
        for b in np.linspace(0.05, math.pi / 2, nb):
            x = np.array([g] * LAYERS + [b] * LAYERS)
            e = expectation(x)
            if best is None or e < best[0]:
                best = (e, x)
    res = minimize(expectation, best[1], method="COBYLA", options={"maxiter": iters, "rhobeg": 0.2})
    angles = res.x if res.fun <= best[0] else best[1]
    psi = _state(energy, k, angles[:LAYERS], angles[LAYERS:])
    probs = np.abs(psi) ** 2

    one_hot = [1 << i for i in range(k)]
    route_probs = [float(probs[s]) for s in one_hot]
    most_probable = int(np.argmax(route_probs))
    # Measure SHOTS times, score every sampled one-hot bitstring classically,
    # keep the cheapest — the standard way a QAOA sample becomes an answer.
    rng = np.random.default_rng(seed)
    shots = np.bincount(rng.choice(2**k, size=SHOTS, p=probs / probs.sum()), minlength=2**k)
    sampled = [i for i, s in enumerate(one_hot) if shots[s] > 0]
    chosen = min(sampled, key=lambda i: c[i]) if sampled else most_probable
    exact = int(np.argmin(c))
    return {
        "method": "qaoa-statevector-sim",
        "qubits": k,
        "layers": LAYERS,
        "gammas": [round(float(v), 4) for v in angles[:LAYERS]],
        "betas": [round(float(v), 4) for v in angles[LAYERS:]],
        "expected_energy": round(expectation(angles), 4),
        "ground_energy": round(float(energy.min()), 4),
        "route_probabilities": [round(p, 4) for p in route_probs],
        "feasible_probability": round(float(sum(route_probs)), 4),
        "shots": SHOTS,
        "shot_counts": [int(shots[s]) for s in one_hot],
        "most_probable": most_probable,
        "chosen": chosen,
        "chosen_probability": round(route_probs[chosen], 4),
        "optimal_probability": round(route_probs[exact], 4),
        "selection": "lowest-cost route among the measured shots",
        "exhaustive_best": exact,
        "matches_exhaustive": chosen == exact,
    }


def qaoa_choose(costs: list[float], seed: int = 7) -> dict[str, Any]:
    """QAOA route choice + diagnostics for K ≤ 5 QUBO costs. The costs are
    rescaled to [0, 1] first so the penalty term dominates any infeasible
    (not exactly one route) bitstring; the ordering of routes is unchanged."""
    c = np.asarray(costs, dtype=float)
    span = float(c.max() - c.min())
    scaled = (c - c.min()) / span if span > 1e-9 else np.zeros_like(c)
    return dict(_solve(tuple(round(float(v), 4) for v in scaled), seed))


def candidate_costs(cands: list[dict[str, Any]]) -> list[float]:
    """QUBO linear terms: normalised travel + λ · worst flood exposure."""
    worst = max(c["weighted_km"] for c in cands) or 1.0
    return [c["weighted_km"] / worst + HAZARD_WEIGHT * c["hazard"] for c in cands]
