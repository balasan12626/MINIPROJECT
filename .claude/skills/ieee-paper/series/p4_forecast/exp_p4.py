"""P4 (forecasting paper) experiments -> <work>/p4.json. Offline; reads dataset/camels_ind and models/.

Same task, split and features as scripts/train_flood_model_v4.py (rebuilt and checked against
models/flood_model_metadata_v4.json and flood_evaluation_v4.json):
  task  - does observed streamflow reach the gauge's train-period p95 on any of days t+1..t+3
  split - 20 % of gauges unseen (GroupShuffleSplit seed 42); train 1980-2008, validation 2009-2014,
          primary test = unseen gauges 2015-2020
Experiments on the primary test rows:
  baselines - persistence, gauge climatology (day-of-year exceedance rate of the gauge's own 1980-2008 record,
              +-15 days), and the CAMELS-IND regional LSTM streamflow simulation (lstm_pred_streamflow.csv,
              driven by observed forcing, so it sees the rain of days t+1..t+3: an optimistic reference)
  ablation  - XGBoost (selected configuration) refit on the same 500k-row training sample with feature groups
              removed, incl. a no-streamflow variant that needs no gauge reading at forecast time
  bootstrap - 1000 resamples of test gauges (cluster bootstrap) for BA and PR-AUC and their differences
  calibration - reliability/ECE on test; isotonic recalibration fitted on validation only
  events    - flood onsets (flow reaches threshold after >= 7 days below): warned 1-3 days ahead?
usage: .venv\\Scripts\\python.exe exp_p4.py <work>
"""
import json
import sys
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import average_precision_score, balanced_accuracy_score, roc_auc_score
from sklearn.model_selection import GroupShuffleSplit
from xgboost import XGBClassifier

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
from backend.ml.features_v4 import DATA, TRAIN_END, VAL_END, gauge_frame, load_static  # noqa: E402
import train_flood_model_v4 as T  # noqa: E402

WORK = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
SEED = 42
t00 = time.time()


def log(*a):
    print(f"[{time.time() - t00:6.0f}s]", *a, flush=True)


# ----------------------------------------------------------------------------- rebuild (with dates)
qdf = pd.read_csv(DATA / "streamflow_timeseries" / "streamflow_observed.csv")
dates = pd.DatetimeIndex(pd.to_datetime(qdf[["year", "month", "day"]]))
lstm = pd.read_csv(DATA / "streamflow_timeseries" / "lstm_pred_streamflow.csv")
lstm.index = pd.DatetimeIndex(pd.to_datetime(lstm[["year", "month", "day"]]))
static = load_static()
frames, thr = [], {}
for col in qdf.columns[3:]:
    g = gauge_frame(int(col), qdf[col].astype(float), dates)
    if g is None:
        continue
    thr[int(col)] = g.attrs["flood_threshold"]
    g["date"] = g.index
    # LSTM reference: simulated flow over days t+1..t+3 relative to the same threshold
    if col in lstm.columns:
        sim = lstm[col].astype(float).reindex(dates)
        fut = pd.concat([sim.shift(-k) for k in (1, 2, 3)], axis=1).max(axis=1)
        g["lstm_score"] = (fut / thr[int(col)]).reindex(g.index).astype("float32").to_numpy()
    else:
        g["lstm_score"] = np.nan
    frames.append(g)
df = pd.concat(frames, ignore_index=True).join(static.astype("float32"), on="gauge_id")
del frames
meta = json.loads((ROOT / "models" / "flood_model_metadata_v4.json").read_text(encoding="utf-8"))
ev = json.loads((ROOT / "models" / "flood_evaluation_v4.json").read_text(encoding="utf-8"))
feats = meta["features"]
gauges = df["gauge_id"].unique()
_, ui = next(GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=SEED).split(gauges, groups=gauges))
unseen = set(gauges[ui].tolist())
assert sorted(int(g) for g in unseen) == meta["unseen_gauges"], "unseen gauges match the stored split"
is_un = df["gauge_id"].isin(unseen)
tr = df[~is_un & (df["year"] <= TRAIN_END)]
va = df[~is_un & (df["year"] > TRAIN_END) & (df["year"] <= VAL_END)]
te = df[is_un & (df["year"] > VAL_END)].reset_index(drop=True)
hist = df[is_un & (df["year"] <= TRAIN_END)][["gauge_id", "date", "y"]]  # unseen gauges' own past record
del df
log(f"train={len(tr):,} val={len(va):,} test={len(te):,} gauges={len(gauges)}")
assert len(te) == meta["n_test_unseen"], "test rows match the stored split"

