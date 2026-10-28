"""P1 (quantum) experiments -> <work>/p1.json.

Instances: HqrlEngine(seed = 42 + 17 i), i = 0..29, after the benchmark disruption
(road R5 closed, Shelter A receives 50 % of its capacity), first G = 4 groups -> 12 qubits.
  main     - x vs xy mixer, mean vs CVaR(0.1) objective, p = 1..4      (Table II, Fig. 2)
  base     - exact enumeration, greedy, simulated annealing, uniform sampling (Table II)
  scaling  - G = 2..6 (6..18 qubits), p = 2, mean objective, 10 instances   (Table III)
usage: .venv\\Scripts\\python.exe exp_p1.py <work>
"""
import json
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
SHOTS = 32


def disrupted(seed: int) -> HqrlEngine:
    e = HqrlEngine(config=HqrlConfig(seed=seed))
    e._close_road("R5", "benchmark flood")
    s = e.shelters["SA"]
    s["occupancy"] = min(s["capacity"], s["occupancy"] + int(s["capacity"] * 0.5))
    s["remaining"] = s["capacity"] - s["occupancy"]
    return e


def at_least_one(p: float, n: int) -> float:
    return 1.0 - (1.0 - p) ** n


def run_main(n_inst=30, G=4):
    bits = Q.bit_table(G * 3)
    rows, base = [], []
    for i in range(n_inst):
        inst = Q.instance_from_engine(disrupted(42 + 17 * i), G)
        d = Q.diagonals(inst, bits)
        ex = Q.exact_solve(inst)
        if not np.isfinite(ex["obj"]):
            base.append({"i": i, "feasible_instance": False})
            continue
        opt = d["obj"] <= ex["obj"] + 1e-6
        naive = tuple(int(np.argmin(np.where(inst["forb"][g], np.inf, inst["cost"][g]))) for g in range(G))
        order = sorted(range(G), key=lambda g: -inst["sizes"][g])  # largest group first
        gr = Q.greedy(inst, order)
        gr_obj = None if gr is None else float(sum((inst["cost"] + inst["stab"])[g, s] for g, s in enumerate(gr)))
        rng = np.random.default_rng(1000 + i)
        sa = Q.simulated_annealing(inst, d, rng, restarts=1)
        sa_ok = bool(opt[sa["k"]])
        sa_feas = bool(d["feas"][sa["k"]])
        n_oh = 3 ** G
        k_qubo = int(np.argmin(d["h_qubo"]))
        base.append({
            "i": i, "feasible_instance": True,
            "capacity_binding": naive != ex["assign"],
            "n_feasible": int(d["feas"].sum()), "n_opt": int(opt.sum()),
            "exact_ms": ex["ms"],
            "greedy_feasible": gr is not None,
            "greedy_opt": gr is not None and abs(gr_obj - ex["obj"]) < 1e-6,
            "sa_opt": sa_ok, "sa_feas": sa_feas, "sa_ms": sa["ms"],
            "qubo_exact": bool(opt[k_qubo]),
            "uniform_bits_popt": float(opt.sum() / 2 ** (G * 3)),
            "uniform_onehot_popt": float(opt.sum() / n_oh),
        })
        for alpha in (1.0, 0.1):
            for kind in ("x", "xy"):
                qa = Q.Qaoa(inst, kind, d, alpha=alpha)
                r2 = np.random.default_rng(i)
                warm = None
                for p in (1, 2, 3, 4):
                    t0 = time.perf_counter()
                    nf0 = qa.nfev
                    th, _ = qa.optimise(p, r2, restarts=2, warm=warm)
                    ms = (time.perf_counter() - t0) * 1000
                    warm = th
                    pr = np.abs(qa.state(th)) ** 2
                    popt = float(pr[opt].sum())
                    rows.append({"i": i, "alpha": alpha, "kind": kind, "p": p,
                                 "popt": popt, "pfeas": float(pr[d["feas"]].sum()),
                                 "succ_shots": at_least_one(popt, SHOTS),
                                 "argmax_opt": bool(opt[int(np.argmax(pr))]),
                                 "nfev": qa.nfev - nf0, "ms": ms})
        print(f"instance {i}: feasible={int(d['feas'].sum())} binding={naive != ex['assign']}", flush=True)
    return rows, base


