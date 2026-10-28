"""Re-solve the city instances whose MILP hit the 60 s limit in exp_p3_v2.py -> <work>/p3_timeout.json.

HiGHS status 1 (time limit) proves nothing: exp_p3_v2.py stored those instances as feasible=False, but an
escalation on them is not certified. This script rebuilds exactly those instances (same seeds, same
code path) and gives the MILP a longer limit, so the paper can report what a longer limit settles.
usage: .venv\\Scripts\\python.exe exp_p3_timeout.py <work> [limit_s]
"""
import json
import sys
import time
from multiprocessing import Pool
from pathlib import Path

import exp_p3_v2 as E

WORK = Path(sys.argv[1])
LIMIT = float(sys.argv[2]) if len(sys.argv) > 2 else 1800.0
_milp = E.milp


def long_milp(*a, **kw):
    kw["options"] = {**kw.get("options", {}), "time_limit": LIMIT}
    return _milp(*a, **kw)


def job(args):
    E.milp = long_milp
    r = E.city_job(args)
    r.pop("draws")
    return r


if __name__ == "__main__":
    t0 = time.time()
    old = json.loads((WORK / "p3_v2.json").read_text(encoding="utf-8"))["city"]
    todo = [(r["city"], r["G"], r["tight"], r["k"]) for r in old if r["milp_status"] == 1]
    print("timed out at 60 s:", todo, flush=True)
    with Pool(min(3, len(todo))) as pool:
        rows = pool.map(job, todo)
    for r in rows:
        print(r["city"], r["G"], r["tight"], r["k"], "status", r["milp_status"], "feasible", r["feasible"],
              f"{r['milp_ms'] / 1000:.0f}s", flush=True)
    (WORK / "p3_timeout.json").write_text(json.dumps({"limit_s": LIMIT, "rows": rows}, default=float),
                                          encoding="utf-8")
    print("done", f"{time.time() - t0:.0f}s")
