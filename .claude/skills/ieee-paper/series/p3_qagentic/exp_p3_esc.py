"""P3 escalation experiment -> <work>/p3_esc.json.

Extends each of the 30 episodes with a sixth event, E5: Shelter B also fails, leaving one
shelter. Many episodes then have no feasible plan, which exercises the escalation branch.
Verified policy with angle memory (mu = 0); raw = most frequent QAOA sample, unverified.
usage: .venv\\Scripts\\python.exe exp_p3_esc.py <work>
"""
import json
import random
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[4]), str(HERE.parent), str(HERE)]
from backend.simulation.hqrl_demo import HqrlConfig, HqrlEngine  # noqa: E402
import qaoa_sim as Q  # noqa: E402
from exp_p3 import BITS, G, N_SEEDS, QaoaTool, apply_event, valid  # noqa: E402

WORK = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
rows = []
for i in range(N_SEEDS):
    seed = 42 + 17 * i
    e = HqrlEngine(config=HqrlConfig(seed=seed))
    r = random.Random(seed)
    tool = QaoaTool(True, seed)
    for k in range(6):
        if k < 5:
            apply_event(e, k, r)
        else:
            e.shelters["SB"]["status"] = "FAILED"
            e.shelters["SB"]["remaining"] = 0
        inst = Q.instance_from_engine(e, G)
        d = Q.diagonals(inst, BITS)
        ex = Q.exact_solve(inst)
        feasible = bool(np.isfinite(ex["obj"]))
        q = tool(inst, d)
        a = q["best"]
        how = "qaoa"
        if not valid(inst, a):
            a, how = Q.greedy(inst, sorted(range(G), key=lambda g: -inst["sizes"][g])), "greedy"
        if not valid(inst, a):
            a, how = ex["assign"], "exact"
        escalated = not valid(inst, a)
        rows.append({"seed": seed, "event": k, "feasible": feasible, "escalated": escalated, "how": how,
                     "raw_invalid": not valid(inst, q["top"])})
    print(f"seed {seed} done", flush=True)

e5 = [x for x in rows if x["event"] == 5]
out = {
    "n_episodes": N_SEEDS,
    "e5_infeasible": sum(not x["feasible"] for x in e5),
    "e5_escalated": sum(x["escalated"] for x in e5),
    "correct_escalations": sum(x["escalated"] and not x["feasible"] for x in rows),
    "wrong_escalations": sum(x["escalated"] and x["feasible"] for x in rows),
    "missed_escalations": sum((not x["escalated"]) and (not x["feasible"]) for x in rows),
    "raw_invalid_at_infeasible": sum(x["raw_invalid"] for x in e5 if not x["feasible"]),
    "rows": rows,
}
(WORK / "p3_esc.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
print({k: v for k, v in out.items() if k != "rows"})
