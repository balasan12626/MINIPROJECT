"""P1 third revision -> <work>/p1_r3.json (phase "select") and <work>/p1_r3_dis.json (phase "dis").

select (cheap, no training):
  M1  oracle-free angle selection. The candidates are the trained angle sets of the 30 development instances
      (p1_v2.json, seed 0). Besides the P_opt rule of eq. (6), which needs the exact optimum of every
      development instance, one set per depth is chosen by the lowest mean scaled energy <E>/Delta and by the
      lowest mean CVaR_0.1 over the development instances; neither uses an optimum. Each choice is applied
      unchanged to the 30 held-out instances (i = 30..59), and a leave-one-out version is run on the
      development set. The per-instance best-of-5 baseline is re-chosen by the lowest training objective.
  M6  expected optimality gap of the cheapest verified-feasible plan among N samples, N in {8, 32, 128}.
  M4  simulated annealing with one-hot-preserving moves; uniform sampling over the feasible plans.
  M8  angle concentration (how many trained sets transfer well) and P_opt split by capacity-binding.
  cities/size: the newly chosen angles on the OpenStreetMap city instances (snapshot) - fixed angles only;
      the per-instance training numbers stay those of p1_cities.json.
dis (trains per instance):
  M2  held-out instances with other disruptions, built with the same twin generator: (a) two other roads
      closed, (b) Shelter B failed and one other road closed, (c) a different capacity cut (Shelter C
      receives 30 % or 70 % of its capacity) and one other road closed. 10 feasible instances per pattern
      from seeds 42 + 17 i, i >= 100. Fixed angles (each rule) against per-instance training (seed i).
usage: .venv\\Scripts\\python.exe exp_p1_r3.py <work> select|dis
"""
import json
import math
import sys
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
sys.path[:0] = [str(ROOT), str(HERE.parent), str(HERE)]
import qaoa_sim as Q  # noqa: E402
from exp_p1 import disrupted  # noqa: E402
from exp_p1_v2 import GroverQaoa, load, train  # noqa: E402

WORK = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
PHASE = sys.argv[2] if len(sys.argv) > 2 else "select"
DEPTHS = (1, 2, 3, 4)
NS = (8, 32, 128)
VARIANTS = (("xy", 1.0), ("xy", 0.1), ("x", 1.0), ("grover", 1.0), ("grover", 0.1))
RULES = ("popt", "energy", "cvar")


def make(inst, d, kind, alpha=1.0):
    return GroverQaoa(inst, d, alpha=alpha) if kind == "grover" else Q.Qaoa(inst, kind, d, alpha=alpha)


def metrics(qa, opt, th):
    """P_opt, mean scaled energy and CVaR_0.1 of one angle set on one instance."""
    pr = np.abs(qa.state(np.asarray(th))) ** 2
    e = float(pr @ qa.hn)
    ps = pr[qa.order]
    cum = np.cumsum(ps)
    w = np.clip(0.1 - (cum - ps), 0.0, ps)
    return float(pr[opt].sum()), e, float(w @ qa.hn_sorted) / 0.1, pr


def gap_stats(pr, d, opt_cost):
    """Exact expected relative gap of the cheapest feasible plan among N i.i.d. samples, P(no feasible plan)
    and P(optimum drawn). Gap is (c_best - c*) / c*; it is averaged over the event that a feasible plan is drawn."""
    f = np.where(d["feas"])[0]
    c = d["cost"][f]
    o = np.argsort(c, kind="stable")
    c, q = c[o], pr[f][o]
    out = {}
    for N in NS:
        tail = np.clip(1.0 - np.concatenate([[0.0], np.cumsum(q)]), 0.0, 1.0)  # P(sample not in first k)
        p_best = tail[:-1] ** N - tail[1:] ** N  # P(cheapest feasible drawn = plan k)
        pf = 1.0 - tail[-1] ** N
        gap = float(p_best @ ((c - opt_cost) / opt_cost)) / pf if pf > 0 else float("nan")
        out[N] = {"gap": gap, "p_feas": float(pf), "p_opt": float(p_best[c <= opt_cost + 1e-6].sum())}
    return out


