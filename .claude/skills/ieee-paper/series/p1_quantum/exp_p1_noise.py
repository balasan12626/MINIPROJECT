"""P1 gate-level noise study -> <work>/p1_noise.json.

Retrains mean-objective QAOA (X and XY mixers, p = 1..4) on the first 10 instances with the same
procedure as exp_p1.py, then estimates P_opt under two-qubit Pauli noise by quantum trajectories:
every two-qubit gate (one-hot and overload ZZ couplings, XY mixer pairs, W-state preparation)
fails with probability eps, and a failure applies one of the 15 non-identity two-qubit Paulis,
uniformly. Errors are inserted after the layer step (cost or mixer) that contains the gate.
Single-qubit errors are ignored. Also reports the global-depolarising prediction for the same
circuits, so the two noise models can be compared.
usage: .venv\\Scripts\\python.exe exp_p1_noise.py <work>
"""
import itertools
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[4]), str(HERE.parent), str(HERE)]
import qaoa_sim as Q  # noqa: E402
from exp_p1 import disrupted  # noqa: E402

WORK = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
G, S, N_INST, TRAJ = 4, 3, 10, 200
EPS = (0.001, 0.005, 0.01, 0.02)
W_GATES = 4  # two-qubit gates charged per W_3 preparation (same charge as the global model)
n = G * S
bits = Q.bit_table(n)
idx = np.arange(2 ** n, dtype=np.int64)
signs = [(1 - 2 * ((idx >> q) & 1)).astype(np.float64) for q in range(n)]
PAULIS = [(a, b) for a in "IXYZ" for b in "IXYZ" if (a, b) != ("I", "I")]


def apply_1q(psi, q, pauli):
    if pauli in ("Z", "Y"):
        psi = psi * signs[q]
    if pauli in ("X", "Y"):
        psi = psi[idx ^ (1 << q)]
    return psi  # Y = iXZ; the global phase i does not affect probabilities


def noisy_layer(psi, gates, eps, rng):
    for (a, b) in gates:
        if rng.random() < eps:
            pa, pb = PAULIS[rng.integers(len(PAULIS))]
            if pa != "I":
                psi = apply_1q(psi, a, pa)
            if pb != "I":
                psi = apply_1q(psi, b, pb)
    return psi


def run_noisy(qa, theta, cost_gates, mix_gates, prep_gates, eps, rng):
    p = len(theta) // 2
    psi = noisy_layer(qa.psi0.copy(), prep_gates, eps, rng)
    for k in range(p):
        psi = psi * np.exp(-1j * theta[k] * qa.hn)
        psi = noisy_layer(psi, cost_gates, eps, rng)
        if qa.kind == "x":
            Q._apply_rx_all(psi, qa.n, theta[p + k])
        else:
            Q._apply_xy(psi, qa.pairs, theta[p + k])
            psi = noisy_layer(psi, mix_gates, eps, rng)
    return np.abs(psi) ** 2


rows = []
for i in range(N_INST):
    inst = Q.instance_from_engine(disrupted(42 + 17 * i), G)
    d = Q.diagonals(inst, bits)
    ex = Q.exact_solve(inst)
    opt = d["obj"] <= ex["obj"] + 1e-6
    ov = [(g * S + s, h * S + s) for g, h, s in Q.overload_pairs(inst)]
    onehot = [(g * S + a, g * S + b) for g in range(G) for a, b in itertools.combinations(range(S), 2)]
    ring = [(g * S + a, g * S + (a + 1) % S) for g in range(G) for a in range(S)]
    for kind in ("x", "xy"):
        qa = Q.Qaoa(inst, kind, d)
        rng_train = np.random.default_rng(i)
        cost_gates = (onehot + ov) if kind == "x" else ov
        mix_gates = ring if kind == "xy" else []
        prep_gates = [ring[g * S + (j % S)] for g in range(G) for j in range(W_GATES)] if kind == "xy" else []
        warm = None
        for p in (1, 2, 3, 4):
            th, _ = qa.optimise(p, rng_train, restarts=2, warm=warm)
            warm = th
            ideal = float((np.abs(qa.state(th)) ** 2)[opt].sum())
            n2 = len(prep_gates) + p * (len(cost_gates) + len(mix_gates))
            for eps in EPS:
                rng = np.random.default_rng(10_000 * i + 100 * p + int(eps * 1000))
                acc = 0.0
                for _ in range(TRAJ):
                    acc += float(run_noisy(qa, th, cost_gates, mix_gates, prep_gates, eps, rng)[opt].sum())
                F = (1 - eps) ** n2
                rows.append({"i": i, "kind": kind, "p": p, "eps": eps, "n2": n2, "ideal": ideal,
                             "traj": acc / TRAJ, "global": F * ideal + (1 - F) * opt.sum() / 2 ** n})
    print(f"instance {i} done", flush=True)

summ = []
for kind in ("x", "xy"):
    for p in (1, 2, 3, 4):
        for eps in EPS:
            rr = [r for r in rows if r["kind"] == kind and r["p"] == p and r["eps"] == eps]
            summ.append({"kind": kind, "p": p, "eps": eps, "ideal": float(np.mean([r["ideal"] for r in rr])),
                         "traj": float(np.mean([r["traj"] for r in rr])),
                         "traj_sd": float(np.std([r["traj"] for r in rr])),
                         "global": float(np.mean([r["global"] for r in rr])),
                         "n2": float(np.mean([r["n2"] for r in rr]))})
(WORK / "p1_noise.json").write_text(json.dumps({"n_inst": N_INST, "traj": TRAJ, "w_gates": W_GATES,
                                                "summary": summ, "rows": rows}, indent=1), encoding="utf-8")
for s in summ:
    if s["p"] == 4:
        print(s)
