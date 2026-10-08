"""Worked example for P1 -> <work>/p1_example.json: instance 0 (seed 42), costs, optimum, greedy plan,
and the five most likely bitstrings of the trained depth-4 XY and X circuits (mean objective).
usage: .venv\\Scripts\\python.exe exp_p1_example.py <work>
"""
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[4]), str(HERE.parent), str(HERE)]
import qaoa_sim as Q  # noqa: E402
from exp_p1 import disrupted  # noqa: E402

WORK = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
G, S = 4, 3
inst = Q.instance_from_engine(disrupted(42), G)
d = Q.diagonals(inst)
ex = Q.exact_solve(inst)
opt = d["obj"] <= ex["obj"] + 1e-6
gr = Q.greedy(inst, sorted(range(G), key=lambda g: -inst["sizes"][g]))
out = {"sizes": inst["sizes"].tolist(), "remaining": inst["rem"].tolist(), "cost": np.round(inst["cost"], 2).tolist(),
       "forbidden": inst["forb"].tolist(), "optimum": list(ex["assign"]), "opt_cost": round(float(ex["obj"]), 2),
       "greedy": list(gr) if gr else None,
       "greedy_cost": round(float(sum(inst["cost"][g, s] for g, s in enumerate(gr))), 2) if gr else None,
       "n_feasible": int(d["feas"].sum()), "samples": {}}
for kind in ("xy", "x"):
    qa = Q.Qaoa(inst, kind, d)
    rng = np.random.default_rng(0)
    th = None
    for p in (1, 2, 3, 4):
        th, _ = qa.optimise(p, rng, restarts=2, warm=th)
    pr = np.abs(qa.state(th)) ** 2
    top = np.argsort(-pr)[:5]
    out["samples"][kind] = {"p_opt": float(pr[opt].sum()), "p_feas": float(pr[d["feas"]].sum()), "top": [
        {"assign": Q.index_to_assign(int(k), G, S), "prob": float(pr[k]), "feasible": bool(d["feas"][k]),
         "optimal": bool(opt[k]),
         "cost": round(float(sum(inst["cost"][g, s] for g, s in enumerate(Q.index_to_assign(int(k), G, S)))), 2)
         if Q.index_to_assign(int(k), G, S) else None}
        for k in top]}
(WORK / "p1_example.json").write_text(json.dumps(out, indent=1, default=lambda o: list(o)), encoding="utf-8")
print(json.dumps(out, indent=1, default=lambda o: list(o)))