yte = te["y"].to_numpy().astype(int)
model = joblib.load(ROOT / "models" / "flood_forecast_v4.pkl")
THR = float(meta["decision_threshold"])
p_te = model.predict_proba(te[feats])[:, 1]
p_va = model.predict_proba(va[feats])[:, 1]
yva = va["y"].to_numpy().astype(int)
ba = balanced_accuracy_score(yte, (p_te >= THR).astype(int))
assert abs(ba - ev["test"]["unseen_gauges_2015_2020"]["model"]["balanced_accuracy"]) < 1e-9, "selected model reproduces"
log("selected model reproduces BA", round(ba, 4))


def metrics(y, score, thr_):
    yp = (score >= thr_).astype(int)
    tp = int(((yp == 1) & (y == 1)).sum())
    fp = int(((yp == 1) & (y == 0)).sum())
    fn = int(((yp == 0) & (y == 1)).sum())
    rec = tp / max(tp + fn, 1)
    prec = tp / max(tp + fp, 1)
    return {"ba": float(balanced_accuracy_score(y, yp)), "recall": rec, "precision": prec,
            "f1": 2 * prec * rec / max(prec + rec, 1e-12), "roc_auc": float(roc_auc_score(y, score)),
            "pr_auc": float(average_precision_score(y, score)), "thr": float(thr_), "n": int(len(y))}


def pick(y, s):
    grid = np.quantile(s[np.isfinite(s)], np.linspace(0.5, 0.995, 120))
    return float(max(grid, key=lambda t: balanced_accuracy_score(y, (s >= t).astype(int))))


out = {"n_test": int(len(te)), "n_test_gauges": int(te["gauge_id"].nunique()), "pos_rate": float(yte.mean()),
       "methods": {}}
scores_te = {"xgboost": p_te}
out["methods"]["xgboost"] = metrics(yte, p_te, THR)

# persistence (flood today); rows with no reading today count as "no flood"
pers = np.nan_to_num(te["flood_today"].to_numpy(), nan=0.0)
scores_te["persistence"] = pers
out["methods"]["persistence"] = metrics(yte, pers, 0.5)

# climatology: the gauge's own 1980-2008 exceedance rate within +-15 days of the day of year
hist = hist.assign(doy=hist["date"].dt.dayofyear)


def clim_table(frame):
    tab = {}
    for gid, gdf in frame.groupby("gauge_id"):
        rate = np.zeros(367)
        doy, y = gdf["doy"].to_numpy(), gdf["y"].to_numpy()
        for d in range(1, 367):
            dist = np.minimum(np.abs(doy - d), 366 - np.abs(doy - d))
            m = dist <= 15
            rate[d] = y[m].mean() if m.any() else 0.0
        tab[gid] = rate
    return tab


ctab = clim_table(hist)
clim_te = np.array([ctab[g][d] for g, d in zip(te["gauge_id"], te["date"].dt.dayofyear)])
va_hist = tr[["gauge_id", "date", "y"]].assign(doy=tr["date"].dt.dayofyear)
ctab_va = clim_table(va_hist[va_hist["gauge_id"].isin(va["gauge_id"].unique())])
clim_va = np.array([ctab_va[g][d] for g, d in zip(va["gauge_id"], va["date"].dt.dayofyear)])
t_clim = pick(yva, clim_va)
scores_te["climatology"] = clim_te
out["methods"]["climatology"] = metrics(yte, clim_te, t_clim)

# CAMELS-IND regional LSTM simulation (exceedance of the same threshold in the next 3 days)
ls_te = te["lstm_score"].to_numpy()
ls_va = va["lstm_score"].to_numpy()
mte, mva = np.isfinite(ls_te), np.isfinite(ls_va)
out["lstm_coverage"] = float(mte.mean())
t_lstm = pick(yva[mva], ls_va[mva])
out["methods"]["lstm_sim"] = metrics(yte[mte], ls_te[mte], t_lstm)
out["methods"]["lstm_sim_at_1"] = metrics(yte[mte], ls_te[mte], 1.0)
out["methods"]["xgboost_on_lstm_rows"] = metrics(yte[mte], p_te[mte], THR)
scores_te["lstm_sim"] = np.where(mte, ls_te, 0.0)
log("baselines done", {k: round(v["ba"], 3) for k, v in out["methods"].items()})

