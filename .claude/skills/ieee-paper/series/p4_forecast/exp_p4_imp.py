"""Gain importance of the selected model, per feature and per input group -> <work>/p4_imp.json.
Reads models/flood_forecast_v4.pkl only (no data). usage: .venv\\Scripts\\python.exe exp_p4_imp.py <work>"""
import json
import sys
from pathlib import Path

import joblib

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
WORK = Path(sys.argv[1])
meta = json.loads((ROOT / "models" / "flood_model_metadata_v4.json").read_text(encoding="utf-8"))
feats = meta["features"]
model = joblib.load(ROOT / "models" / "flood_forecast_v4.pkl")
est = model.steps[-1][1] if hasattr(model, "steps") else model
gain = est.get_booster().get_score(importance_type="total_gain")
# the booster names features f0.. when fitted on arrays, or by column name when fitted on a DataFrame
named = {(feats[int(k[1:])] if k[0] == "f" and k[1:].isdigit() else k): v for k, v in gain.items()}
tot = sum(named.values())
GROUPS = {
    "flow": [f for f in feats if f.startswith("qr_") or f in ("log_q", "q_obs_today")],
    "rain": [f for f in feats if f.startswith("prcp_")],
    "weather": [f for f in feats if f in ("tmax", "tmin", "rh", "pet", "aet")],
    "soil": [f for f in feats if f.startswith("sm")],
    "season": [f for f in feats if f.startswith("doy_")],
}
GROUPS["static"] = [f for f in feats if not any(f in v for v in GROUPS.values())]
out = {"feature": {f: named.get(f, 0.0) / tot for f in feats},
       "group": {g: sum(named.get(f, 0.0) for f in fs) / tot for g, fs in GROUPS.items()}}
(WORK / "p4_imp.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
top = sorted(out["feature"].items(), key=lambda kv: -kv[1])[:12]
print({g: round(v, 3) for g, v in out["group"].items()})
print([(f, round(v, 3)) for f, v in top])