def binding(inst, ex):
    naive = tuple(int(np.argmin(np.where(inst["forb"][g], np.inf, inst["cost"][g]))) for g in range(inst["G"]))
    return naive != tuple(ex["assign"])


def pool(ids):
    out = {}
    for i in ids:
        inst, d, ex = load(i)
        if np.isfinite(ex["obj"]):
            out[i] = (inst, d, d["obj"] <= ex["obj"] + 1e-6, ex)
    return out


def bitflip_sa_feasible(inst, d, rng, restarts=20, sweeps=200):
    """Bit-flip SA of the main study, also tracking the cheapest verified-feasible plan visited."""
    n = inst["G"] * inst["S"]
    h = d["h_qubo"]
    best_k, best_e, bf_k, bf_c = None, math.inf, None, math.inf
    scale = max(d["P"] - 1.0, 1e-9)
    t0 = time.perf_counter()
    for _ in range(restarts):
        k = int(rng.integers(0, 2 ** n))
        e = h[k]
        T = 2.0 * scale
        for _ in range(sweeps):
            for q in rng.permutation(n):
                k2 = k ^ (1 << int(q))
                de = h[k2] - e
                if de <= 0 or rng.random() < math.exp(-de / T):
                    k, e = k2, h[k2]
                    if d["feas"][k] and d["cost"][k] < bf_c:
                        bf_k, bf_c = k, d["cost"][k]
            T *= 0.9
        if e < best_e:
            best_k, best_e = k, e
    return {"k": best_k, "feas_k": bf_k, "ms": (time.perf_counter() - t0) * 1000}


