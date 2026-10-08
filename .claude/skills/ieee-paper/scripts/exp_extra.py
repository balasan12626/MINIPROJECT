"""Extra deterministic analyses for the extended (8-page) P4 -> <work>/exp_extra.json + figures.

  forecast  - scores the stored unseen-gauge test set (models/flood_test_unseen_v4.npz) with the saved
              v4 model; checks BA/ROC-AUC/PR-AUC against models/flood_evaluation_v4.json, then reports
              PR/ROC curves, per-gauge balanced accuracy, a descriptive threshold table and top features
  shield    - one worked example of the shield on the twin (seed 42): candidates, violations, choice
Run with the repo .venv:  exp_extra.py <work>
"""
import json
import sys
import warnings
from pathlib import Path

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from sklearn.metrics import (average_precision_score, balanced_accuracy_score, precision_recall_curve,  # noqa: E402
                             roc_auc_score, roc_curve)

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
WORK = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
out = {}

# ------------------------------------------------------------------ forecasting on unseen gauges
z = np.load(ROOT / "models" / "flood_test_unseen_v4.npz", allow_pickle=True)
X, y, gid, today = z["X"], z["y"].astype(int), z["gauge_id"], z["flood_today"]
model = joblib.load(ROOT / "models" / "flood_forecast_v4.pkl")
ev = json.loads((ROOT / "models" / "flood_evaluation_v4.json").read_text(encoding="utf-8"))
thr = float(ev["decision_threshold"])
ref = ev["test"]["unseen_gauges_2015_2020"]["model"]
prob = model.predict_proba(X)[:, 1]
pred = (prob >= thr).astype(int)
ba, roc, pr = balanced_accuracy_score(y, pred), roc_auc_score(y, prob), average_precision_score(y, prob)
assert abs(ba - ref["balanced_accuracy"]) < 2e-3 and abs(roc - ref["roc_auc"]) < 2e-3, "re-scoring must reproduce the paper"
per_gauge = []
for g in np.unique(gid):
    m = gid == g
    if y[m].min() == y[m].max():
        continue
    per_gauge.append({"gauge": int(g), "n": int(m.sum()), "pos": int(y[m].sum()),
                      "ba": float(balanced_accuracy_score(y[m], pred[m])),
                      "recall": float(pred[m][y[m] == 1].mean())})
bas = np.array([r["ba"] for r in per_gauge])
_p, _r, _ = precision_recall_curve(y, prob)
persist_recall = float(ev["test"]["unseen_gauges_2015_2020"]["baseline_persistence"]["recall"])
model_prec_at_persist = float(_p[_r >= persist_recall].max())
thr_rows = []
for t in (0.30, 0.45, 0.60, 0.75):
    pt = (prob >= t).astype(int)
    tp = int(((pt == 1) & (y == 1)).sum()); fp = int(((pt == 1) & (y == 0)).sum()); fn = int(((pt == 0) & (y == 1)).sum())
    thr_rows.append({"t": t, "recall": tp / (tp + fn), "precision": tp / max(tp + fp, 1),
                     "alarms_per_1000": 1000 * (tp + fp) / len(y)})
feat = [str(f) for f in z["features"]]
imp = model.get_booster().get_score(importance_type="gain")
gain = sorted(((feat[int(k[1:])] if k.startswith("f") and k[1:].isdigit() else k, v) for k, v in imp.items()),
              key=lambda kv: -kv[1])
tot = sum(v for _, v in gain)
out["forecast"] = {"n": int(len(y)), "pos_rate": float(y.mean()), "threshold": thr, "ba": float(ba), "roc_auc": float(roc),
                   "pr_auc": float(pr), "n_gauges": int(len(np.unique(gid))), "n_gauges_with_floods": len(per_gauge),
                   "gauge_ba_median": float(np.median(bas)), "gauge_ba_q1": float(np.percentile(bas, 25)),
                   "gauge_ba_q3": float(np.percentile(bas, 75)), "gauge_ba_min": float(bas.min()),
                   "gauge_ba_below_07": int((bas < 0.7).sum()), "thresholds": thr_rows,
                   "model_prec_at_persist_recall": model_prec_at_persist,
                   "top_features": [{"feature": f, "share": v / tot} for f, v in gain[:8]],
                   "persist_point": {"recall": float(ev["test"]["unseen_gauges_2015_2020"]["baseline_persistence"]["recall"]),
                                     "precision": float(ev["test"]["unseen_gauges_2015_2020"]["baseline_persistence"]["precision"])}}