# ----------------------------------------------------------------------------- ablation by feature group
GROUPS = {
    "flow": [f for f in feats if f.startswith("qr_") or f in ("log_q", "q_obs_today")],
    "rain": [f for f in feats if f.startswith("prcp_")],
    "weather": [f for f in feats if f in ("tmax", "tmin", "rh", "pet", "aet")],
    "soil": [f for f in feats if f.startswith("sm")],
    "season": [f for f in feats if f.startswith("doy_")],
}
GROUPS["static"] = [f for f in feats if not any(f in v for v in GROUPS.values())]
out["groups"] = {k: len(v) for k, v in GROUPS.items()}
sub = tr.iloc[np.random.default_rng(SEED).choice(len(tr), min(500_000, len(tr)), replace=False)]
ysub = sub["y"].to_numpy().astype(int)
pos_w = float((ysub == 0).sum() / max((ysub == 1).sum(), 1))
VARIANTS = {"all": feats, "no_flow": [f for f in feats if f not in GROUPS["flow"]],
            "no_static": [f for f in feats if f not in GROUPS["static"]],
            "no_soil": [f for f in feats if f not in GROUPS["soil"]],
            "no_rain": [f for f in feats if f not in GROUPS["rain"]],
            "flow_only": GROUPS["flow"] + GROUPS["season"]}
out["ablation"] = {}
for name, fs in VARIANTS.items():
    m = XGBClassifier(n_estimators=3000, max_depth=6, learning_rate=0.05, subsample=0.8, colsample_bytree=0.8,
                      min_child_weight=20, reg_lambda=5.0, scale_pos_weight=pos_w, tree_method="hist",
                      eval_metric="aucpr", early_stopping_rounds=100, n_jobs=4, random_state=SEED)
    m.fit(sub[fs], ysub, eval_set=[(va[fs], yva)], verbose=False)
    pv = m.predict_proba(va[fs])[:, 1]
    t_ = pick(yva, pv)
    pt = m.predict_proba(te[fs])[:, 1]
    r = metrics(yte, pt, t_)
    r["n_features"] = len(fs)
    onset = (te["flood_today"] == 0).to_numpy()
    r["onset"] = metrics(yte[onset], pt[onset], t_)
    out["ablation"][name] = r
    if name == "no_flow":
        scores_te["xgb_no_flow"] = pt
        out["methods"]["xgb_no_flow"] = r
    log("ablation", name, round(r["ba"], 4), round(r["pr_auc"], 4))
del sub, tr

# ----------------------------------------------------------------------------- gauge-cluster bootstrap
rng = np.random.default_rng(SEED)
gids = te["gauge_id"].to_numpy()
ug = np.unique(gids)
idx_by = {g: np.flatnonzero(gids == g) for g in ug}
thr_by = {"xgboost": THR, "persistence": 0.5, "climatology": t_clim, "lstm_sim": t_lstm,
          "xgb_no_flow": out["ablation"]["no_flow"]["thr"]}
boot = {k: {"ba": [], "pr_auc": []} for k in thr_by}
for b in range(1000):
    pick_g = rng.choice(ug, size=len(ug), replace=True)
    ix = np.concatenate([idx_by[g] for g in pick_g])
    yb = yte[ix]
    if yb.min() == yb.max():
        continue
    for k, t_ in thr_by.items():
        s = scores_te[k][ix]
        boot[k]["ba"].append(balanced_accuracy_score(yb, (s >= t_).astype(int)))
        boot[k]["pr_auc"].append(average_precision_score(yb, s))
out["bootstrap"] = {}
for k, v in boot.items():
    out["bootstrap"][k] = {m: [float(np.percentile(v[m], 2.5)), float(np.percentile(v[m], 97.5))] for m in v}
    for m in ("ba", "pr_auc"):
        d = np.array(boot["xgboost"][m]) - np.array(v[m])
        out["bootstrap"][k][f"diff_{m}"] = [float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))]
log("bootstrap done")

# ----------------------------------------------------------------------------- calibration
def ece(y, p, bins=10):
    e = np.linspace(0, 1, bins + 1)
    tot, rows = 0.0, []
    for i in range(bins):
        m = (p >= e[i]) & ((p < e[i + 1]) if i < bins - 1 else (p <= 1))
        if m.any():
            rows.append({"lo": float(e[i]), "n": int(m.sum()), "conf": float(p[m].mean()), "freq": float(y[m].mean())})
            tot += m.sum() / len(p) * abs(p[m].mean() - y[m].mean())
    return float(tot), rows


