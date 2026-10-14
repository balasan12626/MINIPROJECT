"""P3 revision: runtime assurance for sampling-based optimisers in flood re-planning -> <work>/p3_v2.json.

Two studies, both on the same loop: sampler -> exact verifier -> greedy fallback -> escalation, where
escalation is either (a) uncertified ("no tool found a valid plan") or (b) certified by an exact MILP
feasibility/optimality check (HiGHS through scipy.optimize.milp).

A  twin episodes (G = 4, S = 3, 12 binary variables): 30 seeds x 6 events (E0..E4 as in exp_p3.py plus
   E5: Shelter B also fails). Samplers: QAOA (ring-XY, p = 3, depth-progressive training per event) and
   simulated annealing on the same QUBO. 10 independent sample draws per event (shot noise), fixed budget
   of 64 shots and an adaptive budget (batches of 8 until a verified plan appears or 64 shots are used).
B  city scale on OpenStreetMap road graphs (six cities): G in {8, 16, 32} groups, S = 10 shelters
   (24..320 variables), 10 instances per (city, G) and two tightness levels. Sampler: vectorised
   simulated annealing on the pairwise-capacity QUBO (64 chains). Enumeration is impossible here
   (10^8..10^32 plans), so the MILP is the only exact reference.
usage: .venv\\Scripts\\python.exe exp_p3_v2.py <work>
"""
import json
import random
import zlib
import sys
import time
from multiprocessing import Pool
from pathlib import Path

import networkx as nx
import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
sys.path[:0] = [str(ROOT), str(HERE.parent), str(HERE), str(HERE.parent / "p1_quantum")]
from backend.simulation.hqrl_demo import HqrlConfig, HqrlEngine  # noqa: E402
import qaoa_sim as Q  # noqa: E402
from exp_p3 import apply_event, state_key  # noqa: E402

WORK = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
SHOTS, BATCH, DRAWS, P_LAYERS = 64, 8, 10, 3


# ----------------------------------------------------------------------------- exact tools
def milp_solve(cost, forb, sizes, rem):
    """Exact assignment by MILP. Returns (assignment or None, objective, ms, status)."""
    G, S = cost.shape
    n = G * S
    c = np.where(forb, 0.0, cost).ravel()
    A_one = np.zeros((G, n))
    for g in range(G):
        A_one[g, g * S:(g + 1) * S] = 1
    A_cap = np.zeros((S, n))
    for g in range(G):
        for s in range(S):
            A_cap[s, g * S + s] = sizes[g]
    ub = np.where(forb.ravel(), 0.0, 1.0)
    t0 = time.perf_counter()
    r = milp(c, constraints=[LinearConstraint(A_one, 1, 1), LinearConstraint(A_cap, -np.inf, rem)],
             integrality=np.ones(n), bounds=Bounds(np.zeros(n), ub), options={"time_limit": 60})
    ms = (time.perf_counter() - t0) * 1000
    if r.status != 0 or r.x is None:
        return None, np.inf, ms, int(r.status)
    x = np.round(r.x).reshape(G, S)
    return tuple(int(np.argmax(x[g])) for g in range(G)), float(r.fun), ms, 0


def verify(a, forb, sizes, rem):
    if a is None:
        return False
    load = np.zeros(len(rem))
    for g, s in enumerate(a):
        if forb[g, s]:
            return False
        load[s] += sizes[g]
    return bool((load <= np.asarray(rem) + 1e-9).all())


def greedy(cost, forb, sizes, rem):
    left = np.asarray(rem, dtype=float).copy()
    a = [None] * len(sizes)
    for g in sorted(range(len(sizes)), key=lambda g: -sizes[g]):
        opts = [s for s in range(cost.shape[1]) if not forb[g, s] and sizes[g] <= left[s]]
        if not opts:
            return None
        s = min(opts, key=lambda s: cost[g, s])
        a[g] = s
        left[s] -= sizes[g]
    return tuple(a)


