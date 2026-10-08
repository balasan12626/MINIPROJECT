"""Seeded experiments behind every routing/gating number in the IEEE paper.

Runs backend/simulation/hqrl_demo.py without modifying it and writes <work>/exp.json:
  bench    – 6-method benchmark, 30 scenarios, seed 42            (Table II)
  ablation – proposer without vs with shield, 20 scenarios          (text, Sec. V-B)
  sweep    – closures 0/2/4 x flood severity 0.20-0.65, 30 each    (Fig. 2)
  gating   – failure injection vs auto-dispatch gate               (Table III)
Run with the repo .venv (needs networkx):  .venv\\Scripts\\python.exe exp.py <work>
"""
import json
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]  # scripts -> ieee-paper -> skills -> .claude -> repo
sys.path.insert(0, str(ROOT))
from backend.simulation.hqrl_demo import HqrlConfig, HqrlEngine  # noqa: E402

WORK = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
WORK.mkdir(parents=True, exist_ok=True)

METHODS = {
    "Static shortest path": lambda e, g: e._method_static_shortest(g),
    "Flood-aware A*": lambda e, g: e._method_astar(g),
    "Risk-aware greedy": lambda e, g: e._method_risk_greedy(g),
    "Proposer only": lambda e, g: e._method_ppo_only(g),
    "Proposer + QUBO (SA)": lambda e, g: e._method_ppo_qubo(g),
    "Proposer + QUBO (QAOA-insp.)": lambda e, g: e._method_ppo_qaoa(g),
}
out = {"sweep": [], "gating": []}

engine = HqrlEngine()
engine.run_benchmark(n_scenarios=30, seed=42)
out["bench"] = engine.benchmark["table"]
out["ablation"] = engine.run_ablation(n_scenarios=20, seed=42, store_only=True)

N = 30
for sev in (0.2, 0.35, 0.5, 0.65):
    for clos in (0, 2, 4):
        agg = {k: [] for k in METHODS}
        for i in range(N):
            eng = HqrlEngine(config=HqrlConfig(seed=42 + i * 17, flood_severity=sev, n_road_closures=clos))
            snap, g = eng._network_snapshot(), eng.groups[0]
            for name, fn in METHODS.items():
                eng._restore_network(snap)
                agg[name].append(eng._eval_method_on(name, fn, g))
        for name, rows in agg.items():
            out["sweep"].append({
                "severity": sev, "closures": clos, "method": name,
                "safe": round(st.mean(r["safe_evacuation_pct"] for r in rows), 2),
                "clear": round(st.mean(r["clearance_time_min"] for r in rows), 2),
                "capv": round(st.mean(r["capacity_violations"] for r in rows), 3),
                "replan_ms": round(st.mean(r["replanning_latency_ms"] for r in rows), 3)})

fails = ["weather_outage", "delayed_radar", "sensor_drift", "outdated_road_data", "citizen_conflict",
         "comms_failure", "shelter_failure"]
cases = [[]] + [[f] for f in fails] + [["delayed_radar", "sensor_drift"], ["sensor_drift", "outdated_road_data"],
                                       ["weather_outage", "sensor_drift", "outdated_road_data"]]
for c in cases:
    e = HqrlEngine(config=HqrlConfig(seed=42))
    e.set_failures({f: True for f in c})
    rel = sum(s["reliability"] for s in e.sources) / len(e.sources)
    out["gating"].append({"failures": c or ["none"], "mean_reliability": round(rel, 3),
                          "auto_dispatch": e.auto_dispatch_allowed, "human_required": e.human_required})

(WORK / "exp.json").write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
for r in out["bench"]:
    print(f"{r['method']:<24} safe={r['safe_evacuation_pct']:>6} clear={r['clearance_time_min']:>7} replan={r['replanning_latency_ms']}")
print("saved", WORK / "exp.json")
