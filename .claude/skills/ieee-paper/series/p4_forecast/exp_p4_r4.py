"""P4 operating rules -> <work>/p4_r4.json. Offline; stored selected model (models/flood_forecast_v4.pkl), primary split.

Question: persistence has the best critical success index (CSI) because a river already above its level usually stays
there, while the model is better on rivers still below the level. Can a decision rule that combines them reduce false
alarms? Rules, all with thresholds chosen to maximise CSI on the validation years (seen gauges, 2009-2014) and then
scored ONCE on the test set (unseen gauges, 2015-2020):
  model       - one threshold on the model score
  seasonal    - separate thresholds for June-September and the other months
  hybrid      - alarm if the river is above its level today (persistence), otherwise the model score with its own threshold
  hybrid_seas - hybrid with seasonal thresholds on the below-level rows
Paired gauge bootstrap (1,000) of the CSI and BA differences against 'model' and against persistence.
usage: .venv\\Scripts\\python.exe exp_p4_r4.py <work>
"""
import json
import sys
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import balanced_accuracy_score
from sklearn.model_selection import GroupShuffleSplit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
from backend.ml.features_v4 import DATA, TRAIN_END, VAL_END, gauge_frame, load_static  # noqa: E402

WORK = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
SEED = 42
NB = 1000
t00 = time.time()


def log(*a):
    print(f"[{time.time() - t00:6.0f}s]", *a, flush=True)


qdf = pd.read_csv(DATA / "streamflow_timeseries" / "streamflow_observed.csv")
dates = pd.DatetimeIndex(pd.to_datetime(qdf[["year", "month", "day"]]))
static = load_static()
frames = []
for col in qdf.columns[3:]:
    g = gauge_frame(int(col), qdf[col].astype(float), dates)
    if g is not None:
        g["date"] = g.index
        frames.append(g)
df = pd.concat(frames, ignore_index=True).join(static.astype("float32"), on="gauge_id")
del frames
meta = json.loads((ROOT / "models" / "flood_model_metadata_v4.json").read_text(encoding="utf-8"))
feats = meta["features"]
gauges = np.array(sorted(df["gauge_id"].unique()))
_, ui = next(GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=SEED).split(gauges, groups=gauges))
unseen = set(gauges[ui].tolist())
assert sorted(int(g) for g in unseen) == meta["unseen_gauges"]
is_un = df["gauge_id"].isin(unseen)
va = df[~is_un & (df["year"] > TRAIN_END) & (df["year"] <= VAL_END)].reset_index(drop=True)
te = df[is_un & (df["year"] > VAL_END)].reset_index(drop=True)
del df
model = joblib.load(ROOT / "models" / "flood_forecast_v4.pkl")
THR = float(meta["decision_threshold"])
S = {"va": model.predict_proba(va[feats])[:, 1], "te": model.predict_proba(te[feats])[:, 1]}
assert abs(balanced_accuracy_score(te["y"].astype(int), S["te"] >= THR) - 0.8978479116831157) < 1e-9
log("scored", len(va), len(te))


def parts(fr):
    return {"y": fr["y"].to_numpy().astype(int), "high": (fr["flood_today"] == 1).to_numpy(),
            "mon": fr["date"].dt.month.isin([6, 7, 8, 9]).to_numpy()}


P = {"va": parts(va), "te": parts(te)}


def csi(y, a):
    tp = int((a & (y == 1)).sum())
    return tp / max(tp + int((a & (y == 0)).sum()) + int((~a & (y == 1)).sum()), 1)


GRID = np.round(np.arange(0.05, 0.996, 0.01), 2)


def best(y, s, mask):
    """threshold maximising validation CSI of the alarms on the rows in mask (other rows fixed elsewhere)"""
    return float(max(GRID, key=lambda t: csi(y[mask], s[mask] >= t)))


def rule(name, d, s, th):
    p = P[d]
    if name == "model":
        return s >= th["t"]
    if name == "seasonal":
        return np.where(p["mon"], s >= th["t_mon"], s >= th["t_oth"])
    if name == "hybrid":
        return p["high"] | (s >= th["t"])
    if name == "hybrid_seas":
        return p["high"] | np.where(p["mon"], s >= th["t_mon"], s >= th["t_oth"])
    raise KeyError(name)


yv, sv, pv = P["va"]["y"], S["va"], P["va"]
TH = {"model": {"t": best(yv, sv, np.ones(len(yv), bool))},
      "seasonal": {"t_mon": best(yv, sv, pv["mon"]), "t_oth": best(yv, sv, ~pv["mon"])}}