# ----------------------------------------------------------------------------- QUBO + vectorised SA sampler
def qubo(cost, forb, sizes, rem):
    """Same energy as qaoa_sim.diagonals: shifted cost + P (one-hot + forbidden + pairwise capacity)."""
    G, S = cost.shape
    n = G * S
    big = np.where(forb, np.inf, cost)
    lo = np.where(np.isfinite(big.min(axis=1)), big.min(axis=1), 0.0)
    cs = np.where(forb, 0.0, cost - lo[:, None])
    P = 1.0 + cs.max(axis=1).sum()
    Qm = np.zeros((n, n))
    lin = cs.ravel().copy()
    for g in range(G):  # P (1 - sum_s x)^2 = P (1 - sum x + 2 sum_{s<t} x_s x_t)
        for s in range(S):
            lin[g * S + s] -= P
            for t in range(s + 1, S):
                Qm[g * S + s, g * S + t] += P
    lin += P * forb.ravel()
    for s in range(S):
        for g in range(G):
            for h in range(g + 1, G):
                if not forb[g, s] and not forb[h, s] and sizes[g] + sizes[h] > rem[s]:
                    Qm[g * S + s, h * S + s] += P
    Qs = Qm + Qm.T
    return lin, Qs, P


def sa_sample(lin, Qs, P, shots, rng, sweeps=60):
    """`shots` independent annealing chains run in parallel; returns final bit vectors."""
    n = len(lin)
    x = rng.integers(0, 2, size=(shots, n)).astype(np.float64)
    h = x @ Qs  # local field
    T0 = max(P, 1.0)
    for sw in range(sweeps):
        T = T0 * 0.002 ** (sw / max(sweeps - 1, 1)) + 1e-9
        for i in rng.permutation(n):
            d = (1 - 2 * x[:, i]) * (lin[i] + h[:, i])
            acc = (d <= 0) | (rng.random(shots) < np.exp(-np.clip(d, 0, None) / T))
            flip = np.where(acc, 1 - 2 * x[:, i], 0.0)
            x[:, i] += flip
            h += np.outer(flip, Qs[i])
    return x.astype(np.int8)


def decode(xbits, G, S):
    out = []
    for row in xbits.reshape(-1, G, S):
        out.append(tuple(int(np.argmax(r)) for r in row) if (row.sum(axis=1) == 1).all() else None)
    return out


# ----------------------------------------------------------------------------- the assurance loop
def run_loop(samples, cost, forb, sizes, rem, opt_obj, feasible_exists, adaptive):
    """samples: list of decoded plans in draw order (None = not one-hot). Returns per-policy outcome."""
    out = {}
    used = len(samples)
    if adaptive:  # batches of BATCH until a verified plan appears
        for b in range(0, len(samples), BATCH):
            if any(verify(a, forb, sizes, rem) for a in samples[b:b + BATCH]):
                used = b + BATCH
                break
    pool = samples[:used]
    valid = [a for a in pool if verify(a, forb, sizes, rem)]
    best = min(valid, key=lambda a: sum(cost[g, s] for g, s in enumerate(a))) if valid else None
    # most frequent sample, unverified
    cnt = {}
    for a in pool:
        cnt[a] = cnt.get(a, 0) + 1
    top = max(cnt, key=cnt.get)
    out["raw_invalid"] = not verify(top, forb, sizes, rem)
    tool = "sampler" if best is not None else None
    plan = best
    if plan is None:
        g = greedy(cost, forb, sizes, rem)
        if verify(g, forb, sizes, rem):
            plan, tool = g, "greedy"
    out["shots_used"] = used
    out["sampler_found"] = best is not None
    # uncertified loop: escalate if neither tool found a plan
    out["uncert_escalate"] = plan is None
    out["uncert_false_escalation"] = plan is None and feasible_exists
    # certified loop: MILP decides before escalating (and supplies the plan if one exists)
    out["cert_escalate"] = plan is None and not feasible_exists
    out["cert_false_escalation"] = False
    out["cert_missed_escalation"] = False
    if plan is not None:
        obj = sum(cost[g, s] for g, s in enumerate(plan))
        out["gap_pct"] = 100 * (obj - opt_obj) / opt_obj if opt_obj > 0 else 0.0
        out["optimal"] = abs(obj - opt_obj) < 1e-6
    else:
        out["gap_pct"] = 0.0 if feasible_exists else None  # certified loop dispatches the MILP plan
        out["optimal"] = feasible_exists
    out["tool"] = tool or ("milp" if feasible_exists else "escalate")
    return out