iso = IsotonicRegression(out_of_bounds="clip").fit(p_va, yva)
p_cal = iso.predict(p_te)
e_raw, r_raw = ece(yte, p_te)
e_cal, r_cal = ece(yte, p_cal)
out["calibration"] = {"ece_raw": e_raw, "ece_iso": e_cal, "brier_raw": float(np.mean((p_te - yte) ** 2)),
                      "brier_iso": float(np.mean((p_cal - yte) ** 2)), "bins_raw": r_raw, "bins_iso": r_cal}

# ----------------------------------------------------------------------------- event lead time
ev_rows = []
for gid, gdf in te.groupby("gauge_id"):
    gdf = gdf.sort_values("date")
    ft = gdf["flood_today"].to_numpy()
    d = gdf["date"].to_numpy()
    pos = {pd.Timestamp(x): i for i, x in enumerate(d)}
    for i in range(7, len(gdf)):
        if ft[i] == 1 and np.all(ft[i - 7:i] == 0) and (pd.Timestamp(d[i]) - pd.Timestamp(d[i - 7])).days == 7:
            onset = pd.Timestamp(d[i])
            rec = {"gauge": int(gid)}
            for k in ("xgboost", "lstm_sim", "climatology", "xgb_no_flow", "persistence"):
                lead = 0
                for L in (3, 2, 1):
                    j = pos.get(onset - pd.Timedelta(days=L))
                    if j is not None:
                        s = scores_te[k][gdf.index[j]]
                        if s >= thr_by[k]:
                            lead = L
                            break
                rec[k] = lead
            ev_rows.append(rec)
out["events"] = {"n": len(ev_rows), "gauges": len({r["gauge"] for r in ev_rows})}
for k in ("xgboost", "lstm_sim", "climatology", "xgb_no_flow", "persistence"):
    leads = np.array([r[k] for r in ev_rows])
    out["events"][k] = {"warned_pct": float(100 * (leads > 0).mean()), "mean_lead_warned": float(leads[leads > 0].mean())
                        if (leads > 0).any() else 0.0, "lead_hist": {int(L): int((leads == L).sum()) for L in (0, 1, 2, 3)}}
log("events", out["events"]["n"])

# operating points of the selected model (threshold fixed on validation = THR; others descriptive only)
out["operating_points"] = []
for t_ in (0.30, THR, 0.60, 0.75):
    yp = p_te >= t_
    tp, fp = int((yp & (yte == 1)).sum()), int((yp & (yte == 0)).sum())
    out["operating_points"].append({"thr": float(t_), "recall": tp / int(yte.sum()), "precision": tp / max(tp + fp, 1),
                                    "alarms_per_1000": 1000 * float(yp.mean())})
# per-gauge balanced accuracy (gauges with at least one flood window in the test years)
out["per_gauge"] = {}
for k in ("xgboost", "xgb_no_flow", "lstm_sim"):
    vals = []
    for g, ix in idx_by.items():
        y_ = yte[ix]
        if y_.min() == y_.max():
            continue
        s = scores_te[k][ix]
        if k == "lstm_sim" and not np.isfinite(te["lstm_score"].to_numpy()[ix]).all():
            continue
        vals.append(balanced_accuracy_score(y_, (s >= thr_by[k]).astype(int)))
    v = np.array(vals)
    out["per_gauge"][k] = {"n": int(len(v)), "median": float(np.median(v)), "q1": float(np.percentile(v, 25)),
                           "q3": float(np.percentile(v, 75)), "min": float(v.min()), "values": v.tolist()}

# precision-recall curves for the figure (thinned to <= 200 points each)
from sklearn.metrics import precision_recall_curve  # noqa: E402

out["pr_curves"] = {}
for k in ("xgboost", "lstm_sim", "climatology", "xgb_no_flow"):
    s, y_ = (scores_te[k][mte], yte[mte]) if k == "lstm_sim" else (scores_te[k], yte)
    pr, rc, _ = precision_recall_curve(y_, s)
    keep = np.unique(np.linspace(0, len(pr) - 1, 200).astype(int))
    out["pr_curves"][k] = {"precision": pr[keep].tolist(), "recall": rc[keep].tolist()}
out["persistence_point"] = {"precision": out["methods"]["persistence"]["precision"],
                            "recall": out["methods"]["persistence"]["recall"]}
(WORK / "p4.json").write_text(json.dumps(out, default=float), encoding="utf-8")
log("done")
