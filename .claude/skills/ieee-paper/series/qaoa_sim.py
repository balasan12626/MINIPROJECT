"""Exact statevector QAOA for the shelter-assignment problem of the HQRL digital twin.

Used by the paper-series experiments (P1 quantum, P3 agentic+quantum). Pure numpy/scipy,
noiseless, classical simulation of the circuit. No hardware, no speed-up claim.

Instance: G evacuation groups x S shelters, binary x[g,s] (qubit q = g*S + s).
  cost      c[g,s]   = travel_min + 5 * hazard_exposure of the best open path zone(g) -> s
  forbidden          = no open path, shelter failed, or group larger than remaining seats
  capacity           sum_g n_g x[g,s] <= R_s   (encoded pairwise in the QUBO, checked exactly)
"""
from __future__ import annotations

import itertools
import math
import time

import networkx as nx
import numpy as np
from scipy.optimize import minimize


# ----------------------------------------------------------------------------- instances
def instance_from_engine(eng, n_groups: int, prev: dict | None = None, mu: float = 0.0) -> dict:
    """Build an assignment instance from the current HqrlEngine state.

    prev: optional {group_index: shelter_index} of the plan in force; mu adds a linear
    stability penalty mu * (1 - x[g, prev[g]]) (constant dropped) so re-plans avoid churn.
    """
    gnx = eng._build_nx()
    sids = list(eng.shelters)
    groups = eng.groups[:n_groups]
    G, S = len(groups), len(sids)
    cost = np.zeros((G, S))
    forb = np.zeros((G, S), dtype=bool)
    rem = np.array([max(0, int(eng.shelters[s]["remaining"])) if eng.shelters[s]["status"] != "FAILED" else 0
                    for s in sids])
    sizes = np.array([int(g["size"]) for g in groups])
    for gi, g in enumerate(groups):
        for si, s in enumerate(sids):
            sh = eng.shelters[s]
            try:
                path = nx.shortest_path(gnx, g["zone"], s, weight="weight")
                m = eng._path_metrics(path, g)
                cost[gi, si] = m["travel_min"] + 5.0 * m["hazard_exposure"]
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                forb[gi, si] = True
                continue
            if sh["status"] == "FAILED" or sizes[gi] > rem[si] or (g["vulnerable"] and not sh["accessibility"]):
                forb[gi, si] = True
    stab = np.zeros((G, S))
    if prev and mu > 0:
        for gi, si in prev.items():
            if gi < G:
                stab[gi, :] = mu
                stab[gi, si] = 0.0
    return {"G": G, "S": S, "sids": sids, "sizes": sizes, "rem": rem, "cost": cost, "forb": forb, "stab": stab}


def overload_pairs(inst: dict) -> list[tuple[int, int, int]]:
    """(g, g', s) pairs whose combined size exceeds shelter s (each fits alone)."""
    out = []
    for s in range(inst["S"]):
        for g, h in itertools.combinations(range(inst["G"]), 2):
            if inst["forb"][g, s] or inst["forb"][h, s]:
                continue
            if inst["sizes"][g] + inst["sizes"][h] > inst["rem"][s]:
                out.append((g, h, s))
    return out


def shifted_cost(inst: dict) -> np.ndarray:
    """c[g,s] - min_s c[g,s] over allowed shelters. On one-hot states this only subtracts a
    constant, so the optimum is unchanged, but the energy scale now reflects the decision."""
    c = inst["cost"] + inst["stab"]
    big = np.where(inst["forb"], np.inf, c)
    lo = np.where(np.isfinite(big.min(axis=1)), big.min(axis=1), 0.0)
    return np.where(inst["forb"], 0.0, c - lo[:, None])


def penalty_weight(inst: dict) -> float:
    """Any single violation costs more than the largest possible feasible-cost difference."""
    return 1.0 + float(np.sum(shifted_cost(inst).max(axis=1)))


# ----------------------------------------------------------------------------- energies
def bit_table(n: int) -> np.ndarray:
    idx = np.arange(2 ** n, dtype=np.int64)
    return ((idx[:, None] >> np.arange(n)) & 1).astype(np.int8)


