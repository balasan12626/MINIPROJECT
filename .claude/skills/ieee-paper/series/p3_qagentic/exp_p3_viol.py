"""Why is the most frequent sample invalid? -> <work>/p3_viol.json.

Re-runs the twin and city studies of exp_p3_v2.py with the same seeds and code path, and classifies the
most frequent sample of every fixed-budget draw by the first rule of (1) it breaks:
  onehot     - a group has no shelter or several (decode() returned None)
  forbidden  - a group is sent to a forbidden pair (no open path, failed shelter, too large)
  blind      - a shelter is overfilled although every pair of groups in it fits: the pairwise QUBO
               penalty is zero, so the energy cannot see the violation
  pair       - a shelter is overfilled and contains a penalised pair
  valid      - passes (1)
raw_invalid from the original run_loop is stored next to each class, so post_p3.py can check that the
re-run reproduces p3_v2.json draw for draw. The city MILP is skipped (feasibility is taken from p3_v2.json).
usage: .venv\\Scripts\\python.exe exp_p3_viol.py <work>
"""
import json
import sys
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np

import exp_p3_v2 as E

WORK = Path(sys.argv[1])
_run_loop = E.run_loop
CAP = []


def classify(a, forb, sizes, rem):
    if a is None:
        return "onehot"
    if any(forb[g, s] for g, s in enumerate(a)):
        return "forbidden"
    rem = np.asarray(rem, dtype=float)
    load = np.zeros(len(rem))
    for g, s in enumerate(a):
        load[s] += sizes[g]
    over = [s for s in range(len(rem)) if load[s] > rem[s] + 1e-9]
    if not over:
        return "valid"
    for s in over:
        gs = [g for g, t in enumerate(a) if t == s]
        if any(sizes[g] + sizes[h] > rem[s] for i, g in enumerate(gs) for h in gs[i + 1:]):
            return "pair"
    return "blind"


def run_loop(samples, cost, forb, sizes, rem, opt_obj, feasible_exists, adaptive):
    out = _run_loop(samples, cost, forb, sizes, rem, opt_obj, feasible_exists, adaptive)
    if not adaptive:
        cnt = {}
        for a in samples:
            cnt[a] = cnt.get(a, 0) + 1
        top = max(cnt, key=cnt.get)
        CAP.append({"cls": classify(top, forb, sizes, rem), "raw_invalid": bool(out["raw_invalid"])})
    return out


def no_milp(cost, forb, sizes, rem):
    return None, np.inf, 0.0, 9  # city: feasibility comes from p3_v2.json


def twin(i):
    E.run_loop = run_loop
    CAP.clear()
    rows = E.twin_job(i)
    # per event: qaoa draws then sa draws (adaptive calls are not captured)
    per = 2 * E.DRAWS
    assert len(CAP) == per * len(rows)
    return [{"seed": r["seed"], "event": r["event"],
             "qaoa": CAP[j * per:j * per + E.DRAWS], "sa": CAP[j * per + E.DRAWS:(j + 1) * per]}
            for j, r in enumerate(rows)]


def city(args):
    E.run_loop = run_loop
    E.milp_solve = no_milp
    CAP.clear()
    E.city_job(args)
    assert len(CAP) == E.DRAWS
    return {"city": args[0], "G": args[1], "tight": args[2], "k": args[3], "sa": list(CAP)}


if __name__ == "__main__":
    t0 = time.time()
    out = {}
    with Pool(3) as pool:
        tw = []
        for rows in pool.imap_unordered(twin, range(30)):
            tw += rows
            print(f"twin {len(tw)} events {time.time() - t0:.0f}s", flush=True)
        out["twin"] = tw
        jobs = [(c, G, t, k) for c in E.CITIES for G in (8, 16, 32) for t in (0.6, 0.9) for k in range(10)]
        cc = []
        for r in pool.imap_unordered(city, jobs):
            cc.append(r)
            if len(cc) % 30 == 0:
                print(f"city {len(cc)}/{len(jobs)} {time.time() - t0:.0f}s", flush=True)
        out["city"] = cc
    (WORK / "p3_viol.json").write_text(json.dumps(out), encoding="utf-8")
    print("done", f"{time.time() - t0:.0f}s")
