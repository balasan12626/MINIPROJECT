"""Where does the selected forecaster succeed and fail? -> <work>/p4_extra.json. Test gauges only (low memory).

Primary test set of exp_p4.py (unseen gauges, 2015-2020), selected model models/flood_forecast_v4.pkl at its
validation threshold:
  lead    - for each h in 1..3, of the days t with Q(t+h) >= q95, the share on which the model alarmed on day t
            (recall by lead day), and the same for rows where the river is still below q95 on day t
  season  - metrics in the monsoon months (June-September) and in the rest of the year
  gauges  - per-gauge balanced accuracy with catchment attributes (area, aridity, mean rain, slope) and
            Spearman correlations between them
usage: .venv\\Scripts\\python.exe exp_p4_extra.py <work>
"""
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.metrics import average_precision_score, balanced_accuracy_score

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
sys.path[:0] = [str(ROOT)]
from backend.ml.features_v4 import DATA, VAL_END, gauge_frame, load_static  # noqa: E402

WORK = Path(sys.argv[1])
meta = json.loads((ROOT / "models" / "flood_model_metadata_v4.json").read_text(encoding="utf-8"))
feats, THR = meta["features"], float(meta["decision_threshold"])
unseen = set(meta["unseen_gauges"])
qdf = pd.read_csv(DATA / "streamflow_timeseries" / "streamflow_observed.csv")
dates = pd.DatetimeIndex(pd.to_datetime(qdf[["year", "month", "day"]]))
static = load_static()
frames = []
for col in qdf.columns[3:]:
    if int(col) not in unseen:
        continue
    q = qdf[col].astype(float).set_axis(dates)
    g = gauge_frame(int(col), qdf[col].astype(float), dates)
    thr = g.attrs["flood_threshold"]
    g["date"] = g.index
    for h in (1, 2, 3):
        fq = q.shift(-h).reindex(g.index)
        g[f"y{h}"] = np.where(fq.notna(), (fq >= thr).astype(float), np.nan)
    g["fut_ratio"] = (pd.concat([q.shift(-h) for h in (1, 2, 3)], axis=1).max(axis=1) / thr).reindex(g.index)
    frames.append(g[g["year"] > VAL_END])
te = pd.concat(frames, ignore_index=True).join(static.astype("float32"), on="gauge_id")
assert len(te) == meta["n_test_unseen"], "same test rows as the paper"
model = joblib.load(ROOT / "models" / "flood_forecast_v4.pkl")
p = model.predict_proba(te[feats])[:, 1]
alarm = p >= THR
y = te["y"].to_numpy().astype(int)
below = (te["flood_today"] == 0).to_numpy()
out = {"lead": {}, "season": {}}
for h in (1, 2, 3):
    yh = te[f"y{h}"].to_numpy()
    m = yh == 1
    mb = m & below
    out["lead"][h] = {"n": int(m.sum()), "recall": float(alarm[m].mean()),
                      "n_rising": int(mb.sum()), "recall_rising": float(alarm[mb].mean()) if mb.any() else None}


def mets(mask):
    yy, aa, pp = y[mask], alarm[mask], p[mask]
    tp, fp = int((aa & (yy == 1)).sum()), int((aa & (yy == 0)).sum())
    return {"n": int(mask.sum()), "pos_rate": float(yy.mean()), "ba": float(balanced_accuracy_score(yy, aa)),
            "pr_auc": float(average_precision_score(yy, pp)), "recall": tp / max(int(yy.sum()), 1),
            "precision": tp / max(tp + fp, 1), "alarms_per_1000": 1000 * float(aa.mean()),
            "false_alarms": fp}


mon = te["date"].dt.month.isin([6, 7, 8, 9]).to_numpy()
out["season"]["monsoon"] = mets(mon)
out["season"]["other"] = mets(~mon)
fr = te["fut_ratio"].to_numpy()
for lab, mm in (("monsoon", mon), ("other", ~mon)):
    fa = mm & alarm & (y == 0) & np.isfinite(fr)
    out["season"][lab]["near_miss_share"] = float(((fr[fa] >= 0.7) & (fr[fa] < 1.0)).mean()) if fa.any() else None
    out["season"][lab]["fa_median_ratio"] = float(np.median(fr[fa])) if fa.any() else None
out["season"]["fp_share_monsoon"] =out["season"]["monsoon"]["false_alarms"] / max(
    out["season"]["monsoon"]["false_alarms"] + out["season"]["other"]["false_alarms"], 1)
rows = []
for gid, ix in te.groupby("gauge_id").indices.items():
    yy = y[ix]
    if yy.min() == yy.max():
        continue
    st = static.loc[gid]
    rows.append({"gauge": int(gid), "ba": float(balanced_accuracy_score(yy, alarm[ix])), "pos_rate": float(yy.mean()),
                 "log_area": float(st["log_area"]), "aridity": float(st["aridity_p_pet"]),
                 "p_mean": float(st["p_mean"]), "slope": float(st["slope_mean"])})
out["gauges"] = rows
out["spearman"] = {}
ba = [r["ba"] for r in rows]
for k in ("log_area", "aridity", "p_mean", "slope", "pos_rate"):
    rho, pv = spearmanr([r[k] for r in rows], ba)
    out["spearman"][k] = {"rho": float(rho), "p": float(pv)}
(WORK / "p4_extra.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
print(json.dumps({"lead": out["lead"], "season": {k: (v if not isinstance(v, dict) else
                  {a: round(b, 3) for a, b in v.items()}) for k, v in out["season"].items()},
                  "spearman": out["spearman"]}, indent=1))