def select_phase():
    t_start = time.time()
    v2 = json.loads((WORK / "p1_v2.json").read_text(encoding="utf-8"))["results"]
    r2 = json.loads((WORK / "p1_r2.json").read_text(encoding="utf-8"))
    ho = json.loads((WORK / "p1_holdout.json").read_text(encoding="utf-8"))
    dev, new = pool(range(30)), pool(range(30, 60))
    did, nid = sorted(dev), sorted(new)
    out = {"dev_ids": did, "new_ids": nid, "variants": {}, "fixed": {}}
    for kind, a in VARIANTS:
        task = f"grover:{a}" if kind == "grover" else f"seed:{kind}:{a}:0"
        tr = {r["i"]: {x["p"]: x for x in r["runs"]} for r in v2 if r["task"] == task and r["feasible_instance"]}
        qd = {i: make(dev[i][0], dev[i][1], kind, a) for i in did}
        qn = {i: make(new[i][0], new[i][1], kind, a) for i in nid}
        V = {}
        for p in DEPTHS:
            cands = [tr[i][p]["theta"] for i in did]
            # cross matrices [candidate, development instance]
            Mp = np.zeros((len(did), len(did)))
            Me, Mc = np.zeros_like(Mp), np.zeros_like(Mp)
            for ci, th in enumerate(cands):
                for ti, t in enumerate(did):
                    Mp[ci, ti], Me[ci, ti], Mc[ci, ti], _ = metrics(qd[t], dev[t][2], th)
            choice = {"popt": int(np.argmax(Mp.mean(1))), "energy": int(np.argmin(Me.mean(1))),
                      "cvar": int(np.argmin(Mc.mean(1)))}
            # leave-one-out on the development set: choose without the target, apply to it
            loo = {r: [] for r in RULES}
            for ti in range(len(did)):
                keep = [c for c in range(len(did)) if c != ti]
                cols = [c for c in range(len(did)) if c != ti]
                sub = lambda M: np.array([np.mean([M[c, x] for x in cols if x != c]) for c in keep])  # noqa: E731
                for r, M, f in (("popt", Mp, np.argmax), ("energy", Me, np.argmin), ("cvar", Mc, np.argmin)):
                    loo[r].append(float(Mp[keep[int(f(sub(M)))], ti]))
            rec = {"dev_trained": [tr[i][p]["popt"] for i in did],
                   "cand_dev_popt": Mp.mean(1).tolist(), "cand_dev_energy": Me.mean(1).tolist(),
                   "cand_dev_cvar": Mc.mean(1).tolist(), "loo": loo, "choice": {}, "new": {}}
            for r, ci in choice.items():
                th = cands[ci]
                rec["choice"][r] = {"from_instance": did[ci], "theta": th}
                vals = [metrics(qn[i], new[i][2], th) for i in nid]
                rec["new"][r] = {"popt": [v[0] for v in vals], "energy": [v[1] for v in vals],
                                 "cvar": [v[2] for v in vals]}
                out["fixed"][f"{kind}:{a}:{p}:{r}"] = th
                if p == 4 and kind in ("xy", "x") and a == 1.0 or (p == 4 and kind == "xy"):
                    rec["new"][r]["gaps"] = [gap_stats(v[3], new[i][1], new[i][3]["obj"]) for v, i in zip(vals, nid)]
            V[p] = rec
        out["variants"][f"{kind}:{a}"] = V
        print(kind, a, {r: round(float(np.mean(V[4]["new"][r]["popt"])), 3) for r in RULES},
              f"{time.time() - t_start:.0f}s", flush=True)
    # held-out per-instance training (p1_holdout.json) and binding flags
    out["new_trained"] = {f"{r['kind']}:{r['alpha']}:{r['p']}:{r['i']}": r["trained"] for r in ho["rows"]}
    out["new_binding"] = {str(i): binding(new[i][0], new[i][3]) for i in nid}
    out["dev_binding"] = {str(i): binding(dev[i][0], dev[i][3]) for i in did}
    # per-instance best-of-5 chosen by the training objective (lowest mean energy), development and held-out
    b5 = {"dev": [], "new": []}
    for i in did:
        runs = [{x["p"]: x for x in r["runs"]} for r in v2 if r["task"].startswith("seed:xy:1.0:") and r["i"] == i]
        qa = make(dev[i][0], dev[i][1], "xy", 1.0)
        m = [metrics(qa, dev[i][2], rr[4]["theta"]) for rr in runs]
        b5["dev"].append({"i": i, "popt": [x[0] for x in m], "energy": [x[1] for x in m],
                          "nfev": [sum(rr[q]["nfev"] for q in DEPTHS) for rr in runs]})
    for r in r2["rows"]:
        if r["task"] != "cobyla5":
            continue
        i = r["i"]
        qa = make(new[i][0], new[i][1], "xy", 1.0)
        m = [metrics(qa, new[i][2], rr[3]["theta"]) for rr in r["runs"]]
        b5["new"].append({"i": i, "popt": [x[0] for x in m], "energy": [x[1] for x in m],
                          "nfev": [sum(x["nfev"] for x in rr) for rr in r["runs"]],
                          "gaps_seed0": gap_stats(m[0][3], new[i][1], new[i][3]["obj"])})
    out["best5"] = b5
    # baselines on held-out instances: uniform one-hot and uniform over feasible plans (gaps and P_opt)
    base = []
    for i in nid:
        inst, d, opt, ex = new[i]
        oh = d["onehot"].astype(float)
        fe = d["feas"].astype(float)
        base.append({"i": i, "uni_onehot": gap_stats(oh / oh.sum(), d, ex["obj"]),
                     "uni_feas": gap_stats(fe / fe.sum(), d, ex["obj"]),
                     "uni_feas_popt": float(opt.sum() / fe.sum()), "uni_onehot_popt": float(opt.sum() / oh.sum())})
    out["new_baselines"] = base
    # M4 on the development set: one-hot-move SA, bit-flip SA with verifier, uniform over feasible plans
    sa = []
    for i in did:
        inst, d, opt, ex = dev[i]
        sd = Q.subspace_diag(inst)
        sopt = sd["obj"] <= ex["obj"] + 1e-6
        r1 = Q.sa_onehot(inst, sd, np.random.default_rng(5000 + i), restarts=20, sweeps=200)
        r0 = bitflip_sa_feasible(inst, d, np.random.default_rng(5000 + i))
        sa.append({"i": i, "oh_opt": bool(sopt[r1["k"]]), "oh_feas": bool(sd["feas"][r1["k"]]),
                   "oh_ver_opt": bool(r1["feas_k"] is not None and sopt[r1["feas_k"]]), "oh_ms": r1["ms"],
                   "bf_opt": bool(opt[r0["k"]]), "bf_feas": bool(d["feas"][r0["k"]]),
                   "bf_ver_opt": bool(r0["feas_k"] is not None and opt[r0["feas_k"]]), "bf_ms": r0["ms"],
                   "uni_feas_popt": float(opt.sum() / d["feas"].sum()), "n_feas": int(d["feas"].sum()),
                   "n_opt": int(opt.sum())})
    out["sa_dev"] = sa
    (WORK / "p1_r3.json").write_text(json.dumps(out), encoding="utf-8")
    print("select done", f"{time.time() - t_start:.0f}s", flush=True)
    cities_phase(out)


