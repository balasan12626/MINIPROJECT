"""P1 second revision -> <work>/p1_r2.json. Needs p1_v2.json and p1_holdout.json.

  feasgm   - a mixer restricted to the FEASIBLE subspace: Grover mixer whose start state is the uniform
             superposition of the plans that satisfy every constraint, capacity included (the subspace an
             LX/Grover construction would preserve). Trained per development instance with the same
             procedure as the other mixers (seed 0, mean objective, p = 1..4).
  norm     - is the shared energy scale what makes transfer work? XY/mean is re-trained on the 30
             development instances (seed 0) with (a) no scaling (raw shifted energies, scale = 1) and
             (b) a different normalisation (divide by the standard deviation of the penalty-free plan
             energies); one angle set per depth is fixed by eq. (6) on the development set and applied
             unchanged to the 30 held-out instances, exactly as for the deployed scaling.
  strong   - stronger per-instance baselines on the held-out instances (XY/mean): best of 5 COBYLA seeds
             (5x the budget), COBYLA warm-started from the transferred angles with the full 250-evaluation
             budget per depth, and L-BFGS-B (finite-difference gradients, 600 evaluations per start,
             same starts as COBYLA).
usage: .venv\\Scripts\\python.exe exp_p1_r2.py <work>
"""
import json
import math
import sys
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[4]), str(HERE.parent), str(HERE)]
import qaoa_sim as Q  # noqa: E402
from exp_p1_v2 import load, train  # noqa: E402

WORK = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
DEPTHS = (1, 2, 3, 4)


class FeasGrover(Q.Qaoa):
    """Grover mixer over the feasible subspace: |s> = uniform over plans that satisfy (one-hot, forbidden, capacity)."""

    def __init__(self, inst, diag):
        super().__init__(inst, "xy", diag)
        f = diag["feas"].astype(np.float64)
        self.psi0 = (f / math.sqrt(f.sum())).astype(np.complex128)
        self.kind = "feasgm"

    def state(self, theta):
        p = len(theta) // 2
        psi = self.psi0.copy()
        s = self.psi0
        for k in range(p):
            psi *= np.exp(-1j * theta[k] * self.hn)
            psi += (np.exp(-1j * theta[p + k]) - 1.0) * np.vdot(s, psi) * s
        return psi


class Rescaled(Q.Qaoa):
    """XY QAOA with a different energy normalisation (mode 'none' or 'std')."""

    def __init__(self, inst, diag, mode):
        super().__init__(inst, "xy", diag)
        if mode == "none":
            self.scale = 1.0
        else:
            free = diag["onehot"] & (diag["h_xy"] <= diag["P"] - 1.0 + 1e-9)
            self.scale = max(float(np.std(self.h[free])), 1e-9)
        self.hn = self.h / self.scale
        self.order = np.argsort(self.hn, kind="stable")
        self.hn_sorted = self.hn[self.order]


def train_lbfgs(qa, opt, feas, seed, maxfun=600):
    rng = np.random.default_rng(seed)
    warm, out = None, []
    for p in DEPTHS:
        nf0 = qa.nfev
        starts = []
        if warm is not None:
            q = len(warm) // 2
            xs = np.linspace(0, 1, q) if q > 1 else np.array([0.0])
            xn = np.linspace(0, 1, p)
            starts.append(np.concatenate([np.interp(xn, xs, warm[:q]), np.interp(xn, xs, warm[q:])]))
        for _ in range(2):
            starts.append(np.concatenate([rng.uniform(0, math.pi, p), rng.uniform(0, math.pi / 2, p)]))
        best_t, best_e = None, math.inf
        for t0 in starts:
            r = minimize(qa.energy, t0, method="L-BFGS-B", options={"maxfun": maxfun})
            if r.fun < best_e:
                best_t, best_e = r.x, float(r.fun)
        warm = best_t
        pr = np.abs(qa.state(best_t)) ** 2
        out.append({"p": p, "popt": float(pr[opt].sum()), "nfev": qa.nfev - nf0})
    return out