def diagonals(inst: dict, bits: np.ndarray | None = None) -> dict:
    """QUBO energy, true cost, true feasibility and one-hot mask over all 2^n bitstrings."""
    G, S = inst["G"], inst["S"]
    n = G * S
    if bits is None:
        bits = bit_table(n)
    x = bits.reshape(-1, G, S).astype(np.float64)
    c = inst["cost"] + inst["stab"]
    lin = np.einsum("kgs,gs->k", x, c)
    lin_s = np.einsum("kgs,gs->k", x, shifted_cost(inst))
    P = penalty_weight(inst)
    onehot_viol = ((1.0 - x.sum(axis=2)) ** 2).sum(axis=1)
    forb_viol = np.einsum("kgs,gs->k", x, inst["forb"].astype(np.float64))
    pair_viol = np.zeros(len(bits))
    for g, h, s in overload_pairs(inst):
        pair_viol += x[:, g, s] * x[:, h, s]
    h_qubo = lin_s + P * (onehot_viol + forb_viol + pair_viol)
    h_xy = lin_s + P * (forb_viol + pair_viol)  # one-hot is preserved by the XY mixer
    onehot = (x.sum(axis=2) == 1).all(axis=1)
    load = np.einsum("kgs,g->ks", x, inst["sizes"].astype(np.float64))
    feas = onehot & (forb_viol == 0) & (load <= inst["rem"][None, :]).all(axis=1)
    true_cost = np.where(feas, np.einsum("kgs,gs->k", x, inst["cost"]), np.inf)
    obj = np.where(feas, lin, np.inf)  # planner objective incl. stability term
    return {"h_qubo": h_qubo, "h_xy": h_xy, "feas": feas, "onehot": onehot, "cost": true_cost, "obj": obj, "P": P}


def exact_solve(inst: dict) -> dict:
    """Enumerate the G^S one-hot assignments (classical reference)."""
    t0 = time.perf_counter()
    G, S = inst["G"], inst["S"]
    c = inst["cost"] + inst["stab"]
    best, best_a = math.inf, None
    for a in itertools.product(range(S), repeat=G):
        if any(inst["forb"][g, s] for g, s in enumerate(a)):
            continue
        load = np.zeros(S)
        for g, s in enumerate(a):
            load[s] += inst["sizes"][g]
        if (load > inst["rem"]).any():
            continue
        v = sum(c[g, s] for g, s in enumerate(a))
        if v < best - 1e-12:
            best, best_a = v, a
    return {"obj": best, "assign": best_a, "ms": (time.perf_counter() - t0) * 1000}


def assign_to_index(a, S: int) -> int:
    return sum(1 << (g * S + s) for g, s in enumerate(a))


def index_to_assign(k: int, G: int, S: int):
    a = []
    for g in range(G):
        row = [(k >> (g * S + s)) & 1 for s in range(S)]
        if sum(row) != 1:
            return None
        a.append(row.index(1))
    return tuple(a)


# ----------------------------------------------------------------------------- circuits
def _apply_rx_all(psi: np.ndarray, n: int, beta: float) -> np.ndarray:
    c, s = math.cos(beta), -1j * math.sin(beta)
    for q in range(n):
        v = psi.reshape(2 ** (n - q - 1), 2, 2 ** q)
        a0, a1 = v[:, 0, :].copy(), v[:, 1, :].copy()
        v[:, 0, :] = c * a0 + s * a1
        v[:, 1, :] = s * a0 + c * a1
    return psi


def xy_pairs(n: int, G: int, S: int) -> list[tuple[np.ndarray, np.ndarray]]:
    """Index pairs (|..0_a..1_b..>, |..1_a..0_b..>) for the ring XY mixer inside each group."""
    idx = np.arange(2 ** n, dtype=np.int64)
    out = []
    ring = [(i, (i + 1) % S) for i in range(S)] if S > 2 else [(0, 1)]
    for g in range(G):
        for i, j in ring:
            a, b = g * S + i, g * S + j
            m = (((idx >> a) & 1) == 0) & (((idx >> b) & 1) == 1)
            i01 = idx[m]
            out.append((i01, i01 ^ ((1 << a) | (1 << b))))
    return out


