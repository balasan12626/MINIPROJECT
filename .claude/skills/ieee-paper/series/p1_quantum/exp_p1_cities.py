"""P1 cross-network transfer test -> <work>/p1_cities.json. Needs p1_holdout.json (the fixed angles).

Shelter-assignment instances on the OpenStreetMap road graphs of six Indian cities
(backend/data/cities/*.json): road geometry, junctions, zone and shelter locations and each road's
flood-exposure proxy come from the city data. Edge weight and travel time follow the live router
(backend/services/route_engine.py): weighted km = km * (1 + 0.8 traffic + 1.4 flood), traffic 0.4 when
unknown, travel minutes = weighted km / 25 km/h * 60. Cost c_gs = T_gs + 5 H_gs as in the twin, with H the
length-weighted mean flood exposure of the path. Demand is not in the city data, so group sizes (8-22)
and shelter seats (capacities 120/90/70, occupancy 15-45 %) are drawn from the twin's distributions.
Disruption, as in the twin benchmark: the most flood-exposed road on any zone->shelter path closes and
the first shelter receives arrivals equal to half its capacity.

The angles fixed on the 30 development instances of the twin (p1_holdout.json) are applied unchanged;
per-instance training (same procedure, seed i) is run for comparison.
"""
import json
import sys
from pathlib import Path

import networkx as nx
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
sys.path[:0] = [str(ROOT), str(HERE.parent), str(HERE)]
import qaoa_sim as Q  # noqa: E402
from exp_p1_v2 import train  # noqa: E402

CITIES = ["delhi", "chennai", "mumbai", "kolkata", "guwahati", "patna"]
SEEDS_PER_CITY = 10
G, S = 4, 3
work = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
# frozen copy of backend/data/cities (rebuilt after the first run); SHA-256 sums in SHA256SUMS.txt there
CITY_DIR = HERE.parent / "city_snapshot_2026-10-13" / "backend" / "data" / "cities"


def hav(a, b):
    lat1, lon1, lat2, lon2 = map(np.radians, (a[0], a[1], b[0], b[1]))
    h = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * np.arcsin(np.sqrt(h))


def city_graph(c):
    roads = {r["road_id"]: r for r in c["roads"]}
    g = nx.Graph()
    for u, v, rid in c["graph_edges"]:
        if u == v:
            continue
        info = c["edge_info"].get(f"{u}|{v}") or c["edge_info"].get(f"{v}|{u}")
        km = float(info["km"]) if info and info.get("km") is not None else hav(c["graph_nodes"][u], c["graph_nodes"][v])
        r = roads.get(rid, {})
        traffic = float(r.get("traffic") or 0.4)
        flood = float(r.get("flood_exposure") or 0.2)
        w = km * (1.0 + 0.8 * traffic + 1.4 * flood)
        if not g.has_edge(u, v) or g[u][v]["w"] > w:
            g.add_edge(u, v, w=w, km=km, flood=flood, rid=rid)
    return g


def nearest(c, lat, lon, nodes):
    return min(nodes, key=lambda n: hav((lat, lon), c["graph_nodes"][n]))


