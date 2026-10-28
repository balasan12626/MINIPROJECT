"""P3 second revision -> <work>/p3_r2.json.

Re-runs the twin and city studies of exp_p3_v2.py with the same seeds and code path and, for every
fixed-budget draw, scores the integrations the reviewers asked for next to the naive one:
  top        - the most frequent sample, unverified (the paper's original baseline; must reproduce p3_v2.json)
  lowest_e   - the lowest-QUBO-energy sample, unverified (usual practice for annealers)
  pen_free   - the lowest-energy sample among those with zero penalty (one-hot, no forbidden pair, no penalised
               pair), i.e. filtering by the encoding's own constraints; None when no sample is penalty-free
and records the sampler's wall time per draw, so the loop can be compared with an exact-solver-first design
(MILP alone, always optimal when it finishes). Non-one-hot samples get infinite energy (they carry the
one-hot penalty P, which exceeds every cost difference).
City part, twice: the original annealer (40 sweeps, 64 chains, 10 draws) and a 10x longer one
(400 sweeps, 64 chains, 3 draws, 3 instances per city, size and demand), to see whether the city-scale failures come from a weak search.
usage: .venv\\Scripts\\python.exe exp_p3_r2.py <work> [twin|city|strong|all]
"""
import json
import sys
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np

import exp_p3_v2 as E

WORK = Path(sys.argv[1])
PART = sys.argv[2] if len(sys.argv) > 2 else "all"
_run_loop, _sa = E.run_loop, E.sa_sample
CAP, TIMES = [], []
STRONG = {"on": False, "cache": [], "n": 0}


def energy_parts(a, cost, forb, sizes, rem):
    """(shifted cost, number of penalty violations) of a one-hot plan; None plan -> (inf, inf)."""
    if a is None:
        return np.inf, np.inf
    big = np.where(forb, np.inf, cost)
    lo = np.where(np.isfinite(big.min(axis=1)), big.min(axis=1), 0.0)
    cs = np.where(forb, 0.0, cost - lo[:, None])
    pen = sum(bool(forb[g, s]) for g, s in enumerate(a))
    for s in set(a):
        gs = [g for g, t in enumerate(a) if t == s]
        pen += sum(1 for i, g in enumerate(gs) for h in gs[i + 1:]
                   if not forb[g, s] and not forb[h, s] and sizes[g] + sizes[h] > rem[s])
    return float(sum(cs[g, s] for g, s in enumerate(a))), pen


def run_loop(samples, cost, forb, sizes, rem, opt_obj, feasible_exists, adaptive):
    out = _run_loop(samples, cost, forb, sizes, rem, opt_obj, feasible_exists, adaptive)
    if not adaptive:
        cnt = {}
        for a in samples:
            cnt[a] = cnt.get(a, 0) + 1
        top = max(cnt, key=cnt.get)
        parts = {a: energy_parts(a, cost, forb, sizes, rem) for a in cnt}
        Pw = 1.0 + np.where(forb, 0.0, cost - np.where(np.isfinite(np.where(forb, np.inf, cost).min(axis=1)),
                                                         np.where(forb, np.inf, cost).min(axis=1), 0)[:, None]
                            ).max(axis=1).sum()
        en = {a: (c + Pw * p if np.isfinite(c) else np.inf) for a, (c, p) in parts.items()}
        low = min(en, key=en.get)
        free = [a for a in cnt if parts[a][1] == 0]
        pf = min(free, key=lambda a: parts[a][0]) if free else None
        ok = lambda a: E.verify(a, forb, sizes, rem)  # noqa: E731
        CAP.append({"raw_invalid": bool(out["raw_invalid"]), "top_unsafe": not ok(top),
                    "low_unsafe": not ok(low), "pf_none": pf is None, "pf_unsafe": (pf is not None and not ok(pf)),
                    "sampler_found": bool(out["sampler_found"]), "tool": out["tool"], "gap": out["gap_pct"],
                    "feasible": bool(feasible_exists)})
    return out


def sa_timed(lin, Qs, P, shots, rng, sweeps=60):
    if STRONG["on"]:
        sweeps = 400
        n = STRONG["n"]
        STRONG["n"] += 1
        if n >= E.DRAWS:  # the adaptive pass re-draws the same seeds: reuse the fixed-pass samples
            return STRONG["cache"][n - E.DRAWS]
    t0 = time.perf_counter()
    x = _sa(lin, Qs, P, shots, rng, sweeps=sweeps)
    TIMES.append((time.perf_counter() - t0) * 1000)
    if STRONG["on"]:
        STRONG["cache"].append(x)
    return x


def twin(i):
    E.run_loop, E.sa_sample = run_loop, sa_timed
    CAP.clear()
    TIMES.clear()
    rows = E.twin_job(i)
    per = 2 * E.DRAWS
    assert len(CAP) == per * len(rows)
    sa_ms = list(TIMES)  # fixed and adaptive draws do the same work
    return [{"seed": r["seed"], "event": r["event"], "feasible": r["feasible"], "milp_ms": r["milp_ms"],
             "qaoa_train_ms": r["qaoa_train_ms"], "qaoa": CAP[j * per:j * per + E.DRAWS],
             "sa": CAP[j * per + E.DRAWS:(j + 1) * per]} for j, r in enumerate(rows)] + \
        [{"_sa_ms": float(np.median(sa_ms)) if sa_ms else None}]


def city(args):
    strong = args[-1]
    E.run_loop, E.sa_sample = run_loop, sa_timed
    STRONG.update(on=strong, cache=[], n=0)
    E.DRAWS = 3 if strong else 10
    CAP.clear()
    TIMES.clear()
    r = E.city_job(args[:-1])
    return {"city": args[0], "G": args[1], "tight": args[2], "k": args[3], "strong": strong,
            "feasible": r["feasible"], "milp_ms": r["milp_ms"], "milp_status": r["milp_status"],
            "greedy_valid": r["greedy_valid"], "sa_ms": float(np.median(TIMES[:E.DRAWS])), "sa": list(CAP)}


if __name__ == "__main__":
    t0 = time.time()
    f = WORK / "p3_r2.json"
    out = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    with Pool(3) as pool:
        if PART in ("twin", "all"):
            tw = []
            for rows in pool.imap_unordered(twin, range(30)):
                tw += rows
                print(f"twin {len(tw)} {time.time() - t0:.0f}s", flush=True)
            out["twin"] = [r for r in tw if "_sa_ms" not in r]
            out["twin_sa_ms"] = [r["_sa_ms"] for r in tw if "_sa_ms" in r]
            f.write_text(json.dumps(out), encoding="utf-8")
        for key, strong in (("city", False), ("strong", True)):
            if PART not in (key, "all"):
                continue
            n_k = 3 if strong else 10  # the 10x annealer is a sensitivity check on 3 instances per cell
            jobs = [(c, G, t, k, strong) for c in E.CITIES for G in (8, 16, 32) for t in (0.6, 0.9) for k in range(n_k)]
            cc = []
            for r in pool.imap_unordered(city, jobs):
                cc.append(r)
                if len(cc) % 30 == 0:
                    print(f"{key} {len(cc)}/{len(jobs)} {time.time() - t0:.0f}s", flush=True)
            out[key] = cc
            f.write_text(json.dumps(out), encoding="utf-8")
    print("done", f"{time.time() - t0:.0f}s")
