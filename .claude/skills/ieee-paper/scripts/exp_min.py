"""Per-source reliabilities for the failure-injection cases -> <work>/exp_min.json.

Deterministic (no timing), so it runs on every build. Feeds the minimum-based gate
comparison in Table V of the paper. Run with the repo .venv.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from backend.simulation.hqrl_demo import HqrlConfig, HqrlEngine  # noqa: E402

WORK = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
fails = ["weather_outage", "delayed_radar", "sensor_drift", "outdated_road_data", "citizen_conflict",
         "comms_failure", "shelter_failure"]
cases = [[]] + [[f] for f in fails] + [["delayed_radar", "sensor_drift"], ["sensor_drift", "outdated_road_data"],
                                       ["weather_outage", "sensor_drift", "outdated_road_data"]]
out = []
for c in cases:
    e = HqrlEngine(config=HqrlConfig(seed=42))
    e.set_failures({f: True for f in c})
    rel = [s["reliability"] for s in e.sources]
    out.append({"failures": c or ["none"], "mean": round(sum(rel) / len(rel), 3), "min": round(min(rel), 3),
                "min_gate_allows": min(rel) >= 0.60, "mean_gate_allows": sum(rel) / len(rel) >= 0.60})
(WORK / "exp_min.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
print("saved", WORK / "exp_min.json")