def cities_phase(sel):
    """Fixed angles of every rule on the city instances (snapshot), XY and X, p = 4."""
    import exp_p1_cities as C
    cj = json.loads((WORK / "p1_cities.json").read_text(encoding="utf-8"))
    bits = Q.bit_table(12)
    graphs = {}
    rows = []
    for r in cj["rows"]:
        if not r["feasible_instance"]:
            continue
        city = r["city"]
        if city not in graphs:
            c = json.loads((C.CITY_DIR / f"{city}.json").read_text(encoding="utf-8"))
            graphs[city] = (c, C.city_graph(c))
        c, g = graphs[city]
        inst = C.build(c, g, r["seed"])
        ex = Q.exact_solve(inst)
        d = Q.diagonals(inst, bits)
        opt = d["obj"] <= ex["obj"] + 1e-6
        assert abs(opt.sum() / 81 - r["uniform"]) < 1e-12, "city instance rebuilt identically"
        row = {"city": city, "seed": r["seed"], "binding": r["binding"]}
        for kind, a in (("xy", 1.0), ("xy", 0.1), ("x", 1.0)):
            qa = Q.Qaoa(inst, kind, d, alpha=a)
            for rule in RULES:
                pr = np.abs(qa.state(np.asarray(sel["fixed"][f"{kind}:{a}:4:{rule}"]))) ** 2
                row[f"{kind}:{a}:{rule}"] = float(pr[opt].sum())
                if kind == "xy" and a == 1.0:
                    row[f"gaps:{rule}"] = gap_stats(pr, d, ex["obj"])
            row[f"{kind}:{a}:trained"] = r[f"{kind}:{a}:4"]["trained"]
        assert abs(row["xy:1.0:popt"] - r["xy:1.0:4"]["fixed"]) < 1e-9, "P_opt rule reproduces p1_cities.json"
        rows.append(row)
    (WORK / "p1_r3_cities.json").write_text(json.dumps({"rows": rows}), encoding="utf-8")
    print("cities done", len(rows), flush=True)


# ----------------------------------------------------------------------------- M2: other disruptions
PATTERNS = ("roads", "shelter", "capacity")


def disrupted_var(seed, pattern):
    from backend.simulation.hqrl_demo import HqrlConfig, HqrlEngine
    e = HqrlEngine(config=HqrlConfig(seed=seed))
    rng = np.random.default_rng(seed)
    closable = [r for r in e.roads if r not in ("R1", "R2", "R3", "R5")]
    if pattern == "roads":
        for rid in rng.choice(closable, 2, replace=False):
            e._close_road(str(rid), "varied disruption")
        desc = "two roads closed"
    elif pattern == "shelter":
        e._close_road(str(rng.choice(closable)), "varied disruption")
        e.shelters["SB"]["status"] = "FAILED"
        e.shelters["SB"]["remaining"] = 0
        desc = "Shelter B failed, one road closed"
    else:
        e._close_road(str(rng.choice(closable)), "varied disruption")
        frac = float(rng.choice([0.3, 0.7]))
        s = e.shelters["SC"]
        s["occupancy"] = min(s["capacity"], s["occupancy"] + int(s["capacity"] * frac))
        s["remaining"] = s["capacity"] - s["occupancy"]
        desc = f"Shelter C +{int(frac * 100)}%, one road closed"
    return e, desc