def build(c, g, seed):
    rng = np.random.default_rng(seed)
    comp = max(nx.connected_components(g), key=len)  # route on the main component
    nodes = list(comp)
    zones = [c["zones"][k] for k in rng.choice(len(c["zones"]), G, replace=False)]
    shel = [c["shelters"][k] for k in rng.choice(len(c["shelters"]), S, replace=False)]
    zn = [nearest(c, z["lat"], z["lon"], nodes) for z in zones]
    sn = [nearest(c, s["lat"], s["lon"], nodes) for s in shel]
    cap = np.array([120, 90, 70])
    rem = (cap * (1 - rng.uniform(0.15, 0.45, S))).astype(int)
    sizes = rng.integers(8, 23, G)
    # disruption 1: close the most flood-exposed road on any zone->shelter path
    used = {}
    for a in zn:
        for b in sn:
            if a != b:
                p = nx.shortest_path(g, a, b, weight="w")
                for u, v in zip(p, p[1:]):
                    used[g[u][v]["rid"]] = g[u][v]["flood"]
    closed = max(used, key=used.get) if used else None
    h = g.copy()
    h.remove_edges_from([(u, v) for u, v, d in g.edges(data=True) if d["rid"] == closed])
    # disruption 2: the first shelter receives arrivals equal to half its capacity
    rem[0] = max(0, rem[0] - cap[0] // 2)
    cost = np.zeros((G, S))
    forb = np.zeros((G, S), dtype=bool)
    for gi, a in enumerate(zn):
        for si, b in enumerate(sn):
            try:
                p = nx.shortest_path(h, a, b, weight="w") if a != b else [a]
            except nx.NetworkXNoPath:
                forb[gi, si] = True
                continue
            km = sum(h[u][v]["km"] for u, v in zip(p, p[1:]))
            wkm = sum(h[u][v]["w"] for u, v in zip(p, p[1:]))
            haz = sum(h[u][v]["km"] * h[u][v]["flood"] for u, v in zip(p, p[1:])) / km if km > 0 else 0.0
            cost[gi, si] = wkm / 25.0 * 60.0 + 5.0 * haz
            if sizes[gi] > rem[si]:
                forb[gi, si] = True
    return {"G": G, "S": S, "sizes": sizes, "rem": rem, "cost": cost, "forb": forb, "stab": np.zeros((G, S)),
            "closed": closed, "zones": [z["name"] for z in zones], "shelters": [s["name"] for s in shel]}


if __name__ == "__main__":
    ho = json.loads((work / "p1_holdout.json").read_text(encoding="utf-8"))
    bits = Q.bit_table(G * S)
    rows = []
    for ci, city in enumerate(CITIES):
        c = json.loads((CITY_DIR / f"{city}.json").read_text(encoding="utf-8"))
        g = city_graph(c)
        for k in range(SEEDS_PER_CITY):
            seed = 1000 * (ci + 1) + k
            inst = build(c, g, seed)
            ex = Q.exact_solve(inst)
            if not np.isfinite(ex["obj"]):
                rows.append({"city": city, "seed": seed, "feasible_instance": False})
                continue
            d = Q.diagonals(inst, bits)
            opt = d["obj"] <= ex["obj"] + 1e-6
            naive = tuple(int(np.argmin(np.where(inst["forb"][gg], np.inf, inst["cost"][gg]))) for gg in range(G))
            row = {"city": city, "seed": seed, "feasible_instance": True, "n_feasible": int(d["feas"].sum()),
                   "binding": naive != ex["assign"], "mean_cost": float(inst["cost"][~inst["forb"]].mean()),
                   "uniform": float(opt.sum() / 81), "qubo_exact": bool(opt[int(np.argmin(d["h_qubo"]))])}
            for kind, a in (("xy", 1.0), ("xy", 0.1), ("x", 1.0)):
                qa = Q.Qaoa(inst, kind, d, alpha=a)
                tr = train(qa, opt, d["feas"], seed)
                for p in (1, 2, 3, 4):
                    th = np.asarray(ho["fixed"][f"{kind}:{a}:{p}"]["theta"])
                    pr = np.abs(Q.Qaoa(inst, kind, d, alpha=a).state(th)) ** 2
                    row[f"{kind}:{a}:{p}"] = {"fixed": float(pr[opt].sum()), "fixed_feas": float(pr[d["feas"]].sum()),
                                              "trained": tr[p - 1]["popt"],
                                              "trained_cum_nfev": sum(x["nfev"] for x in tr[:p])}
            rows.append(row)
            r4 = row["xy:1.0:4"]
            print(f"{city} {seed} feas={row['n_feasible']} bind={row['binding']} "
                  f"fixed={r4['fixed']:.3f} trained={r4['trained']:.3f}", flush=True)
    (work / "p1_cities.json").write_text(json.dumps({"cities": CITIES, "rows": rows}), encoding="utf-8")
