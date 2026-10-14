"""P1 angle-transfer study -> <work>/p1_transfer.json. Needs p1_v2.json (trained angles, seed 0).

Leave-one-out, no information from the target instance is used to choose its angles:
  donor   - among the 29 other instances' trained angles, the set with the highest mean P_opt on
            the remaining 28 instances (target excluded) is applied to the target unchanged.
  median  - coordinate-wise median of the 29 other instances' trained angles.
  donor+ft- donor angles refined on the target with COBYLA, at most FT objective evaluations.
Variants: XY/mean and XY/CVaR at p = 1..4, and X/mean for comparison.
"""
import json
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[4]), str(HERE.parent), str(HERE)]
import qaoa_sim as Q  # noqa: E402
from exp_p1_v2 import load  # noqa: E402

FT = 30
work = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
res = json.loads((work / "p1_v2.json").read_text(encoding="utf-8"))["results"]
VARIANTS = (("xy", 1.0), ("xy", 0.1), ("x", 1.0))

cache = {}
for i in range(30):
    inst, d, ex = load(i)
    if np.isfinite(ex["obj"]):
        opt = d["obj"] <= ex["obj"] + 1e-6
        cache[i] = (inst, d, opt)
ids = sorted(cache)
qa_cache = {(i, k, a): Q.Qaoa(cache[i][0], k, cache[i][1], alpha=a) for i in ids for k, a in VARIANTS}


def popt(i, k, a, th):
    pr = np.abs(qa_cache[(i, k, a)].state(np.asarray(th))) ** 2
    return float(pr[cache[i][2]].sum())


out = []
for k, a in VARIANTS:
    tag = f"seed:{k}:{a}:0"
    trained = {r["i"]: {x["p"]: x for x in r["runs"]} for r in res if r["task"] == tag and r["feasible_instance"]}
    for p in (1, 2, 3, 4):
        th = {i: trained[i][p]["theta"] for i in ids}
        # cross-evaluation matrix M[donor, target]
        M = np.array([[popt(t, k, a, th[dn]) for t in ids] for dn in ids])
        for ti, t in enumerate(ids):
            others = [j for j in range(len(ids)) if j != ti]
            score = [np.mean([M[dn, x] for x in others if x != dn]) for dn in others]
            dn = others[int(np.argmax(score))]
            med = np.median(np.array([th[ids[j]] for j in others]), axis=0)
            qa = qa_cache[(t, k, a)]
            nf0 = qa.nfev
            r = minimize(qa.energy, np.asarray(th[ids[dn]]), method="COBYLA",
                         options={"maxiter": FT, "rhobeg": 0.1})
            out.append({"kind": k, "alpha": a, "p": p, "i": t,
                        "trained": trained[t][p]["popt"], "trained_nfev": trained[t][p]["nfev"],
                        "donor": float(M[dn, ti]), "donor_id": ids[dn],
                        "median": popt(t, k, a, med),
                        "ft": popt(t, k, a, r.x), "ft_nfev": qa.nfev - nf0})
        print(k, a, p, "trained %.3f donor %.3f median %.3f ft %.3f" % tuple(
            np.mean([o[f] for o in out if o["kind"] == k and o["alpha"] == a and o["p"] == p])
            for f in ("trained", "donor", "median", "ft")), flush=True)
(work / "p1_transfer.json").write_text(json.dumps({"ft_budget": FT, "rows": out}), encoding="utf-8")
