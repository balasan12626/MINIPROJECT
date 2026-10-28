"""P1: transfer across problem size, and fixed angles under gate noise -> <work>/p1_size.json.

size  - the angles fixed on the 12-qubit development set (p1_holdout.json, G = 4) are applied unchanged
        to new twin instances with G = 5 (15 qubits) and G = 6 (18 qubits), seeds 42 + 17 i, i = 30..39.
        Per-instance training with the main procedure (seed i) is run for comparison (XY, mean objective;
        also CVaR at G = 5).
noise - on the 10 new 12-qubit instances i = 30..39, fixed and per-instance trained XY circuits at p = 4
        are run through the gate-level Pauli-trajectory model of exp_p1_noise.py (200 runs, eps 0.005 and
        0.01), so the transfer result is checked under noise.
usage: .venv\\Scripts\\python.exe exp_p1_size.py <work>
"""
import itertools
import json
import sys
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[4]), str(HERE.parent), str(HERE)]
import qaoa_sim as Q  # noqa: E402
from exp_p1 import disrupted  # noqa: E402
from exp_p1_v2 import train  # noqa: E402

WORK = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
S, TRAJ, EPS, W_GATES = 3, 200, (0.005, 0.01), 4
PAULIS = [(a, b) for a in "IXYZ" for b in "IXYZ" if (a, b) != ("I", "I")]


def fixed_angles():
    ho = json.loads((WORK / "p1_holdout.json").read_text(encoding="utf-8"))
    return {k: np.asarray(v["theta"]) for k, v in ho["fixed"].items()}


def size_job(args):
    G, i, alpha = args
    t0 = time.perf_counter()
    inst = Q.instance_from_engine(disrupted(42 + 17 * i), G)
    ex = Q.exact_solve(inst)
    if not np.isfinite(ex["obj"]):
        return {"G": G, "i": i, "alpha": alpha, "feasible_instance": False}
    d = Q.diagonals(inst, Q.bit_table(3 * G))
    opt = d["obj"] <= ex["obj"] + 1e-6
    fx = fixed_angles()
    out = {"G": G, "i": i, "alpha": alpha, "feasible_instance": True, "uniform": float(opt.sum() / 3 ** G),
           "exact_ms": ex["ms"], "n_feasible": int(d["feas"].sum())}
    qa = Q.Qaoa(inst, "xy", d, alpha=alpha)
    for p in (1, 2, 3, 4):
        pr = np.abs(qa.state(fx[f"xy:{alpha}:{p}"])) ** 2
        out[f"fixed_p{p}"] = float(pr[opt].sum())
        out[f"fixed_feas_p{p}"] = float(pr[d["feas"]].sum())
    tr = train(Q.Qaoa(inst, "xy", d, alpha=alpha), opt, d["feas"], i)
    for p in (1, 2, 3, 4):
        out[f"trained_p{p}"] = tr[p - 1]["popt"]
        out[f"trained_cum_nfev_p{p}"] = sum(x["nfev"] for x in tr[:p])
    out["sec"] = time.perf_counter() - t0
    return out


def noise_job(i):
    G = 4
    n = G * S
    idx = np.arange(2 ** n, dtype=np.int64)
    signs = [(1 - 2 * ((idx >> q) & 1)).astype(np.float64) for q in range(n)]

    def apply_1q(psi, q, pauli):
        if pauli in ("Z", "Y"):
            psi = psi * signs[q]
        if pauli in ("X", "Y"):
            psi = psi[idx ^ (1 << q)]
        return psi

    def noisy_layer(psi, gates, eps, rng):
        for (a, b) in gates:
            if rng.random() < eps:
                pa, pb = PAULIS[rng.integers(len(PAULIS))]
                if pa != "I":
                    psi = apply_1q(psi, a, pa)
                if pb != "I":
                    psi = apply_1q(psi, b, pb)
        return psi

    inst = Q.instance_from_engine(disrupted(42 + 17 * i), G)
    d = Q.diagonals(inst, Q.bit_table(n))
    ex = Q.exact_solve(inst)
    opt = d["obj"] <= ex["obj"] + 1e-6
    ov = [(g * S + s, h * S + s) for g, h, s in Q.overload_pairs(inst)]
    ring = [(g * S + a, g * S + (a + 1) % S) for g in range(G) for a in range(S)]
    prep = [ring[g * S + (j % S)] for g in range(G) for j in range(W_GATES)]
    qa = Q.Qaoa(inst, "xy", d)
    tr = train(Q.Qaoa(inst, "xy", d), opt, d["feas"], i)
    angles = {"fixed": fixed_angles()["xy:1.0:4"], "trained": np.asarray(tr[3]["theta"])}
    out = {"i": i}
    for name, th in angles.items():
        out[f"{name}_ideal"] = float((np.abs(qa.state(th)) ** 2)[opt].sum())
        for eps in EPS:
            rng = np.random.default_rng(10_000 * i + int(eps * 1000))
            acc = 0.0
            for _ in range(TRAJ):
                psi = noisy_layer(qa.psi0.copy(), prep, eps, rng)
                for k in range(4):
                    psi = psi * np.exp(-1j * th[k] * qa.hn)
                    psi = noisy_layer(psi, ov, eps, rng)
                    Q._apply_xy(psi, qa.pairs, th[4 + k])
                    psi = noisy_layer(psi, ring, eps, rng)
                acc += float((np.abs(psi) ** 2)[opt].sum())
            out[f"{name}_eps{eps}"] = acc / TRAJ
    return out


if __name__ == "__main__":
    t0 = time.time()
    jobs = [(5, i, a) for i in range(30, 40) for a in (1.0, 0.1)] + [(6, i, 1.0) for i in range(30, 40)]
    jobs.sort(key=lambda j: -j[0])  # start the slow 18-qubit jobs first
    with Pool(3) as pool:
        size = []
        for r in pool.imap_unordered(size_job, jobs):
            size.append(r)
            print(f"size G={r['G']} i={r['i']} a={r['alpha']} "
                  + (f"fixed={r['fixed_p4']:.3f} trained={r['trained_p4']:.3f}" if r["feasible_instance"] else "infeasible")
                  + f" {time.time() - t0:.0f}s", flush=True)
        noise = list(pool.imap_unordered(noise_job, range(30, 40)))
    (WORK / "p1_size.json").write_text(json.dumps({"size": size, "noise": noise, "traj": TRAJ, "eps": EPS}),
                                       encoding="utf-8")
    print("done", f"{time.time() - t0:.0f}s")
