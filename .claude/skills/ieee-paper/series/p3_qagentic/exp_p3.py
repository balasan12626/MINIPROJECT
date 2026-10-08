"""P3 (agentic + quantum) experiments -> <work>/p3.json.

An agent loop re-plans shelter assignment over a five-event disruption episode on the HQRL twin:
  E0 initial state | E1 road R5 closes | E2 Shelter A gets 50 % of capacity as arrivals
  E3 one more random road closes       | E4 Shelter A fails
Monitor agent detects the change, Planner builds the QUBO instance (with stability term mu),
Solver agent calls tools, Verifier re-checks the plan against the current state, and the loop
escalates to a human when no feasible plan exists.
Policies compared on the same episodes (30 seeds, G = 4 groups, 12 qubits):
  raw        - most frequent QAOA sample, dispatched without verification
  verified   - best feasible of S QAOA shots -> greedy -> exact -> escalate
  portfolio  - verified QAOA and greedy both run, cheaper valid plan kept
  classical  - greedy -> exact -> escalate (no QAOA)
  oracle     - exact enumeration
QAOA: ring-XY mixer, p = 3, exact statevector. Angle memory (warm start from the previous
event) is compared with cold starts.
usage: .venv\\Scripts\\python.exe exp_p3.py <work>
"""
import json
import random
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
sys.path[:0] = [str(ROOT), str(HERE.parent)]
from backend.simulation.hqrl_demo import HqrlConfig, HqrlEngine  # noqa: E402
import qaoa_sim as Q  # noqa: E402

WORK = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
WORK.mkdir(parents=True, exist_ok=True)
G, S, P_LAYERS, SHOTS, N_SEEDS = 4, 3, 3, 64, 30
EVENTS = ["E0 initial", "E1 road R5 closed", "E2 Shelter A surge", "E3 extra closure", "E4 Shelter A failed"]
BITS = Q.bit_table(G * S)


def apply_event(e: HqrlEngine, k: int, r: random.Random):
    if k == 1:
        e._close_road("R5", "flood")
    elif k == 2:
        s = e.shelters["SA"]
        s["occupancy"] = min(s["capacity"], s["occupancy"] + int(s["capacity"] * 0.5))
        s["remaining"] = s["capacity"] - s["occupancy"]
    elif k == 3:
        opts = sorted(rid for rid, x in e.roads.items() if not x["closed"] and rid not in ("R1", "R2", "R3"))
        e._close_road(r.choice(opts), "extra closure")
    elif k == 4:
        e.shelters["SA"]["status"] = "FAILED"
        e.shelters["SA"]["remaining"] = 0


def state_key(e: HqrlEngine):
    return (e.graph_version, tuple((s, x["status"], x["remaining"]) for s, x in sorted(e.shelters.items())))


def valid(inst, a) -> bool:
    if a is None:
        return False
    load = np.zeros(S)
    for g, s in enumerate(a):
        if inst["forb"][g, s]:
            return False
        load[s] += inst["sizes"][g]
    return bool((load <= inst["rem"]).all())


def travel(inst, a):
    return float(sum(inst["cost"][g, s] for g, s in enumerate(a)))


def objective(inst, a):
    return float(sum((inst["cost"] + inst["stab"])[g, s] for g, s in enumerate(a)))


def churn(prev, a):
    if prev is None or a is None:
        return 0
    return sum(1 for g, s in enumerate(a) if prev.get(g) is not None and prev[g] != s)


class QaoaTool:
    """QAOA as a tool with optional angle memory across events."""

    def __init__(self, memory: bool, seed: int):
        self.memory, self.theta, self.rng = memory, None, np.random.default_rng(seed)

    def __call__(self, inst, d):
        t0 = time.perf_counter()
        qa = Q.Qaoa(inst, "xy", d)
        if self.memory and self.theta is not None:
            th, _ = qa.optimise(P_LAYERS, self.rng, restarts=0, warm=self.theta)
        else:
            th = None
            for p in range(1, P_LAYERS + 1):
                th, _ = qa.optimise(p, self.rng, restarts=2, warm=th)
        self.theta = th
        pr = np.abs(qa.state(th)) ** 2
        shots = Q.sample(pr, SHOTS, self.rng)
        ks, counts = np.unique(shots, return_counts=True)
        top = int(ks[np.argmax(counts)])
        feas = [int(k) for k in ks if d["feas"][k]]
        best = min(feas, key=lambda k: d["obj"][k]) if feas else None
        return {"top": Q.index_to_assign(top, G, S), "best": None if best is None else Q.index_to_assign(best, G, S),
                "nfev": qa.nfev, "ms": (time.perf_counter() - t0) * 1000}


