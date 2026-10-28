"""P3 city study, re-run in one piece on a frozen snapshot of the city data -> <work>/p3_city2.json.

The city JSONs in backend/data/cities were rebuilt after the first city run (exp_p3_v2.py, 2026-10-10), so that
run can no longer be reproduced from the repository. This script repeats everything the paper reports at city
scale on the snapshot in series/city_snapshot_2026-10-13 (SHA-256 sums stored next to it and in the output):
  city     - the exp_p3_v2.py city rows (same seeds, same code path), and per fixed-budget draw the integrations of
             exp_p3_r2.py (most frequent / lowest-energy / penalty-free sample) and the violation class of
             exp_p3_viol.py
  timeout  - instances whose MILP hit the 60 s limit, re-solved with a 1800 s limit (as exp_p3_timeout.py)
  reach    - zone-to-shelter reachability after the closures (as exp_p3_reach.py)
  strong   - the 400-sweep annealer on 3 instances per city, size and demand (as exp_p3_r2.py strong)
usage: .venv\\Scripts\\python.exe exp_p3_city2.py <work>
"""
import hashlib
import json
import sys
import time
from multiprocessing import Pool
from pathlib import Path

import networkx as nx
import numpy as np

import exp_p3_r2 as R
import exp_p3_v2 as E
from exp_p3_viol import classify

HERE = Path(__file__).resolve().parent
SNAP = HERE.parent / "city_snapshot_2026-10-13"
WORK = Path(sys.argv[1])
LONG = 1800.0
_milp = E.milp


def setup(strong=False, long_limit=False):
    E.ROOT = SNAP  # city_job reads ROOT / backend / data / cities
    E.run_loop, E.sa_sample = run_loop, R.sa_timed
    R.STRONG.update(on=strong, cache=[], n=0)
    E.DRAWS = 3 if strong else 10
    if long_limit:
        E.milp = lambda *a, **kw: _milp(*a, **{**kw, "options": {**kw.get("options", {}), "time_limit": LONG}})
    else:
        E.milp = _milp


def run_loop(samples, cost, forb, sizes, rem, opt_obj, feasible_exists, adaptive):
    n0 = len(R.CAP)
    out = R.run_loop(samples, cost, forb, sizes, rem, opt_obj, feasible_exists, adaptive)
    if not adaptive:
        cnt = {}
        for a in samples:
            cnt[a] = cnt.get(a, 0) + 1
        top = max(cnt, key=cnt.get)
        R.CAP[n0]["cls"] = classify(top, forb, sizes, rem)
    return out


def city(args):
    setup()
    R.CAP.clear()
    R.TIMES.clear()
    r = E.city_job(args)
    r["cap"] = list(R.CAP)
    r["sa_call_ms"] = float(np.median(R.TIMES[:E.DRAWS]))
    return r


def strong(args):
    setup(strong=True)
    R.CAP.clear()
    R.TIMES.clear()
    r = E.city_job(args)
    return {"city": args[0], "G": args[1], "tight": args[2], "k": args[3], "feasible": r["feasible"],
            "milp_status": r["milp_status"], "milp_ms": r["milp_ms"], "sa_ms": float(np.median(R.TIMES[:E.DRAWS])),
            "sa": list(R.CAP)}


def resolve(args):
    setup(long_limit=True)
    r = E.city_job(args)
    r.pop("draws")
    return r


def reach():
    E.ROOT = SNAP
    out = {}
    for c_ in E.CITIES:
        c = json.loads((SNAP / "backend" / "data" / "cities" / f"{c_}.json").read_text(encoding="utf-8"))
        g = E.city_graph(c)
        nodes = list(g.nodes)
        zn = [E.nearest(c, z["lat"], z["lon"], nodes) for z in c["zones"]]
        sn = [E.nearest(c, s["lat"], s["lon"], nodes) for s in c["shelters"]]
        closed = sorted({d["rid"] for _, _, d in g.edges(data=True)}, key=lambda rid: -max(
            d["flood"] for _, _, d in g.edges(data=True) if d["rid"] == rid))[:3]
        h = g.copy()
        h.remove_edges_from([(u, v) for u, v, d in g.edges(data=True) if d["rid"] in closed])
        rc = np.array([[nx.has_path(h, z, s) for s in sn] for z in zn])
        out[c_] = {"zones": len(zn), "shelters": len(sn), "pairs_open": float(rc.mean()),
                   "zones_cut_off": int((~rc.any(1)).sum())}
    return out


if __name__ == "__main__":
    t0 = time.time()
    f = WORK / "p3_city2.json"
    out = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    out["snapshot_sha256"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in sorted((SNAP / "backend" / "data" / "cities").glob("*.json"))}
    out["reach"] = reach()
    jobs = [(c, G, t, k) for c in E.CITIES for G in (8, 16, 32) for t in (0.6, 0.9) for k in range(10)]
    with Pool(3) as pool:
        if "city" not in out:
            rows = []
            for r in pool.imap_unordered(city, jobs):
                rows.append(r)
                if len(rows) % 30 == 0:
                    print(f"city {len(rows)}/{len(jobs)} {time.time() - t0:.0f}s", flush=True)
            out["city"] = rows
            f.write_text(json.dumps(out, default=float), encoding="utf-8")
        todo = [(r["city"], r["G"], r["tight"], r["k"]) for r in out["city"] if r["milp_status"] == 1]
        print("timed out at 60 s:", todo, flush=True)
        if todo and "timeout" not in out:
            out["timeout"] = {"limit_s": LONG, "rows": pool.map(resolve, todo)}
            f.write_text(json.dumps(out, default=float), encoding="utf-8")
        if "strong" not in out:
            sj = [(c, G, t, k) for c in E.CITIES for G in (8, 16, 32) for t in (0.6, 0.9) for k in range(3)]
            st = []
            for r in pool.imap_unordered(strong, sj):
                st.append(r)
                if len(st) % 18 == 0:
                    print(f"strong {len(st)}/{len(sj)} {time.time() - t0:.0f}s", flush=True)
            out["strong"] = st
            f.write_text(json.dumps(out, default=float), encoding="utf-8")
    print("done", f"{time.time() - t0:.0f}s")