plt.rcParams.update({"font.family": "serif", "font.serif": ["Times New Roman"], "font.size": 8,
                     "pdf.fonttype": 42, "ps.fonttype": 42})
fig, axs = plt.subplots(1, 2, figsize=(3.45, 1.75))
p_, r_, _ = precision_recall_curve(y, prob)
axs[0].plot(r_, p_, color="0.1", lw=0.9, label="XGBoost")
pp = out["forecast"]["persist_point"]
axs[0].plot([pp["recall"]], [pp["precision"]], "s", color="0.5", ms=4, label="persistence")
axs[0].axhline(y.mean(), color="black", lw=0.5, ls=":")
axs[0].set_xlabel("recall"); axs[0].set_ylabel("precision"); axs[0].legend(fontsize=6, frameon=False)
f_, t_, _ = roc_curve(y, prob)
axs[1].plot(f_, t_, color="0.1", lw=0.9)
axs[1].plot([0, 1], [0, 1], ":", color="black", lw=0.5)
axs[1].set_xlabel("false-positive rate"); axs[1].set_ylabel("true-positive rate")
for a in axs:
    a.grid(lw=0.3)
fig.tight_layout(pad=0.3, w_pad=0.8)
fig.savefig(WORK / "fig_curves.pdf")

fig, ax = plt.subplots(figsize=(3.45, 1.55))
ax.hist(bas, bins=np.linspace(0.4, 1.0, 13), color="0.7", edgecolor="black", lw=0.5)
ax.axvline(np.median(bas), color="black", lw=0.8, ls="--")
ax.set_xlabel("balanced accuracy per unseen gauge"); ax.set_ylabel("gauges")
ax.grid(axis="y", lw=0.3)
fig.tight_layout(pad=0.3)
fig.savefig(WORK / "fig_gauges.pdf")

# ------------------------------------------------------------------ shield worked example (twin, seed 42)
from backend.simulation.hqrl_demo import HqrlConfig, HqrlEngine  # noqa: E402

# fixed rule: the first benchmark seed (42 + 17 i) in which, after the benchmark disruption, the
# shield rejects at least one of the proposer's candidates
for i in range(30):
    seed = 42 + 17 * i
    e = HqrlEngine(config=HqrlConfig(seed=seed))
    e._close_road("R5", "benchmark flood")
    sa = e.shelters["SA"]
    sa["occupancy"] = min(sa["capacity"], sa["occupancy"] + int(sa["capacity"] * 0.5))
    sa["remaining"] = sa["capacity"] - sa["occupancy"]
    g = e.groups[0]
    cands, _ = e._ppo_candidates(g, k=3)
    q = e._qubo_filter(cands, g)
    if any(c["violations"] for c in q["candidates"]):
        break
sel, _ = e._classical_qubo_select(q["feasible"], seed)
out["shield_example"] = {"seed": seed, "shelter_a_remaining": sa["remaining"],
                         "group": {"id": g["id"], "zone": g["zone"], "size": g["size"], "vulnerable": g["vulnerable"]},
                         "closed_roads": sorted(r for r, x in e.roads.items() if x["closed"]),
                         "candidates": [{"rank": c["rank"], "label": c["label"], "travel": c["travel_min"],
                                         "hazard": c["hazard_exposure"], "violations": c["violations"], "status": c["status"]}
                                        for c in q["candidates"]],
                         "selected": sel["label"] if sel else None}
(WORK / "exp_extra.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
print(json.dumps({k: v for k, v in out["forecast"].items() if k != "thresholds"}, indent=1))
print(json.dumps(out["forecast"]["thresholds"], indent=1))
print(json.dumps(out["shield_example"], indent=1))