def run(mu: float, memory: bool):
    log = []
    for i in range(N_SEEDS):
        seed = 42 + 17 * i
        e = HqrlEngine(config=HqrlConfig(seed=seed))
        r = random.Random(seed)
        tool = QaoaTool(memory, seed)
        plans = {k: None for k in ("raw", "verified", "portfolio", "classical", "oracle")}
        last_key = None
        for k in range(len(EVENTS)):
            apply_event(e, k, r)
            key = state_key(e)
            if key == last_key:  # Monitor agent: nothing changed, no re-plan
                log.append({"seed": seed, "event": k, "replanned": False})
                continue
            last_key = key
            row = {"seed": seed, "event": k, "replanned": True}
            # one QAOA call per event, on the instance of the verified policy (its plan in force
            # sets the stability term); raw and portfolio are scored on the same draw
            pv = None if plans["verified"] is None else {g: s for g, s in enumerate(plans["verified"])}
            inst_q = Q.instance_from_engine(e, G, prev=pv, mu=mu)
            d_q = Q.diagonals(inst_q, BITS)
            q = tool(inst_q, d_q)
            for pol in plans:
                prev = None if plans[pol] is None else {g: s for g, s in enumerate(plans[pol])}
                inst = inst_q if pol in ("raw", "verified", "portfolio") else Q.instance_from_engine(e, G, prev=prev, mu=mu)
                t0 = time.perf_counter()
                ex = Q.exact_solve(inst)
                feasible_exists = np.isfinite(ex["obj"])
                order = sorted(range(G), key=lambda g: -inst["sizes"][g])
                a, how, nfev = None, None, 0
                if pol == "oracle":
                    a, how = ex["assign"], "exact"
                elif pol == "classical":
                    a, how = Q.greedy(inst, order), "greedy"
                    if not valid(inst, a):
                        a, how = ex["assign"], "exact"
                else:
                    nfev = q["nfev"]
                    if pol == "raw":
                        a, how = q["top"], "qaoa-top"
                    else:
                        a, how = q["best"], "qaoa"
                        if pol == "portfolio":
                            gr = Q.greedy(inst, order)
                            if valid(inst, gr) and (a is None or objective(inst, gr) < objective(inst, a) - 1e-9):
                                a, how = gr, "greedy"
                        if not valid(inst, a):
                            a, how = Q.greedy(inst, order), "greedy-fallback"
                        if not valid(inst, a):
                            a, how = ex["assign"], "exact-fallback"
                ms = (time.perf_counter() - t0) * 1000 + (q["ms"] if pol in ("raw", "verified", "portfolio") else 0.0)
                ok = valid(inst, a)
                escalate = (not ok) and pol != "raw"
                dispatched = a if (ok or pol == "raw") else None
                row[pol] = {
                    "how": how if ok or pol == "raw" else "escalate",
                    "valid": ok, "dispatched_invalid": pol == "raw" and a is not None and not ok,
                    "no_plan": a is None, "escalate": escalate, "feasible_exists": bool(feasible_exists),
                    "travel": travel(inst, a) if ok else None,
                    "opt_travel": travel(inst, ex["assign"]) if feasible_exists else None,
                    "gap_obj": (objective(inst, a) - ex["obj"]) if ok and feasible_exists else None,
                    "churn": churn(prev, a) if ok and prev else 0, "nfev": nfev, "ms": ms,
                }
                if dispatched is not None and ok:
                    plans[pol] = tuple(dispatched)
            log.append(row)
        print(f"mu={mu} memory={memory} seed={seed} done", flush=True)
    return log


def summarise(log):
    pols = ("raw", "verified", "portfolio", "classical", "oracle")
    rows = [r for r in log if r.get("replanned")]
    out = {"n_events": len(log), "n_replans": len(rows),
           "no_change_events": sum(1 for r in log if not r.get("replanned"))}
    for p in pols:
        rr = [r[p] for r in rows]
        fe = [x for x in rr if x["feasible_exists"]]
        gaps = [x["gap_obj"] for x in fe if x["gap_obj"] is not None]
        opt_hits = [abs(x["gap_obj"]) < 1e-6 for x in fe if x["gap_obj"] is not None]
        rep = [r[p] for r in rows if r["event"] > 0]
        out[p] = {
            "dispatched_invalid_pct": 100 * np.mean([x["dispatched_invalid"] for x in rr]),
            "valid_when_feasible_pct": 100 * np.mean([x["valid"] for x in fe]) if fe else None,
            "escalations": int(sum(x["escalate"] for x in rr)),
            "correct_escalations": int(sum(x["escalate"] and not x["feasible_exists"] for x in rr)),
            "opt_pct": 100 * float(np.mean(opt_hits)) if opt_hits else None,
            "mean_gap_min": float(np.mean(gaps)) if gaps else None,
            "mean_churn": float(np.mean([x["churn"] for x in rep])) if rep else None,
            "mean_travel": float(np.mean([x["travel"] for x in rr if x["travel"] is not None])),
            "mean_ms": float(np.mean([x["ms"] for x in rr])),
            "mean_nfev": float(np.mean([x["nfev"] for x in rr])),
            "fallback_pct": 100 * float(np.mean([x["how"] in ("greedy-fallback", "exact-fallback") for x in rr])),
            "greedy_won_pct": 100 * float(np.mean([x["how"] == "greedy" for x in rr])),
        }
    out["infeasible_events"] = int(sum(1 for r in rows if not r["oracle"]["feasible_exists"]))
    out["by_event"] = {EVENTS[k]: {"replans": sum(1 for r in rows if r["event"] == k),
                                   "infeasible": sum(1 for r in rows if r["event"] == k and not r["oracle"]["feasible_exists"]),
                                   "raw_invalid": sum(1 for r in rows if r["event"] == k and r["raw"]["dispatched_invalid"])}
                       for k in range(len(EVENTS))}
    return out


if __name__ == "__main__":
    res = {}
    for mu, memory in ((0.0, False), (0.0, True), (3.0, True), (6.0, True)):
        log = run(mu, memory)
        res[f"mu{mu:g}_{'warm' if memory else 'cold'}"] = {"summary": summarise(log), "log": log}
    out = {"config": {"G": G, "S": S, "p": P_LAYERS, "shots": SHOTS, "seeds": N_SEEDS, "events": EVENTS},
           "runs": res}
    (WORK / "p3.json").write_text(json.dumps(out, indent=1, default=float), encoding="utf-8")
    for k, v in res.items():
        print(k, json.dumps({p: v["summary"][p] for p in ("raw", "verified", "portfolio", "classical", "oracle")}, default=float))
