"""P1 fourth revision (scaled down for a laptop) -> <work>/p1_r4_sub.json and <work>/p1_r4_dis.json.

sub  (M3) fixed angles at G groups (3G qubits), simulated exactly on the 3^G one-hot amplitudes (qaoa_sim.SubQaoa,
     validated against the full statevector in exp_p1_sub.validate). Instances: twin seeds 42 + 17 i, i = 30, 31, ...,
     benchmark disruption (R5 closed, Shelter A receives half its capacity), first G groups, first N_SUB feasible
     instances per size. XY mixer, mean objective, p = 4: the development-set angle sets of rule popt (eq. 7) and of
     the energy rule (p1_r3.json) applied unchanged, against per-instance training with the main procedure
     (exp_p1_v2.train: COBYLA <= 250 evaluations per start, depths 1..4, 2 random starts + INTERP, seed i).
dis  (M2) held-out 12-qubit instances with other disruptions (exp_p1_r3.disrupted_var: two other roads closed;
     Shelter B failed + one other road closed; Shelter C capacity cut of 30 % or 70 % + one other road closed),
     seeds 42 + 17 i, i >= 100, first N_DIS feasible instances per pattern. XY mixer, mean objective, p = 4:
     fixed sets of rules popt / energy / cvar against per-instance training (same procedure, seed i).
time  one job of each kind, for planning.
usage: .venv\\Scripts\\python.exe exp_p1_r4.py <work> time|sub|dis [sizes, e.g. 5,6,7] [n] [procs]
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
from exp_p1_v2 import train  # noqa: E402

WORK = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
PHASE = sys.argv[2] if len(sys.argv) > 2 else "time"
SUB_RULES = ("popt", "energy")
DIS_RULES = ("popt", "energy", "cvar")
PATTERNS = ("roads", "shelter", "capacity")


def fixed_sets():
    return json.loads((WORK / "p1_r3.json").read_text(encoding="utf-8"))["fixed"]


def sub_instance(G, i):
    from exp_p1_sub import disrupted_g
    inst = Q.instance_from_engine(disrupted_g(42 + 17 * i, G), G)
    return inst, Q.subspace_diag(inst)


def sub_job(args):
    G, i = args
    t0 = time.perf_counter()
    inst, sd = sub_instance(G, i)
    best = float(np.min(sd["obj"]))
    opt = sd["obj"] <= best + 1e-6
    naive = tuple(int(np.argmin(np.where(inst["forb"][g], np.inf, inst["cost"][g]))) for g in range(G))
    out = {"G": G, "i": i, "n_opt": int(opt.sum()), "uniform": float(opt.sum() / 3 ** G),
           "n_feas": int(sd["feas"].sum()), "binding": naive != tuple(sd["plans"][int(np.argmin(sd["obj"]))])}
    fx = fixed_sets()
    qa = Q.SubQaoa(inst, "xy", sd)
    for rule in SUB_RULES:
        pr = np.abs(qa.state(np.asarray(fx[f"xy:1.0:4:{rule}"]))) ** 2
        out[rule] = float(pr[opt].sum())
        out[f"{rule}:feas"] = float(pr[sd["feas"]].sum())
    t1 = time.perf_counter()
    tr = train(Q.SubQaoa(inst, "xy", sd), opt, sd["feas"], i)
    out["trained"] = tr[3]["popt"]
    out["trained:feas"] = tr[3]["pfeas"]
    out["nfev"] = sum(x["nfev"] for x in tr)
    out["sec_train"] = time.perf_counter() - t1
    out["sec"] = time.perf_counter() - t0
    return out


def dis_job(args):
    pattern, i = args
    from exp_p1_r3 import binding, disrupted_var
    t0 = time.perf_counter()
    eng, desc = disrupted_var(42 + 17 * i, pattern)
    inst = Q.instance_from_engine(eng, 4)
    ex = Q.exact_solve(inst)
    if not np.isfinite(ex["obj"]):
        return {"pattern": pattern, "i": i, "feasible_instance": False}
    d = Q.diagonals(inst, Q.bit_table(12))
    opt = d["obj"] <= ex["obj"] + 1e-6
    row = {"pattern": pattern, "i": i, "feasible_instance": True, "desc": desc, "binding": binding(inst, ex),
           "n_opt": int(opt.sum()), "uniform": float(opt.sum() / 81), "n_feas": int(d["feas"].sum())}
    fx = fixed_sets()
    qa = Q.Qaoa(inst, "xy", d)
    for rule in DIS_RULES:
        pr = np.abs(qa.state(np.asarray(fx[f"xy:1.0:4:{rule}"]))) ** 2
        row[rule] = float(pr[opt].sum())
    tr = train(Q.Qaoa(inst, "xy", d), opt, d["feas"], i)
    row["trained"] = tr[3]["popt"]
    row["nfev"] = sum(x["nfev"] for x in tr)
    row["sec"] = time.perf_counter() - t0
    return row


def screen_sub(G, n):
    ids, i = [], 30
    while len(ids) < n:
        _, sd = sub_instance(G, i)
        if np.isfinite(sd["obj"]).any():
            ids.append(i)
        i += 1
    return ids, i - 30


def run_pool(fn, jobs, procs):
    if procs <= 1:
        return [fn(j) for j in jobs]
    with Pool(procs) as pl:
        return list(pl.imap_unordered(fn, jobs))


if __name__ == "__main__":
    t0 = time.time()
    if PHASE == "time":
        for G in (5, 6, 7, 8):
            r = sub_job((G, 30))
            print(f"sub G={G}: total {r['sec']:.1f}s, training {r['sec_train']:.1f}s, nfev {r['nfev']}, "
                  f"popt {r['popt']:.3f} energy {r['energy']:.3f} trained {r['trained']:.3f}", flush=True)
        for pat in PATTERNS:
            r = dis_job((pat, 100))
            print(f"dis {pat}: {r}", flush=True)
    elif PHASE == "sub":
        sizes = tuple(int(x) for x in sys.argv[3].split(","))
        n, procs = int(sys.argv[4]), int(sys.argv[5])
        out_path = WORK / "p1_r4_sub.json"
        store = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else {"screened": {}, "rows": []}
        for G in sizes:
            ids, tried = screen_sub(G, n)
            rows = []
            for r in run_pool(sub_job, [(G, i) for i in ids], procs):
                rows.append(r)
                print(f"G={G} i={r['i']} popt={r['popt']:.3f} energy={r['energy']:.3f} trained={r['trained']:.3f} "
                      f"{r['sec']:.0f}s total {time.time() - t0:.0f}s", flush=True)
            store["screened"][str(G)] = {"ids": ids, "tried": tried}
            store["rows"] = [x for x in store["rows"] if x["G"] != G] + sorted(rows, key=lambda x: x["i"])
            out_path.write_text(json.dumps(store), encoding="utf-8")  # saved after every size
            print(f"G={G} saved ({n} instances of {tried} tried)", flush=True)
    elif PHASE == "dis":
        n, procs = int(sys.argv[3]), int(sys.argv[4])
        rows, allrows = [], []
        for pat in PATTERNS:
            got, i = [], 100
            while len(got) < n:  # seed order; infeasible instances cost no training
                r = dis_job((pat, i))
                allrows.append({"pattern": pat, "i": i, "feasible_instance": r["feasible_instance"]})
                if r["feasible_instance"]:
                    got.append(r)
                    print(f"{pat} i={i} {r['desc']} popt={r['popt']:.3f} energy={r['energy']:.3f} "
                          f"cvar={r['cvar']:.3f} trained={r['trained']:.3f} {time.time() - t0:.0f}s", flush=True)
                i += 1
            rows += got
        (WORK / "p1_r4_dis.json").write_text(json.dumps({"rows": rows, "all": allrows}), encoding="utf-8")
    print("done", f"{time.time() - t0:.0f}s", flush=True)
