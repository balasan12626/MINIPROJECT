"""Real seeded experiments on backend/simulation/hqrl_demo.py for the revised paper (no repo changes)."""
import copy, json, statistics as st, sys
sys.path.insert(0, r"D:\fineal mini proejct\1")
from backend.simulation.hqrl_demo import HqrlEngine, HqrlConfig

M = {
 "Static shortest path": lambda e,g: e._method_static_shortest(g),
 "Flood-aware A*":       lambda e,g: e._method_astar(g),
 "Risk-aware greedy":    lambda e,g: e._method_risk_greedy(g),
 "Proposer only":        lambda e,g: e._method_ppo_only(g),
 "Proposer + QUBO (SA)": lambda e,g: e._method_ppo_qubo(g),
 "Proposer + QUBO (QAOA-insp.)": lambda e,g: e._method_ppo_qaoa(g),
}
out = {"sweep": [], "gating": []}
N = 30
for sev in (0.2, 0.35, 0.5, 0.65):
    for clos in (0, 2, 4):
        agg = {k: [] for k in M}
        for i in range(N):
            cfg = HqrlConfig(seed=42 + i*17, flood_severity=sev, n_road_closures=clos)
            eng = HqrlEngine(config=cfg); snap = eng._network_snapshot(); g = eng.groups[0]
            for name, fn in M.items():
                eng._restore_network(snap)
                agg[name].append(eng._eval_method_on(name, fn, g))
        for name, rows in agg.items():
            out["sweep"].append({"severity": sev, "closures": clos, "method": name,
                "safe": round(st.mean(r["safe_evacuation_pct"] for r in rows), 2),
                "clear": round(st.mean(r["clearance_time_min"] for r in rows), 2),
                "capv": round(st.mean(r["capacity_violations"] for r in rows), 3),
                "replan_ms": round(st.mean(r["replanning_latency_ms"] for r in rows), 3)})
# failure-injection gating (single + combined failures)
fails = ["weather_outage","delayed_radar","sensor_drift","outdated_road_data","citizen_conflict","comms_failure","shelter_failure"]
cases = [[]] + [[f] for f in fails] + [["delayed_radar","sensor_drift"],["sensor_drift","outdated_road_data"],["weather_outage","sensor_drift","outdated_road_data"]]
for c in cases:
    e = HqrlEngine(config=HqrlConfig(seed=42))
    e.set_failures({f: True for f in c})
    rel = sum(s["reliability"] for s in e.sources)/len(e.sources)
    out["gating"].append({"failures": c or ["none"], "mean_reliability": round(rel,3), "auto_dispatch": e.auto_dispatch_allowed, "human_required": e.human_required})
json.dump(out, open("exp.json","w"), indent=1)
for r in out["gating"]: print(r)
import collections
for r in out["sweep"]:
    if r["method"] in ("Flood-aware A*","Proposer only","Proposer + QUBO (SA)","Static shortest path"): print(r)