# ----------------------------------------------------------------------------- study A: twin episodes
def twin_job(i):
    seed = 42 + 17 * i
    e = HqrlEngine(config=HqrlConfig(seed=seed))
    r = random.Random(seed)
    rng = np.random.default_rng(seed)
    bits = Q.bit_table(12)
    rows, theta, last = [], None, None
    for k in range(6):
        if k <= 4:
            apply_event(e, k, r)
        else:  # E5: Shelter B fails as well
            e.shelters["SB"]["status"] = "FAILED"
            e.shelters["SB"]["remaining"] = 0
        key = state_key(e)
        if key == last:
            continue
        last = key
        inst = Q.instance_from_engine(e, 4)
        cost, forb, sizes, rem = inst["cost"], inst["forb"], inst["sizes"], inst["rem"].astype(float)
        a_m, obj_m, ms_m, _ = milp_solve(cost, forb, sizes, rem)
        ex = Q.exact_solve(inst)
        assert (a_m is None) == (not np.isfinite(ex["obj"])) and (a_m is None or abs(obj_m - ex["obj"]) < 1e-6), \
            "MILP agrees with enumeration"
        feasible = a_m is not None
        d = Q.diagonals(inst, bits)
        qa = Q.Qaoa(inst, "xy", d)
        t0 = time.perf_counter()
        th = None
        for p in range(1, P_LAYERS + 1):
            th, _ = qa.optimise(p, rng, restarts=2, warm=th)
        q_ms = (time.perf_counter() - t0) * 1000
        prq = np.abs(qa.state(th)) ** 2
        lin, Qs, P = qubo(cost, forb, sizes, rem)
        row = {"seed": seed, "event": k, "feasible": feasible, "milp_ms": ms_m, "enum_ms": ex["ms"],
               "qaoa_train_ms": q_ms, "pfeas_qaoa": float(prq[d["feas"]].sum()), "draws": {}}
        for sampler in ("qaoa", "sa"):
            for adaptive in (False, True):
                res = []
                for dr in range(DRAWS):
                    rr = np.random.default_rng(1000 * seed + 100 * k + dr)
                    if sampler == "qaoa":
                        ks = Q.sample(prq, SHOTS, rr)
                        smp = [Q.index_to_assign(int(x), 4, 3) for x in ks]
                    else:
                        smp = decode(sa_sample(lin, Qs, P, SHOTS, rr, sweeps=30), 4, 3)
                    res.append(run_loop(smp, cost, forb, sizes, rem, obj_m if feasible else np.inf, feasible, adaptive))
                row["draws"][f"{sampler}_{'adaptive' if adaptive else 'fixed'}"] = res
        rows.append(row)
    return rows


# ----------------------------------------------------------------------------- study B: city scale
CITIES = ["delhi", "chennai", "mumbai", "kolkata", "guwahati", "patna"]


def city_graph(c):
    roads = {r["road_id"]: r for r in c["roads"]}
    g = nx.Graph()
    for u, v, rid in c["graph_edges"]:
        if u == v:
            continue
        info = c["edge_info"].get(f"{u}|{v}") or c["edge_info"].get(f"{v}|{u}")
        if not info or info.get("km") is None:
            continue
        r = roads.get(rid, {})
        flood = float(r.get("flood_exposure") or 0.2)
        w = float(info["km"]) * (1.0 + 0.8 * float(r.get("traffic") or 0.4) + 1.4 * flood)
        if not g.has_edge(u, v) or g[u][v]["w"] > w:
            g.add_edge(u, v, w=w, km=float(info["km"]), flood=flood, rid=rid)
    return g.subgraph(max(nx.connected_components(g), key=len)).copy()


def nearest(c, lat, lon, nodes):
    return min(nodes, key=lambda n: (c["graph_nodes"][n][0] - lat) ** 2 + (c["graph_nodes"][n][1] - lon) ** 2)


