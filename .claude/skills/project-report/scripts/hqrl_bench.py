"""Run the real HQRL benchmark (seed 42) and save it for the report.

Must run with the repo venv that has networkx:  .venv/Scripts/python.exe
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths as P

sys.path.insert(0, str(P.ROOT))
from backend.simulation.hqrl_demo import HqrlEngine  # noqa: E402

engine = HqrlEngine()
state = engine.run_benchmark(n_scenarios=30, seed=42)
ablation = engine.run_ablation(n_scenarios=20, seed=42, store_only=True)
bench = getattr(engine, "benchmark", None) or state.get("benchmark")
out = P.WORK / "hqrl.json"
out.write_text(json.dumps({"bench": bench, "ablation": ablation}, default=str), encoding="utf-8")
for row in bench["table"]:
    print(f"{row['method']:<24} safe={row['safe_evacuation_pct']:>6} clear={row['clearance_time_min']:>7} cap={row['capacity_violations']}")
print("saved", out)