def _apply_xy(psi: np.ndarray, pairs, beta: float) -> np.ndarray:
    c, s = math.cos(beta), -1j * math.sin(beta)
    for i01, i10 in pairs:
        v01, v10 = psi[i01].copy(), psi[i10]
        psi[i01] = c * v01 + s * v10
        psi[i10] = c * v10 + s * v01
    return psi


def initial_state(kind: str, G: int, S: int) -> np.ndarray:
    n = G * S
    if kind == "x":
        return np.full(2 ** n, 2 ** (-n / 2), dtype=np.complex128)
    psi = np.zeros(2 ** n, dtype=np.complex128)  # product of W states, one per group
    for a in itertools.product(range(S), repeat=G):
        psi[assign_to_index(a, S)] = S ** (-G / 2)
    return psi


class Qaoa:
    """p-layer QAOA with either the transverse-field (x) or ring-XY (xy) mixer."""

    def __init__(self, inst: dict, kind: str, diag: dict | None = None, bits=None, alpha: float = 1.0):
        self.inst, self.kind, self.alpha = inst, kind, alpha
        self.G, self.S = inst["G"], inst["S"]
        self.n = self.G * self.S
        self.d = diag or diagonals(inst, bits)
        h = self.d["h_qubo"] if kind == "x" else self.d["h_xy"]
        self.h = h
        # scale by the total cost spread so feasible energies lie in [0, 1] (angles then O(1))
        self.scale = max(self.d["P"] - 1.0, 1e-9)
        self.hn = h / self.scale
        self.order = np.argsort(self.hn, kind="stable")
        self.hn_sorted = self.hn[self.order]
        self.psi0 = initial_state(kind, self.G, self.S)
        self.pairs = xy_pairs(self.n, self.G, self.S) if kind == "xy" else None
        self.nfev = 0

    def state(self, theta: np.ndarray) -> np.ndarray:
        p = len(theta) // 2
        psi = self.psi0.copy()
        for k in range(p):
            psi *= np.exp(-1j * theta[k] * self.hn)
            if self.kind == "x":
                _apply_rx_all(psi, self.n, theta[p + k])
            else:
                _apply_xy(psi, self.pairs, theta[p + k])
        return psi

    def energy(self, theta: np.ndarray) -> float:
        """Expected energy, or CVaR_alpha (mean of the lowest alpha probability mass)."""
        self.nfev += 1
        pr = np.abs(self.state(theta)) ** 2
        if self.alpha >= 1.0:
            return float(pr @ self.hn)
        ps = pr[self.order]
        cum = np.cumsum(ps)
        w = np.clip(self.alpha - (cum - ps), 0.0, ps)
        return float(w @ self.hn_sorted) / self.alpha

    def optimise(self, p: int, rng: np.random.Generator, restarts: int = 3, warm: np.ndarray | None = None,
                 maxiter: int = 250) -> tuple[np.ndarray, float]:
        starts = []
        if warm is not None:  # INTERP initialisation from the (p-1)-layer optimum
            q = len(warm) // 2
            g_old, b_old = warm[:q], warm[q:]
            xs = np.linspace(0, 1, q) if q > 1 else np.array([0.0])
            xn = np.linspace(0, 1, p)
            starts.append(np.concatenate([np.interp(xn, xs, g_old), np.interp(xn, xs, b_old)]))
        for _ in range(restarts):
            starts.append(np.concatenate([rng.uniform(0, math.pi, p), rng.uniform(0, math.pi / 2, p)]))
        best_t, best_e = None, math.inf
        for t0 in starts:
            r = minimize(self.energy, t0, method="COBYLA", options={"maxiter": maxiter, "rhobeg": 0.4})
            if r.fun < best_e:
                best_t, best_e = r.x, float(r.fun)
        return best_t, best_e