def dis_job(args):
    pattern, i = args
    eng, desc = disrupted_var(42 + 17 * i, pattern)
    inst = Q.instance_from_engine(eng, 4)
    ex = Q.exact_solve(inst)
    if not np.isfinite(ex["obj"]):
        return {"pattern": pattern, "i": i, "feasible_instance": False}
    d = Q.diagonals(inst, Q.bit_table(12))
    opt = d["obj"] <= ex["obj"] + 1e-6
    sel = json.loads((WORK / "p1_r3.json").read_text(encoding="utf-8"))["fixed"]
    row = {"pattern": pattern, "i": i, "feasible_instance": True, "desc": desc, "binding": binding(inst, ex),
           "uniform": float(opt.sum() / 81), "n_feas": int(d["feas"].sum())}
    for kind, a in (("xy", 1.0), ("xy", 0.1)):
        tr = train(Q.Qaoa(inst, kind, d, alpha=a), opt, d["feas"], i)
        qa = Q.Qaoa(inst, kind, d, alpha=a)
        for rule in RULES:
            pr = np.abs(qa.state(np.asarray(sel[f"{kind}:{a}:4:{rule}"]))) ** 2
            row[f"{kind}:{a}:{rule}"] = float(pr[opt].sum())
        row[f"{kind}:{a}:trained"] = tr[3]["popt"]
        row[f"{kind}:{a}:nfev"] = sum(x["nfev"] for x in tr)
    return row


def dis_phase():
    t0 = time.time()
    jobs = [(pat, i) for pat in PATTERNS for i in range(100, 130)]
    rows = []
    with Pool(4) as pl:
        for r in pl.imap(dis_job, jobs):
            rows.append(r)
            if r["feasible_instance"]:
                print(r["pattern"], r["i"], r["desc"], round(r["xy:1.0:energy"], 3), round(r["xy:1.0:trained"], 3),
                      f"{time.time() - t0:.0f}s", flush=True)
    # keep the first 10 feasible instances of each pattern (seed order)
    keep = []
    for pat in PATTERNS:
        keep += [r for r in rows if r["pattern"] == pat and r["feasible_instance"]][:10]
    (WORK / "p1_r3_dis.json").write_text(json.dumps({"rows": keep, "all": [
        {"pattern": r["pattern"], "i": r["i"], "feasible_instance": r["feasible_instance"]} for r in rows]}),
        encoding="utf-8")
    print("dis done", f"{time.time() - t0:.0f}s")


def cand_phase():
    """Angle concentration: held-out mean P_opt of every one of the 30 trained XY/mean angle sets (p = 4)."""
    v2 = json.loads((WORK / "p1_v2.json").read_text(encoding="utf-8"))["results"]
    tr = {r["i"]: {x["p"]: x for x in r["runs"]} for r in v2 if r["task"] == "seed:xy:1.0:0" and r["feasible_instance"]}
    new = pool(range(30, 60))
    qn = {i: make(new[i][0], new[i][1], "xy", 1.0) for i in new}
    H = [float(np.mean([metrics(qn[j], new[j][2], tr[i][4]["theta"])[0] for j in sorted(new)])) for i in sorted(tr)]
    (WORK / "p1_r3_cand.json").write_text(json.dumps({"dev_ids": sorted(tr), "cand_heldout_popt": H}), encoding="utf-8")
    print("cand done")


if __name__ == "__main__":
    if PHASE == "cand":
        cand_phase()
    elif PHASE == "select":
        select_phase()
    elif PHASE == "cities":
        cities_phase(json.loads((WORK / "p1_r3.json").read_text(encoding="utf-8")))
    else:
        dis_phase()