# hybrid: the threshold applies to below-level rows; choose it for the CSI of the whole rule on validation
TH["hybrid"] = {"t": float(max(GRID, key=lambda t: csi(yv, pv["high"] | (sv >= t))))}
TH["hybrid_seas"] = {
    "t_mon": float(max(GRID, key=lambda t: csi(yv[pv["mon"]], (pv["high"] | (sv >= t))[pv["mon"]]))),
    "t_oth": float(max(GRID, key=lambda t: csi(yv[~pv["mon"]], (pv["high"] | (sv >= t))[~pv["mon"]])))}
log("thresholds (validation CSI)", TH)

yt, st, pt = P["te"]["y"], S["te"], P["te"]
A = {k: rule(k, "te", st, TH[k]) for k in TH}
A["model_ba_thr"] = st >= THR
A["persistence"] = pt["high"]

# onsets as in exp_p4.py: river reaches q95 after >= 7 observed days below it; warned 1-3 days ahead
gids = te["gauge_id"].to_numpy()
ug = np.unique(gids)
gidx = {g: np.flatnonzero(gids == g) for g in ug}
ONS = []
for g, gi in gidx.items():
    order = gi[np.argsort(te["date"].to_numpy()[gi])]
    ft = te["flood_today"].to_numpy()[order]
    d = te["date"].to_numpy()[order]
    pos = {pd.Timestamp(x): k for k, x in enumerate(d)}
    for k in range(7, len(order)):
        if ft[k] == 1 and np.all(ft[k - 7:k] == 0) and (pd.Timestamp(d[k]) - pd.Timestamp(d[k - 7])).days == 7:
            ONS.append([order[pos[pd.Timestamp(d[k]) - pd.Timedelta(days=L)]] if (pd.Timestamp(d[k]) - pd.Timedelta(days=L)) in pos
                        else -1 for L in (1, 2, 3)])
ONS = np.array(ONS)


def summ(a, rows=None):
    rows = np.arange(len(yt)) if rows is None else rows
    y_, a_ = yt[rows], a[rows]
    tp = int((a_ & (y_ == 1)).sum())
    w = np.zeros(len(ONS), bool)
    for c in range(3):
        ok = ONS[:, c] >= 0
        w[ok] |= a[ONS[ok, c]]
    b = ~pt["high"][rows]
    return {"csi": csi(y_, a_), "ba": float(balanced_accuracy_score(y_, a_)), "precision": tp / max(int(a_.sum()), 1),
            "recall": tp / max(int((y_ == 1).sum()), 1), "alarms_per_1000": float(1000 * a_.mean()),
            "below_ba": float(balanced_accuracy_score(y_[b], a_[b])), "onsets_warned_pct": float(100 * w.mean())}


OUT = {"objective": "validation CSI", "thresholds": TH, "decision_threshold_ba": THR, "n_test": int(len(yt)),
       "n_onsets": int(len(ONS)), "test": {k: summ(a) for k, a in A.items()},
       "test_monsoon": {k: summ(a, np.flatnonzero(pt["mon"])) for k, a in A.items()},
       "validation": {k: {"csi": csi(yv, rule(k, "va", sv, TH[k]))} for k in TH}}
rng = np.random.default_rng(SEED)
diffs = {f"{k}-{r}": {"csi": [], "ba": []} for k in ("seasonal", "hybrid", "hybrid_seas") for r in ("model", "persistence")}
diffs["model-persistence"] = {"csi": [], "ba": []}
for _ in range(NB):
    ix = np.concatenate([gidx[g] for g in rng.choice(ug, len(ug), replace=True)])
    for key in diffs:
        k, r = key.split("-")
        diffs[key]["csi"].append(csi(yt[ix], A[k][ix]) - csi(yt[ix], A[r][ix]))
        diffs[key]["ba"].append(balanced_accuracy_score(yt[ix], A[k][ix]) - balanced_accuracy_score(yt[ix], A[r][ix]))
OUT["paired"] = {k: {m: [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))] for m, v in d.items()} for k, d in diffs.items()}
# descriptive trade-off curve on the test set (no choice is made from it): CSI and onsets warned per threshold
curve = {"thr": [], "model_csi": [], "model_warn": [], "hybrid_csi": [], "hybrid_warn": []}
for t in np.round(np.arange(0.05, 0.996, 0.01), 2):
    for k, a in (("model", st >= t), ("hybrid", pt["high"] | (st >= t))):
        sm = summ(a)
        curve[f"{k}_csi"].append(sm["csi"])
        curve[f"{k}_warn"].append(sm["onsets_warned_pct"])
    curve["thr"].append(float(t))
OUT["curve"] = curve
(WORK / "p4_r4.json").write_text(json.dumps(OUT, indent=1, default=float), encoding="utf-8")
log({k: (round(v["csi"], 3), round(v["precision"], 3), round(v["recall"], 3), round(v["alarms_per_1000"], 1),
         round(v["onsets_warned_pct"], 1)) for k, v in OUT["test"].items()})
log("paired", OUT["paired"])
log("done")