def sample(probs: np.ndarray, shots: int, rng: np.random.Generator) -> np.ndarray:
    probs = probs / probs.sum()
    return rng.choice(len(probs), size=shots, p=probs)


# ----------------------------------------------------------------------------- classical baselines
def simulated_annealing(inst: dict, diag: dict, rng: np.random.Generator, restarts: int, sweeps: int = 60) -> dict:
    """Single-bit-flip SA on the QUBO energy; returns the best bitstring over restarts."""
    n = inst["G"] * inst["S"]
    h = diag["h_qubo"]
    best_k, best_e = None, math.inf
    t0 = time.perf_counter()
    scale = max(diag["P"] - 1.0, 1e-9)
    for _ in range(restarts):
        k = int(rng.integers(0, 2 ** n))
        e = h[k]
        T = 2.0 * scale
        for _ in range(sweeps):
            for q in rng.permutation(n):
                k2 = k ^ (1 << int(q))
                de = h[k2] - e
                if de <= 0 or rng.random() < math.exp(-de / T):
                    k, e = k2, h[k2]
            T *= 0.9
        if e < best_e:
            best_k, best_e = k, e
    return {"k": best_k, "ms": (time.perf_counter() - t0) * 1000}


def greedy(inst: dict, order: list[int]) -> tuple | None:
    """Cheapest shelter with seats left, groups in the given order (vulnerable first)."""
    rem = inst["rem"].astype(float).copy()
    c = inst["cost"] + inst["stab"]
    a = [None] * inst["G"]
    for g in order:
        opts = [s for s in range(inst["S"]) if not inst["forb"][g, s] and inst["sizes"][g] <= rem[s]]
        if not opts:
            return None
        s = min(opts, key=lambda s: c[g, s])
        a[g] = s
        rem[s] -= inst["sizes"][g]
    return tuple(a)


# ----------------------------------------------------------------------------- one-hot subspace (added for P1 round 3)
# The ring-XY and Grover mixers never leave the span of the S^G one-hot plans, and the cost operator is
# diagonal, so both circuits can be simulated exactly on S^G amplitudes instead of 2^(G S). Nothing above
# is changed; these functions are additive.
def onehot_plans(G: int, S: int) -> np.ndarray:
    """All S^G plans as an (S^G, G) int array; row k is the plan of subspace index k (group 0 slowest)."""
    return np.array(list(itertools.product(range(S), repeat=G)), dtype=np.int64).reshape(-1, G)


def subspace_diag(inst: dict) -> dict:
    """Energies and true feasibility/cost of the S^G one-hot plans (same terms as diagonals())."""
    G, S = inst["G"], inst["S"]
    A = onehot_plans(G, S)
    rows = np.arange(G)
    c = inst["cost"] + inst["stab"]
    cs = shifted_cost(inst)
    lin = c[rows, A].sum(axis=1)
    lin_s = cs[rows, A].sum(axis=1)
    P = penalty_weight(inst)
    forb_viol = inst["forb"][rows, A].sum(axis=1).astype(np.float64)
    pair_viol = np.zeros(len(A))
    for g, h, s in overload_pairs(inst):
        pair_viol += ((A[:, g] == s) & (A[:, h] == s))
    h_xy = lin_s + P * (forb_viol + pair_viol)
    load = np.zeros((len(A), S))
    for g in range(G):
        load[np.arange(len(A)), A[:, g]] += inst["sizes"][g]
    feas = (forb_viol == 0) & (load <= inst["rem"][None, :]).all(axis=1)
    true_cost = np.where(feas, inst["cost"][rows, A].sum(axis=1), np.inf)
    obj = np.where(feas, lin, np.inf)
    full_index = np.array([assign_to_index(a, S) for a in A], dtype=np.int64)
    return {"plans": A, "h_xy": h_xy, "feas": feas, "cost": true_cost, "obj": obj, "P": P, "full_index": full_index}