def pool_of(ids):
    out = {}
    for i in ids:
        inst, d, ex = load(i)
        if np.isfinite(ex["obj"]):
            out[i] = (inst, d, d["obj"] <= ex["obj"] + 1e-6)
    return out


def job(args):
    task, i = args
    inst, d, ex = load(i)
    if not np.isfinite(ex["obj"]):
        return None
    opt = d["obj"] <= ex["obj"] + 1e-6
    t0 = time.perf_counter()
    if task == "feasgm":
        runs = train(FeasGrover(inst, d), opt, d["feas"], i)
    elif task.startswith("norm"):
        mode = task.split(":")[1]
        runs = train(Rescaled(inst, d, mode), opt, d["feas"], i)
    elif task.startswith("cobyla5"):
        runs = [train(Q.Qaoa(inst, "xy", d), opt, d["feas"], i + 10007 * k) for k in range(5)]
    elif task == "lbfgs":
        runs = train_lbfgs(Q.Qaoa(inst, "xy", d), opt, d["feas"], i)
    elif task == "warm250":
        H = json.loads((WORK / "p1_holdout.json").read_text(encoding="utf-8"))
        runs = []
        for p in DEPTHS:
            qa = Q.Qaoa(inst, "xy", d)
            th = np.asarray(H["fixed"][f"xy:1.0:{p}"]["theta"])
            r = minimize(qa.energy, th, method="COBYLA", options={"maxiter": 250, "rhobeg": 0.1})
            pr = np.abs(qa.state(r.x)) ** 2
            runs.append({"p": p, "popt": float(pr[opt].sum()), "nfev": qa.nfev})
    return {"task": task, "i": i, "runs": runs, "sec": time.perf_counter() - t0}


if __name__ == "__main__":
    t_start = time.time()
    dev_ids, new_ids = range(30), range(30, 60)
    tasks = [("feasgm", i) for i in dev_ids] + [(f"norm:{m}", i) for m in ("none", "std") for i in dev_ids]
    tasks += [(t, i) for t in ("cobyla5", "lbfgs", "warm250") for i in new_ids]
    res = []
    with Pool(3) as pool:
        for n, r in enumerate(pool.imap_unordered(job, tasks), 1):
            if r:
                res.append(r)
            if n % 15 == 0:
                print(f"{n}/{len(tasks)} {time.time() - t_start:.0f}s", flush=True)
    out = {"rows": res}
    # transfer under the alternative normalisations: fix on dev by eq. (6), apply unchanged to new instances
    dev, new = pool_of(dev_ids), pool_of(new_ids)
    out["norm_transfer"] = {}
    for mode in ("none", "std"):
        trained = {r["i"]: r["runs"] for r in res if r["task"] == f"norm:{mode}"}
        qd = {i: Rescaled(dev[i][0], dev[i][1], mode) for i in dev}
        qn = {i: Rescaled(new[i][0], new[i][1], mode) for i in new}
        pop = lambda q, opt, th: float((np.abs(q.state(np.asarray(th))) ** 2)[opt].sum())  # noqa: E731
        for p in DEPTHS:
            cands = [trained[i][p - 1]["theta"] for i in sorted(dev)]
            score = [np.mean([pop(qd[t], dev[t][2], th) for t in dev]) for th in cands]
            fixed = cands[int(np.argmax(score))]
            out["norm_transfer"][f"{mode}:{p}"] = {
                "dev_trained": float(np.mean([trained[i][p - 1]["popt"] for i in dev])),
                "dev_fixed": float(max(score)),
                "new_fixed": [pop(qn[i], new[i][2], fixed) for i in sorted(new)]}
    (WORK / "p1_r2.json").write_text(json.dumps(out), encoding="utf-8")
    print("done", f"{time.time() - t_start:.0f}s")
    for k, v in out["norm_transfer"].items():
        print(k, round(v["dev_trained"], 3), round(v["dev_fixed"], 3), round(float(np.mean(v["new_fixed"])), 3))