def city_job(args):
    city, G, tight, k = args
    c = json.loads((ROOT / "backend" / "data" / "cities" / f"{city}.json").read_text(encoding="utf-8"))
    g = city_graph(c)
    nodes = list(g.nodes)
    seed = zlib.crc32(f"{city}|{G}|{tight}|{k}".encode())
    rng = np.random.default_rng(seed)
    S = len(c["shelters"])
    zn = [nearest(c, z["lat"], z["lon"], nodes) for z in c["zones"]]
    sn = [nearest(c, s["lat"], s["lon"], nodes) for s in c["shelters"]]
    cap = np.array([float(s["capacity"]) for s in c["shelters"]])
    rem = cap * (1 - rng.uniform(0.15, 0.45, S))
    # disruption: the 3 most flood-exposed roads close and one random shelter fails
    closed = sorted({d["rid"] for _, _, d in g.edges(data=True)}, key=lambda rid: -max(
        d["flood"] for _, _, d in g.edges(data=True) if d["rid"] == rid))[:3]
    h = g.copy()
    h.remove_edges_from([(u, v) for u, v, d in g.edges(data=True) if d["rid"] in closed])
    failed = int(rng.integers(S))
    rem[failed] = 0
    gz = rng.integers(len(zn), size=G)
    sizes = rng.uniform(0.5, 1.5, G)
    sizes = np.maximum(1, np.round(sizes / sizes.sum() * tight * rem.sum())).astype(float)
    dist = {}
    for z in set(gz.tolist()):
        dist[z] = nx.single_source_dijkstra_path_length(h, zn[z], weight="w")
    cost = np.zeros((G, S))
    forb = np.zeros((G, S), dtype=bool)
    for gi in range(G):
        for s in range(S):
            dd = dist[gz[gi]].get(sn[s])
            if dd is None or rem[s] <= 0 or sizes[gi] > rem[s]:
                forb[gi, s] = True
            else:
                cost[gi, s] = dd / 25.0 * 60.0
    a_m, obj_m, ms_m, status = milp_solve(cost, forb, sizes, rem)
    feasible = a_m is not None
    t0 = time.perf_counter()
    lin, Qs, P = qubo(cost, forb, sizes, rem)
    res = {}
    for adaptive in (False, True):
        out = []
        for dr in range(DRAWS):
            rr = np.random.default_rng(seed + 7919 * dr)
            smp = decode(sa_sample(lin, Qs, P, SHOTS, rr, sweeps=40), G, S)
            out.append(run_loop(smp, cost, forb, sizes, rem, obj_m if feasible else np.inf, feasible, adaptive))
        res["adaptive" if adaptive else "fixed"] = out
    gr = greedy(cost, forb, sizes, rem)
    return {"city": city, "G": G, "S": S, "tight": tight, "k": k, "feasible": feasible, "milp_ms": ms_m,
            "milp_status": status, "sa_ms": (time.perf_counter() - t0) * 1000 / (2 * DRAWS),
            "greedy_valid": verify(gr, forb, sizes, rem),
            "greedy_gap_pct": (100 * (sum(cost[q, s] for q, s in enumerate(gr)) - obj_m) / obj_m
                               if feasible and verify(gr, forb, sizes, rem) and obj_m > 0 else None),
            "draws": res}


if __name__ == "__main__":
    t0 = time.time()
    out = {"config": {"shots": SHOTS, "batch": BATCH, "draws": DRAWS, "p": P_LAYERS}}
    with Pool(3) as pool:
        twin = []
        for rows in pool.imap_unordered(twin_job, range(30)):
            twin += rows
            print(f"twin seed {rows[0]['seed']} done {time.time() - t0:.0f}s", flush=True)
        out["twin"] = twin
        jobs = [(c, G, t, k) for c in CITIES for G in (8, 16, 32) for t in (0.6, 0.9) for k in range(10)]
        city = []
        for r in pool.imap_unordered(city_job, jobs):
            city.append(r)
            if len(city) % 30 == 0:
                print(f"city {len(city)}/{len(jobs)} {time.time() - t0:.0f}s", flush=True)
        out["city"] = city
    (WORK / "p3_v2.json").write_text(json.dumps(out, default=float), encoding="utf-8")
    print("done", f"{time.time() - t0:.0f}s")