class SubQaoa(Qaoa):
    """Ring-XY ("xy") or Grover ("grover") QAOA simulated on the S^G one-hot amplitudes.

    Same angles, scaling (divide by P - 1), objectives and optimiser as Qaoa; state() returns the S^G
    amplitudes ordered as onehot_plans(). Agrees with Qaoa(kind="xy") on the one-hot entries.
    """

    def __init__(self, inst: dict, kind: str = "xy", sd: dict | None = None, alpha: float = 1.0):
        self.inst, self.kind, self.alpha = inst, kind, alpha
        self.G, self.S = inst["G"], inst["S"]
        self.n = self.G * self.S
        self.d = sd or subspace_diag(inst)
        self.h = self.d["h_xy"]
        self.scale = max(self.d["P"] - 1.0, 1e-9)
        self.hn = self.h / self.scale
        self.order = np.argsort(self.hn, kind="stable")
        self.hn_sorted = self.hn[self.order]
        self.psi0 = np.full(self.S ** self.G, self.S ** (-self.G / 2), dtype=np.complex128)
        self.pairs = None
        self.ring = [(i, (i + 1) % self.S) for i in range(self.S)] if self.S > 2 else [(0, 1)]
        self.nfev = 0

    def _mix_xy(self, psi: np.ndarray, beta: float) -> np.ndarray:
        c, s = math.cos(beta), -1j * math.sin(beta)
        v = psi.reshape((self.S,) * self.G)
        for g in range(self.G):
            for i, j in self.ring:
                ix = [slice(None)] * self.G
                jx = [slice(None)] * self.G
                ix[g], jx[g] = i, j
                ai, aj = v[tuple(ix)].copy(), v[tuple(jx)].copy()
                v[tuple(ix)] = c * ai + s * aj
                v[tuple(jx)] = c * aj + s * ai
        return psi

    def state(self, theta: np.ndarray) -> np.ndarray:
        p = len(theta) // 2
        psi = self.psi0.copy()
        for k in range(p):
            psi *= np.exp(-1j * theta[k] * self.hn)
            if self.kind == "grover":
                psi += (np.exp(-1j * theta[p + k]) - 1.0) * np.vdot(self.psi0, psi) * self.psi0
            else:
                self._mix_xy(psi, theta[p + k])
        return psi


def sa_onehot(inst: dict, sd: dict, rng: np.random.Generator, restarts: int, sweeps: int = 200,
              moves_per_sweep: int | None = None) -> dict:
    """SA over one-hot plans: a move reassigns one group to another shelter (one-hot never broken).

    Minimises the same penalised energy h_xy as the XY circuit, with the schedule of simulated_annealing
    (T0 = 2 (P - 1), T *= 0.9 per sweep). Returns the final best plan by energy and, separately, the
    cheapest verified-feasible plan visited (a verifier in the loop).
    """
    G, S = inst["G"], inst["S"]
    m = moves_per_sweep or G * S
    h = sd["h_xy"]
    w = S ** np.arange(G - 1, -1, -1)  # subspace index of a plan
    scale = max(sd["P"] - 1.0, 1e-9)
    best_k, best_e, best_feas_k, best_feas_c = None, math.inf, None, math.inf
    t0 = time.perf_counter()
    for _ in range(restarts):
        a = rng.integers(0, S, G)
        k = int(a @ w)
        e = h[k]
        T = 2.0 * scale
        for _ in range(sweeps):
            for _ in range(m):
                g = int(rng.integers(G))
                s_new = (a[g] + 1 + int(rng.integers(S - 1))) % S
                k2 = k + (s_new - a[g]) * int(w[g])
                de = h[k2] - e
                if de <= 0 or rng.random() < math.exp(-de / T):
                    a[g], k, e = s_new, k2, h[k2]
                    if sd["feas"][k] and sd["cost"][k] < best_feas_c:
                        best_feas_k, best_feas_c = k, sd["cost"][k]
            T *= 0.9
        if sd["feas"][k] and sd["cost"][k] < best_feas_c:
            best_feas_k, best_feas_c = k, sd["cost"][k]
        if e < best_e:
            best_k, best_e = k, e
    return {"k": best_k, "feas_k": best_feas_k, "ms": (time.perf_counter() - t0) * 1000}
