"""P1 third revision, M3: fixed angles at G = 5..10 groups (15..30 qubits) -> <work>/p1_sub.json.

The ring-XY and Grover circuits are simulated exactly on the 3^G one-hot amplitudes (qaoa_sim.SubQaoa),
which agrees with the full 2^(3G) statevector to 1e-15 at G = 4 and 5 (checked here before the run).
Instances: twin seeds 42 + 17 i, i = 30, 31, ..., with the benchmark disruption of the main study (R5 closed,
Shelter A receives half its capacity) and the first G groups; the first 30 feasible instances per size are kept.
For each instance: angles fixed on the 12-qubit development set (p1_r3.json, rules popt / energy / cvar) are
applied unchanged, and per-instance training uses the main procedure (seed i, COBYLA, p = 1..4).
usage: .venv\\Scripts\\python.exe exp_p1_sub.py <work>
"""
import json
import sys
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
sys.path[:0] = [str(ROOT), str(HERE.parent), str(HERE)]
import qaoa_sim as Q  # noqa: E402
from exp_p1_v2 import GroverQaoa, train  # noqa: E402

WORK = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
SIZES = (5, 6, 7, 8, 9, 10)
N_PER = 30
RULES = ("popt", "energy", "cvar")


def disrupted_g(seed, G):
    from backend.simulation.hqrl_demo import HqrlConfig, HqrlEngine
    e = HqrlEngine(config=HqrlConfig(seed=seed, n_groups=max(6, G)))  # first 6 groups identical to n_groups=6
    e._close_road("R5", "benchmark flood")
    s = e.shelters["SA"]
    s["occupancy"] = min(s["capacity"], s["occupancy"] + int(s["capacity"] * 0.5))
    s["remaining"] = s["capacity"] - s["occupancy"]
    return e


def instance(G, i):
    inst = Q.instance_from_engine(disrupted_g(42 + 17 * i, G), G)
    sd = Q.subspace_diag(inst)
    return inst, sd


def validate():
    from exp_p1 import disrupted
    rng = np.random.default_rng(1)
    worst = 0.0
    for G in (4, 5):
        for i in (30, 31):
            inst = Q.instance_from_engine(disrupted(42 + 17 * i), G)
            inst2, sd = instance(G, i)
            assert np.array_equal(inst["cost"], inst2["cost"]) and np.array_equal(inst["rem"], inst2["rem"])
            d = Q.diagonals(inst, Q.bit_table(3 * G))
            for kind in ("xy", "grover"):
                full = Q.Qaoa(inst, "xy", d) if kind == "xy" else GroverQaoa(inst, d)
                sub = Q.SubQaoa(inst, kind, sd)
                for _ in range(4):
                    th = rng.uniform(0, 3, 8)
                    worst = max(worst, float(np.abs(full.state(th)[sd["full_index"]] - sub.state(th)).max()))
    assert worst < 1e-10, worst
    return worst


def job(args):
    G, i = args
    t0 = time.perf_counter()
    inst, sd = instance(G, i)
    best = float(np.min(sd["obj"]))
    opt = sd["obj"] <= best + 1e-6
    fx = json.loads((WORK / "p1_r3.json").read_text(encoding="utf-8"))["fixed"]
    naive = tuple(int(np.argmin(np.where(inst["forb"][g], np.inf, inst["cost"][g]))) for g in range(G))
    k_best = int(np.argmin(sd["obj"]))
    out = {"G": G, "i": i, "uniform": float(opt.sum() / 3 ** G), "n_feas": int(sd["feas"].sum()),
           "uni_feas": float(opt.sum() / sd["feas"].sum()), "binding": naive != tuple(sd["plans"][k_best])}
    for kind in ("xy", "grover"):
        qa = Q.SubQaoa(inst, kind, sd)
        for rule in RULES:
            pr = np.abs(qa.state(np.asarray(fx[f"{kind}:1.0:4:{rule}"]))) ** 2
            out[f"{kind}:{rule}"] = float(pr[opt].sum())
            out[f"{kind}:{rule}:feas"] = float(pr[sd["feas"]].sum())
        tr = train(Q.SubQaoa(inst, kind, sd), opt, sd["feas"], i)
        out[f"{kind}:trained"] = tr[3]["popt"]
        out[f"{kind}:trained:feas"] = tr[3]["pfeas"]
        out[f"{kind}:nfev"] = sum(x["nfev"] for x in tr)
    out["sec"] = time.perf_counter() - t0
    return out


if __name__ == "__main__":
    t0 = time.time()
    worst = validate()
    print("subspace simulator agrees with the full statevector, max |diff| =", worst, flush=True)
    jobs, screened = [], {}
    for G in SIZES:
        ids, i = [], 30
        while len(ids) < N_PER:
            inst, sd = instance(G, i)
            if np.isfinite(sd["obj"]).any():
                ids.append(i)
            i += 1
        screened[G] = {"ids": ids, "tried": i - 30}
        jobs += [(G, k) for k in ids]
        print(f"G={G}: {N_PER} feasible of {i - 30} tried", flush=True)
    jobs.sort(key=lambda j: -j[0])
    rows = []
    with Pool(4) as pl:
        for r in pl.imap_unordered(job, jobs):
            rows.append(r)
            print(f"G={r['G']} i={r['i']} xy fixed(E)={r['xy:energy']:.3f} trained={r['xy:trained']:.3f} "
                  f"gm fixed(E)={r['grover:energy']:.3f} trained={r['grover:trained']:.3f} {time.time() - t0:.0f}s",
                  flush=True)
    rows.sort(key=lambda r: (r["G"], r["i"]))
    (WORK / "p1_sub.json").write_text(json.dumps({"validate_max_diff": worst, "screened": screened, "rows": rows}),
                                      encoding="utf-8")
    print("done", f"{time.time() - t0:.0f}s")
