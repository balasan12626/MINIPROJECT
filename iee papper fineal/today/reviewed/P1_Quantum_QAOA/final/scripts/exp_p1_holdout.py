"""P1 held-out transfer test -> <work>/p1_holdout.json. Needs p1_v2.json.

One fixed angle set per (variant, depth) is chosen on the 30 development instances only (the trained
angle set with the highest mean P_opt over all 30), then applied unchanged to 30 NEW instances
(seeds 42 + 17 i, i = 30..59) that played no part in any choice. On the new instances we also train
per instance with the same procedure as the main study (seed i) and fine-tune the fixed angles with
at most FT evaluations.
"""
import json
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[4]), str(HERE.parent), str(HERE)]
import qaoa_sim as Q  # noqa: E402
from exp_p1_v2 import load, train  # noqa: E402

FT = 30
work = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
res = json.loads((work / "p1_v2.json").read_text(encoding="utf-8"))["results"]
VARIANTS = (("xy", 1.0), ("xy", 0.1), ("x", 1.0))
dev = {}
for i in range(30):
    inst, d, ex = load(i)
    if np.isfinite(ex["obj"]):
        dev[i] = (inst, d, d["obj"] <= ex["obj"] + 1e-6)
new = {}
for i in range(30, 60):
    inst, d, ex = load(i)
    if np.isfinite(ex["obj"]):
        new[i] = (inst, d, d["obj"] <= ex["obj"] + 1e-6)


def popt(pool, i, k, a, th, cache={}):
    key = (id(pool), i, k, a)
    if key not in cache:
        cache[key] = Q.Qaoa(pool[i][0], k, pool[i][1], alpha=a)
    pr = np.abs(cache[key].state(np.asarray(th))) ** 2
    return float(pr[pool[i][2]].sum())


out = {"n_new": len(new), "n_new_infeasible": 30 - len(new), "ft_budget": FT, "fixed": {}, "rows": []}
for k, a in VARIANTS:
    trained = {r["i"]: {x["p"]: x for x in r["runs"]} for r in res
               if r["task"] == f"seed:{k}:{a}:0" and r["feasible_instance"]}
    for p in (1, 2, 3, 4):
        cands = [trained[i][p]["theta"] for i in sorted(dev)]
        score = [np.mean([popt(dev, t, k, a, th) for t in dev]) for th in cands]
        fixed = cands[int(np.argmax(score))]
        out["fixed"][f"{k}:{a}:{p}"] = {"theta": fixed, "dev_mean_popt": float(max(score)),
                                        "from_instance": sorted(dev)[int(np.argmax(score))]}
    for i in sorted(new):
        inst, d, opt = new[i]
        qa = Q.Qaoa(inst, k, d, alpha=a)
        tr = train(qa, opt, d["feas"], i)  # per-instance training, same procedure as the main study
        for p in (1, 2, 3, 4):
            th = out["fixed"][f"{k}:{a}:{p}"]["theta"]
            q2 = Q.Qaoa(inst, k, d, alpha=a)
            r = minimize(q2.energy, np.asarray(th), method="COBYLA", options={"maxiter": FT, "rhobeg": 0.1})
            pr = np.abs(q2.state(r.x)) ** 2
            out["rows"].append({"kind": k, "alpha": a, "p": p, "i": i,
                                "trained": tr[p - 1]["popt"], "trained_cum_nfev": sum(x["nfev"] for x in tr[:p]),
                                "fixed": popt(new, i, k, a, th), "ft": float(pr[opt].sum()), "ft_nfev": q2.nfev,
                                "uniform": float(opt.sum() / 81)})
    for p in (1, 2, 3, 4):
        rr = [x for x in out["rows"] if x["kind"] == k and x["alpha"] == a and x["p"] == p]
        print(k, a, p, "trained %.3f fixed %.3f ft %.3f" % tuple(np.mean([x[f] for x in rr])
                                                               for f in ("trained", "fixed", "ft")), flush=True)
(work / "p1_holdout.json").write_text(json.dumps(out), encoding="utf-8")
