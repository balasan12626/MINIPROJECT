"""Zone-to-shelter reachability after the city disruption of exp_p3_v2.py -> <work>/p3_reach.json.

Explains the infeasible city instances: a zone that the three road closures cut off from every shelter makes
any instance with a group in it unsolvable.
usage: .venv\\Scripts\\python.exe exp_p3_reach.py <work>
"""
import json
import sys
from pathlib import Path

import networkx as nx
import numpy as np

import exp_p3_v2 as E

WORK = Path(sys.argv[1])
out = {}
for city in E.CITIES:
    c = json.loads((E.ROOT / "backend" / "data" / "cities" / f"{city}.json").read_text(encoding="utf-8"))
    g = E.city_graph(c)
    nodes = list(g.nodes)
    zn = [E.nearest(c, z["lat"], z["lon"], nodes) for z in c["zones"]]
    sn = [E.nearest(c, s["lat"], s["lon"], nodes) for s in c["shelters"]]
    closed = sorted({d["rid"] for _, _, d in g.edges(data=True)}, key=lambda rid: -max(
        d["flood"] for _, _, d in g.edges(data=True) if d["rid"] == rid))[:3]
    h = g.copy()
    h.remove_edges_from([(u, v) for u, v, d in g.edges(data=True) if d["rid"] in closed])
    reach = np.array([[nx.has_path(h, z, s) for s in sn] for z in zn])
    out[city] = {"zones": len(zn), "shelters": len(sn), "pairs_open": float(reach.mean()),
                 "zones_cut_off": int((~reach.any(1)).sum())}
    print(city, out[city], flush=True)
(WORK / "p3_reach.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