def run_scaling(n_inst=10, Gs=(2, 3, 4, 5, 6)):
    out = []
    for G in Gs:
        bits = Q.bit_table(G * 3)
        for i in range(n_inst):
            inst = Q.instance_from_engine(disrupted(42 + 17 * i), G)
            ex = Q.exact_solve(inst)
            if not np.isfinite(ex["obj"]):
                out.append({"G": G, "i": i, "feasible_instance": False})
                continue
            d = Q.diagonals(inst, bits)
            opt = d["obj"] <= ex["obj"] + 1e-6
            row = {"G": G, "i": i, "feasible_instance": True, "qubits": G * 3,
                   "n_opt": int(opt.sum()), "exact_ms": ex["ms"],
                   "qubo_exact": bool(opt[int(np.argmin(d["h_qubo"]))]),
                   "uniform_onehot_popt": float(opt.sum() / 3 ** G)}
            for kind in ("x", "xy"):
                qa = Q.Qaoa(inst, kind, d)
                t0 = time.perf_counter()
                th, _ = qa.optimise(1, np.random.default_rng(i), restarts=2)
                th, _ = qa.optimise(2, np.random.default_rng(i), restarts=1, warm=th)
                pr = np.abs(qa.state(th)) ** 2
                row[f"{kind}_popt"] = float(pr[opt].sum())
                row[f"{kind}_pfeas"] = float(pr[d["feas"]].sum())
                row[f"{kind}_ms"] = (time.perf_counter() - t0) * 1000
                row[f"{kind}_nfev"] = qa.nfev
            out.append(row)
            print(f"scaling G={G} i={i} xy_popt={row['xy_popt']:.3f}", flush=True)
        del bits
    return out


def summarise(rows, base, scaling):
    m = lambda xs: float(np.mean(xs)) if xs else float("nan")
    feas = [b for b in base if b["feasible_instance"]]
    s = {"n_instances": len(base), "n_feasible_instances": len(feas), "shots": SHOTS,
         "capacity_binding": sum(b["capacity_binding"] for b in feas),
         "mean_feasible_assignments": m([b["n_feasible"] for b in feas]),
         "greedy_feasible_pct": 100 * m([b["greedy_feasible"] for b in feas]),
         "greedy_opt_pct": 100 * m([b["greedy_opt"] for b in feas]),
         "sa_opt_pct": 100 * m([b["sa_opt"] for b in feas]),
         "sa_feas_pct": 100 * m([b["sa_feas"] for b in feas]),
         "sa_ms": m([b["sa_ms"] for b in feas]),
         "exact_ms": m([b["exact_ms"] for b in feas]),
         "qubo_exact_pct": 100 * m([b["qubo_exact"] for b in feas]),
         "uniform_bits_popt": m([b["uniform_bits_popt"] for b in feas]),
         "uniform_onehot_popt": m([b["uniform_onehot_popt"] for b in feas]),
         "qaoa": []}
    for alpha in (1.0, 0.1):
        for kind in ("x", "xy"):
            for p in (1, 2, 3, 4):
                rr = [r for r in rows if r["alpha"] == alpha and r["kind"] == kind and r["p"] == p]
                s["qaoa"].append({"alpha": alpha, "kind": kind, "p": p,
                                  "popt": m([r["popt"] for r in rr]), "popt_sd": float(np.std([r["popt"] for r in rr])),
                                  "pfeas": m([r["pfeas"] for r in rr]),
                                  "succ_shots_pct": 100 * m([r["succ_shots"] for r in rr]),
                                  "argmax_opt_pct": 100 * m([r["argmax_opt"] for r in rr]),
                                  "nfev": m([r["nfev"] for r in rr]), "ms": m([r["ms"] for r in rr])})
    s["scaling"] = []
    for G in sorted({r["G"] for r in scaling}):
        rr = [r for r in scaling if r["G"] == G and r["feasible_instance"]]
        s["scaling"].append({"G": G, "qubits": 3 * G, "n": len(rr),
                             "n_infeasible": sum(1 for r in scaling if r["G"] == G and not r["feasible_instance"]),
                             "uniform_onehot_popt": m([r["uniform_onehot_popt"] for r in rr]),
                             "x_popt": m([r["x_popt"] for r in rr]), "xy_popt": m([r["xy_popt"] for r in rr]),
                             "x_pfeas": m([r["x_pfeas"] for r in rr]), "xy_pfeas": m([r["xy_pfeas"] for r in rr]),
                             "x_ms": m([r["x_ms"] for r in rr]), "xy_ms": m([r["xy_ms"] for r in rr]),
                             "exact_ms": m([r["exact_ms"] for r in rr]),
                             "qubo_exact_pct": 100 * m([r["qubo_exact"] for r in rr])})
    return s


if __name__ == "__main__":
    rows, base = run_main()
    scaling = run_scaling()
    out = {"summary": summarise(rows, base, scaling), "rows": rows, "base": base, "scaling": scaling}
    (WORK / "p1.json").write_text(json.dumps(out, indent=1, default=float), encoding="utf-8")
    print(json.dumps(out["summary"], indent=1, default=float))
